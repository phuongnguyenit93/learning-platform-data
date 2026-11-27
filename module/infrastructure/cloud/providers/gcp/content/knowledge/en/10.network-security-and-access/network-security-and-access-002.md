# Hierarchical Firewall Policies and Network Firewall Policies on Google Cloud

> **Chapter:** Network Security and Access  
> **Lesson:** Hierarchical Firewall Policies and Network Firewall Policies  
> **Module:** CLOUD_PROVIDERS_GCP

In the **CLOUD_PROVIDERS_GCP** module, learners explore Google Cloud from project organization, IAM, and VPC to Compute Engine, GKE, Cloud Run, storage services, and databases. Through deployment scenarios, learners gain the skills to select services, protect resources, automate releases, and monitor reliability and cost. To govern networking safely across many projects, an enterprise cannot simply create isolated firewall rules and hope every team applies them consistently.

**Hierarchical firewall policies** allow administrators to enforce consistent security rules from the **organization** or **folder** down to VPCs in child projects. **Network firewall policies** organize rules per **VPC network**, at either **global** or **regional** scope. Together they are components of **Cloud Next Generation Firewall (Cloud NGFW)**, evaluated alongside **classic VPC firewall rules** and other network controls.

Key takeaway: **a rule with a numerically lower priority does not automatically beat a rule in a policy evaluated earlier**. You must understand the exact **policy association scope**, **firewall layer ordering**, **`allow`/`deny`/`goto_next` actions**, and **protected target resources** before predicting whether a connection passes.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish between hierarchical firewall policies, global network firewall policies, regional network firewall policies, Google-managed regional system firewall policies, and classic VPC firewall rules.
2. Describe the **organization → folder → project → VPC → workload** hierarchy and where firewall policies are associated.
3. Explain the fields of a firewall rule: **direction, priority, action, match, source/destination, protocol/port, target, logging**.
4. Apply the **two enforcement order modes**: `AFTER_CLASSIC_FIREWALL` and `BEFORE_CLASSIC_FIREWALL`.
5. Distinguish the effects of `allow`, `deny`, `goto_next`, behavior when no rule matches, and implied actions.
6. Design organization-level baseline policies, self-service delegation at the VPC level, and distinguish VM/GKE node protection from Cloud Run and managed services.
7. Read **effective firewall rules** using the Console/`gcloud` to diagnose blocked or unexpectedly open connections.
8. Create a verifiable change plan with least-privilege IAM, logging, testing, rollback, and cost assessment.

## 2. What Does a Firewall Control Inside a VPC?

Google Cloud firewalls evaluate connections on **supported targets**, based on fields such as traffic direction, source/destination addresses, protocol, port, and target. For VMs, rules are enforced at the virtual network layer attached to the **network interface**, rather than requiring operators to deploy a separate firewall appliance VM per subnet.

For example, a VM has internal IP `10.20.1.10` and runs PostgreSQL on port `5432`. Independent questions include:

| Layer | Question | Related tools/controls |
|---|---|---|
| Routing | Is there a route to `10.20.1.10` and a valid return route? | VPC routes, Cloud Router, VPN/Interconnect for hybrid |
| Network firewall | Is TCP/5432 from the specific source allowed to the VM? | Hierarchical, global/regional network, VPC firewall rules |
| Operating system | Does the machine have an OS firewall or a process listening on this port? | Linux/Windows firewall, server configuration |
| Identity | Does the user or workload have permission to access the resource/API? | IAM, service account, Workload Identity |
| Application | Does the database allow that user, TLS, and query? | PostgreSQL roles, network TLS, application |
| Observability | Can you tell where the connection was rejected? | Effective firewalls, VPC Flow Logs, firewall logging |

**Network firewalls do not replace IAM, TLS, or application authorization.** Conversely, granting IAM `roles/compute.admin` does not automatically open SSH, HTTP, or database ports in the firewall.

### 2.1. Ingress and Egress

- **INGRESS**: packets for new connections going **into** the protected target. For example, an on-premises user calling TCP/443 on a frontend VM.
- **EGRESS**: packets for new connections going **out** from the protected source target. For example, a batch VM opening an HTTPS connection to an external API.
- Google Cloud firewalls are generally **stateful** for allowed connections; responses for validly established flows are tracked by the service mechanism. You do not need an ingress rule solely to permit response packets for a valid egress connection.
- Choose IPv4/IPv6 source/destination ranges matching the address family. Opening `0.0.0.0/0` covers all IPv4 sources, whereas `::/0` covers all IPv6 sources; they are not interchangeable.

### 2.2. Resources Not Automatically Covered

VPC/Cloud NGFW firewall rules apply to clearly defined supported targets (such as VM interfaces and certain internal Envoy-based load balancer frontends in supported policy types/tiers). Do not assume every Google Cloud product behaves as a VM target:

- **Compute Engine**: VM network interfaces are the classic target; multiple rules can match the same interface.
- **GKE**: node/network interfaces and traffic to workloads according to the cluster networking model interact with VPC firewalls; **Kubernetes NetworkPolicy** and GKE Dataplane V2 form a separate control layer.
- **Cloud Run**: protected via ingress settings, IAM Invoker, HTTPS/Application Load Balancer/Cloud Armor, and VPC egress settings where applicable; a Cloud Run service does not automatically become a VM target for network firewall policies.
- **Cloud SQL**: private/public connectivity, database authentication, supported IAM features, and network access settings have their own scopes; do not assume VM rules apply directly to a Cloud SQL instance.
- **Cloud Storage**: IAM, bucket policies, endpoints, VPC Service Controls, and related controls are appropriate for object access control.

## 3. Five Policy Layers to Distinguish

| Mechanism | Where created/managed | Where attached/applied | Common role |
|---|---|---|---|
| **Hierarchical firewall policy (HFP)** | Organization/folder level, managed hierarchically | Associated at organization or folder; affects VPCs in matching child projects | Enterprise-wide security boundaries and common standards |
| **Regional system firewall policy** | Managed by Google Cloud | Region/VPC where Google services require them | System rules; users may only adjust logging in supported cases |
| **Classic VPC firewall rules** | Project owning the VPC | A single VPC network, per rule target | Traditional local rules |
| **Global network firewall policy** | Project | Associated to one or more VPCs in the **same project**, applies to all regions | Consistent rule group per VPC |
| **Regional network firewall policy** | Project and region | Associated with a VPC in the corresponding **region** | Region-specific rules or local workload controls |

Common trait across the three **customer-managed firewall policy** groups: a policy contains multiple **rules**, and to take effect it must have a valid **association** at the right scope. A newly created policy that is **not yet associated** generally **does not affect traffic**.

### 3.1. Resource Hierarchy Example

~~~mermaid
flowchart TD
    O["Organization: example.com<br/>Baseline HFP: shared security controls"]
    O --> F1["Folder: Engineering<br/>Additional business-unit HFP"]
    O --> F2["Folder: Finance<br/>Sensitive-network restriction HFP"]
    F1 --> P1["Project: app-dev"]
    F1 --> P2["Project: app-prod"]
    P2 --> N["VPC: prod-vpc<br/>Global network firewall policy"]
    N --> R["Region asia-southeast1<br/>Regional network firewall policy"]
    N --> R2["Region asia-northeast1"]
    R --> VM["VM/GKE nodes or supported targets"]
    P1 --> D["VPC: dev-vpc"]
~~~

The diagram illustrates **two policy attachment axes**: hierarchical follows the **resource ancestor tree**, while network policies follow the **VPC and region**. Whether a rule actually applies to a packet still depends on direction, target, and the rule's match fields.

### 3.2. Hierarchical Firewall Policy

HFP provides a rule set at an upper governance level, applied downward to resources within the association scope:

- Attached at the **organization** to establish baseline policy for all projects in the organization.
- Attached at a **folder** to apply additional constraints for a group of projects.
- Relevant policies are evaluated starting from the **organization**, then **higher ancestor folders** down toward the folder containing the project.
- If an HFP rule matches with `allow` or `deny`, that decision **terminates firewall evaluation**; a VPC-level rule cannot "override" it with a smaller priority number.
- If it matches `goto_next`, evaluation moves to the **next policy/layer**, without continuing to lower-priority rules inside the **same HFP**.
- If no rule matches, the HFP behaves like an implicit **`goto_next`**.

HFPs are highly effective for blocking prohibited ports/source ranges company-wide, enforcing baseline egress, or permitting approved administrative paths. However, an overly broad `allow` in an HFP can **bypass VPC-level denies**, so organization policies must be designed carefully.

### 3.3. Global Network Firewall Policy

A global network firewall policy is configured within a project and attached to VPCs in the **same project**. Its rules apply across every region where the VPC has supported targets. Examples:

- A shared policy for the production VPC in a Shared VPC host project.
- Baseline ingress/egress rules for VM groups and supported targets.
- Rules using **secure tags** or **target service accounts** to target specific VM groups.
- Advanced Cloud NGFW capabilities such as **Layer 7 inspection** with security profile groups depending on tier and supported products.

A VPC can attach **one global network firewall policy** at a given time. Check associations before editing, because modifying a rule in an attached policy **impacts every VPC that policy serves**.

### 3.4. Regional Network Firewall Policy

A regional network firewall policy applies to a VPC **within a specific region**. It fits scenarios where resources in Singapore have different requirements from Tokyo, or when an organization separates operations teams by location.

Example: VPC `prod-vpc` has VMs in Singapore and Tokyo. A regional policy attached for Singapore only affects targets in the associated region; you must not assume that policy also governs VMs in Tokyo.

### 3.5. Regional System Firewall Policy

Google Cloud can create **regional system firewall policies** when a supported service requires system rules. These rules are Google-managed and evaluated **after HFP and before the remaining user-configured layers**. Administrators can typically only enable/disable logging where supported, and cannot arbitrarily alter those rules' actions.

Therefore, when investigating "why is this traffic allowed?", inspect **effective firewall rules** rather than checking only the three policies created by the security team.

## 4. Components of a Firewall Policy Rule

| Component | Meaning | How to verify |
|---|---|---|
| **Priority** | Lower number has higher priority **within the same policy** | Commonly spaced by 100, 200, 300 to leave room for insertions |
| **Direction** | `INGRESS` or `EGRESS` | Identifies whether traffic enters or leaves the target |
| **Action** | `allow`, `deny`, `goto_next`, or supported inspection action | Distinguish terminal actions from layer delegation |
| **Source/destination** | IP/CIDR or other attributes supported per policy type/tier | Do not use source IP as destination IP |
| **Layer 4 protocol/port** | TCP/443, TCP/22, UDP/53, ICMP, etc. | Match both protocol and destination port |
| **Target** | All supported targets or service account/secure tag/target resources per rule type | Broad target by default if unconstrained |
| **Logging** | Record connection decisions per configuration and product capability | Incurs log cost/volume; requires retention and security |
| **Disabled** | Turn off rule enforcement while keeping its configuration | Do not treat a disabled rule as an active deny |
| **Description/owner** | Purpose, ticket, owner, expiration | Aids review and cleanup |

### 4.1. Priority Is Per-Policy, Not System-Wide

A priority `1000` rule in a **network policy** cannot jump ahead of a priority `2000` rule in an **organization HFP**: HFP is an **earlier-evaluated layer**.

Within **a single policy**, each rule has its own unique priority; **lower numbers** are evaluated first. In classic VPC firewall rules, a specific rule applies: if two rules share the **same priority**, both match the traffic, and one is allow while the other is deny, then **deny wins**. Do not apply that tie-breaker across two different policies or equate it with layer ordering.

### 4.2. Actions and Outcomes

| Action | Effect | Are subsequent rules still evaluated? |
|---|---|---|
| `allow` | Permits matched traffic at the firewall layer, subject to supported conditions | **No**; an allow decision is terminal |
| `deny` | Rejects matched traffic | **No**; a deny decision is terminal |
| `goto_next` | Delegates evaluation to the next policy/layer in the chain | **Remaining rules in the current policy are not evaluated** |
| No rule matches | Equivalent to implicit `goto_next` | Proceeds to the next evaluation step |
| `apply_security_profile_group` | Sends matched traffic to a security profile/firewall endpoint per supported product | Decided after inspection per profile; not treated as `goto_next` |

`goto_next` is a tool to **delegate decisions to lower layers**, not an allow for traffic. It is especially important when organization boundaries should only block prohibited cases while project teams remain free to design valid flows.

### 4.3. Targets, Secure Tags, and Service Accounts

- **Target service account**: in supported policy types, uses the service account identity **attached to the VM** to select matching network interfaces. It is **not** a mechanism for verifying HTTP user identities calling an application.
- **Secure tags**: Resource Manager secure tags can be used to select permitted targets per policy capabilities. Permissions to create/bind tags must be protected; anyone who can edit secure tags can indirectly change rule scope.
- **Traditional network tags** in classic VPC firewall rules differ from **secure tags** in Cloud NGFW; do not assume setting label `env=prod` or network tag `prod` automatically matches a secure tag condition.
- **Source secure tags** and other advanced fields are only available for specific rule types, traffic directions, and tiers; check the official specification rather than copying options blindly from one policy type to another.

Example: a rule targeting only **VMs carrying the backend service account** narrows blast radius compared to targeting all VMs in the VPC. However, changing a VM's service account can move that VM from one target group to another.

## 5. Evaluation Order: The Most Common Source of Mistakes

Google Cloud lets you choose the **network firewall policy enforcement order** on a VPC. HFPs and regional system firewall policies are always evaluated before these configurable layers.

### 5.1. Default: `AFTER_CLASSIC_FIREWALL`

For a default VPC using `AFTER_CLASSIC_FIREWALL`, the order is:

1. **Hierarchical firewall policies:** organization first, then ancestor folders from root downward.
2. **Regional system firewall policies:** if required by Google Cloud services.
3. **Classic VPC firewall rules.**
4. **Global network firewall policy.**
5. **Regional network firewall policies.**
6. **Implied actions.**

~~~mermaid
flowchart TD
    A["Traffic to/from target"] --> H["Hierarchical policies<br/>organization → folder"]
    H --> S["Regional system policies"]
    S --> C["Classic VPC firewall rules"]
    C --> G["Global network firewall policy"]
    G --> R["Regional network firewall policies"]
    R --> I["Implied action"]
    H -. "allow/deny: stop" .-> Stop["Terminal result"]
    S -. "allow/deny: stop" .-> Stop
    C -. "allow/deny: stop" .-> Stop
    G -. "allow/deny: stop" .-> Stop
    R -. "allow/deny: stop" .-> Stop
~~~

**Consequence:** if a classic VPC firewall rule already **allow**s the traffic, a **deny** rule in a global network firewall policy may **never be reached**. Therefore, you cannot create a deny in a network policy and assume it blocks all existing classic allows while the enforcement order remains at the default.

### 5.2. Option: `BEFORE_CLASSIC_FIREWALL`

With `BEFORE_CLASSIC_FIREWALL`, the order is:

1. Hierarchical firewall policies.
2. Regional system firewall policies.
3. **Global network firewall policy.**
4. **Regional network firewall policies.**
5. **Classic VPC firewall rules.**
6. Implied actions.

This option is useful when an enterprise wants network firewall policies to control traffic **before existing classic rules**, such as during a migration of security standards from classic VPC rules to Cloud NGFW. However, changing the enforcement order **alters behavior for the entire VPC**, potentially causing previously allowed applications to be denied or vice versa.

### 5.3. Quick Comparison Table

| Policy layer | `AFTER_CLASSIC_FIREWALL` (default) | `BEFORE_CLASSIC_FIREWALL` |
|---|---:|---:|
| Hierarchical | 1 | 1 |
| Regional system | 2 | 2 |
| Classic VPC rules | **3** | **5** |
| Global network | **4** | **3** |
| Regional network | **5** | **4** |
| Implied action | 6 | 6 |

**Do not assume "network policy always runs before VPC rules".** Inspect the **actual enforcement order attribute of the VPC** during troubleshooting, especially in migrated projects.

### 5.4. Implied Actions: Consider the Target Type

If no rule makes a decision and evaluation reaches the end:

- For a **VM network interface**, ingress has **implied deny**; egress has **implied allow**.
- For certain **internal Envoy-based Application/Proxy Network Load Balancer forwarding rules** within supported scope, the implied ingress action can be **allow**, unlike VM ingress.
- Do not extrapolate VM defaults to every Google Cloud resource or every version/tier.

Because implied egress can be allow, a secure network should not rely solely on "we haven't configured any egress rules." When outbound control is required, design an **explicit egress policy** accounting for Google APIs, DNS, patching, and partner connections before blocking.

## 6. Interpreting Conflict Scenarios

### 6.1. HFP Deny Beats VPC Allow

- Organization HFP: priority `1000`, ingress `deny` TCP/22 from `0.0.0.0/0` to target VM.
- Classic VPC: priority `100`, ingress `allow` TCP/22 from `203.0.113.10/32`.
- Traffic: from that IP to VM TCP/22.

**Result:** the HFP deny is evaluated first and terminates evaluation. The number `100` in the VPC being smaller than `1000` does not let allow win.

### 6.2. HFP Allow Can Also Bypass Lower-Layer Denies

- Organization HFP: ingress `allow` TCP/443 from `0.0.0.0/0` for all VMs.
- VPC policy: deny TCP/443 from source ranges outside the customer group.

**Result:** once the HFP allow matches, lower-layer denies never get a chance to execute. This is why broad allows should not be placed in HFPs unless the architecture proves it appropriate.

### 6.3. `goto_next` to Let Application Teams Decide

- Organization HFP: deny TCP/22 from the public Internet, except approved support paths.
- Next rule in HFP (for the specific target and delegated traffic): `goto_next`.
- Folder/Network/VPC: application team configures allow TCP/443 for frontend and denies external access to backend ports.

**Result:** `goto_next` does not itself permit traffic; it forwards evaluation to subsequent layers. If a lower-priority organization rule in the **same HFP** would have denied it, that rule **is no longer evaluated** once `goto_next` matches; thus the placement of `goto_next` must be carefully checked.

### 6.4. Classic Allow and Global Network Deny Under Both Enforcement Orders

| Component | Rule |
|---|---|
| Classic VPC | `allow` TCP/443 from `198.51.100.0/24` |
| Global network policy | `deny` TCP/443 from `198.51.100.0/24` |
| Hierarchical/system | No terminal rule matches |
| `AFTER_CLASSIC_FIREWALL` | **Allow from classic**; global deny is not evaluated |
| `BEFORE_CLASSIC_FIREWALL` | **Deny from global**; classic allow is not evaluated |

This example assumes target, direction, and source/destination all match. The ranges `198.51.100.0/24` and `203.0.113.0/24` are **documentation** ranges, not real customer IPs.

### 6.5. Neither HFP Nor Regional Policy Matches

Finding no matching rule in a policy means evaluation continues. If no layer has an applicable rule, the outcome depends on the **implied action** and target type. Never treat "no deny rules exist" as proof that ingress to a VM is allowed.

## 7. Designing for Multi-Project Enterprises and Shared VPC

### 7.1. Context

Organization `ExampleRetail` has the following projects:

- `retail-network-host`: VPC `prod-vpc` and subnets in Singapore/Tokyo; acts as the Shared VPC host.
- `retail-app-prod`: workloads using the host VPC; frontend behind a load balancer, plus several backend VMs.
- `retail-data-prod`: data VMs/jobs and dedicated managed services.
- `retail-app-dev`: development VPC for testing.

Requirements:

1. Disallow direct SSH from the Internet to production VMs.
2. Allow VM administration only through approved flows (e.g., IAP TCP forwarding or a dedicated management network).
3. Public frontends expose only TCP/443 by design; backends must not be exposed directly to the Internet.
4. Application teams manage allowed internal flows autonomously, without breaking the organization baseline.
5. Logging for sensitive rules, a change workflow, and anomaly reporting.

### 7.2. Policy Architecture

~~~mermaid
flowchart TD
    O["Organization HFP<br/>Baseline: block admin ports from untrusted sources"]
    O --> F["Folder HFP: Production<br/>Restrict entry paths into production"]
    F --> H["Host project: retail-network-host"]
    H --> V["prod-vpc<br/>Global network firewall policy"]
    V --> SG["Singapore: regional policy if needed"]
    V --> TK["Tokyo: regional policy if needed"]
    SG --> App["Backend VMs / GKE nodes"]
    TK --> App2["Batch VMs"]
    Shared["Service projects"] -. "Uses host VPC via Shared VPC" .-> V
~~~

**With Shared VPC:** evaluate firewall and VPC management permissions in the **host project** where the network lives, combined with the resource hierarchy of related projects and target types. A workload residing in a service project while using the host project's network does **not** mean the service project team can independently manage network firewall policies on the host. IAM for modifying policies should be separated from IAM for deploying workloads.

### 7.3. Reference Rule Matrix

| Scope | Illustrative priority | Direction | Match | Action | Purpose |
|---|---:|---|---|---|---|
| Organization HFP | 100 | Ingress | TCP/22 from untrusted sources to selected VM targets | Deny | SSH baseline |
| Organization HFP | 200 | Ingress | Approved admin flow to needed targets | `goto_next` or controlled allow | Leave decisions to layers closer to workloads |
| Folder Production HFP | 300 | Ingress | Prohibited source ranges for production | Deny | Production-specific restriction |
| Global network policy | 500 | Ingress | HTTPS to appropriate VM/frontend targets | Allow | Open the exact application serving path |
| Regional network policy | 600 | Egress | Singapore-specific destination ranges or protocols | Allow/Deny | Regional variation |
| Classic VPC rules | Varies | Both directions | Remaining flows delegated to the project | Allow/Deny | Legacy rules or application needs |

This table is a **logical model**, not a ready-to-run rule set. Do not use `0.0.0.0/0` as "untrusted sources" while intending to exclude IAP/management networks without writing proper exceptions; you must define specific match conditions and priorities.

### 7.4. A Controlled SSH Approach

For VMs requiring SSH via **IAP TCP forwarding**, IAP's source IP range is `35.235.240.0/20` in applicable IPv4 scenarios. Illustrative pattern:

- Block TCP/22 ingress from other sources through an appropriately scoped policy.
- Allow connections from `35.235.240.0/20` **only to VMs requiring administration** at the appropriate policy layer.
- Authenticate users via proper IAM/IAP, SSH keys/OS Login per configuration; a firewall allow **does not grant** SSH login rights.
- Do not enable a broad HFP deny for `0.0.0.0/0` expecting a network policy allow for IAP to override it.

In real deployments, you can use two HFP rules in specific order to allow/carve out an exception for IAP before denying the rest, or use appropriate targets/conditions. Verify **effective rules** and access paths on a test VM before rolling out organization-wide.

## 8. Firewall Policy Design and Approval Workflow

1. **Finalize flow requirements:** source, destination, port/protocol, target VM/service, region, application owner, and justification.
2. **Determine scope:** company-wide baselines in HFP; VPC-wide rules in global network policy; regional exceptions in regional network policy.
3. **Select precise targets:** service accounts/secure tags where supported, avoiding default all-targets.
4. **Review current effective rules:** ancestor HFPs, regional system policies, classic VPC rules, global and regional policies.
5. **Check enforcement order:** default or switched to `BEFORE_CLASSIC_FIREWALL`?
6. **Design priorities and actions:** which allow/deny rules are terminal, where `goto_next` is needed, what happens on no-match?
7. **Assess impact:** simulate valid and invalid connections; check admin operations, DNS, health checks, software updates, and return paths.
8. **Create policy in sandbox**, check associations, and use restricted targets before expanding.
9. **Enable selective logging**, test, and record evidence.
10. **Roll out in an approved change window**, monitor, and keep a rollback plan ready.
11. **Periodically review** expired rules, exceptions, members with policy-edit permissions, costs, and logs.

**Good design is not just "deny as much as possible."** An overly broad egress policy can break DNS, access to Google APIs, image pulls from Artifact Registry, log shipping, database connections, Cloud NAT, or essential health checks. The goal is to allow only **justified flows**, with diagnostics and recovery ready when issues arise.

## 9. Exploring and Inspecting via Google Cloud Console

In the Console, select the appropriate project/organization and navigate to the **Firewall policies** page or the corresponding **VPC network / Firewall** section (menu names may vary across UI updates).

### 9.1. Inspecting Hierarchical Policies

1. Identify the **organization** containing the target project and its ancestor folder chain.
2. Open the hierarchical firewall policies list and review policy ID/short name, associations, and rules.
3. Check which policy is attached at the organization or which folder, and whether rules match the traffic's target.
4. Read priority, direction, action, and enabled/disabled status.
5. Cross-check IAM for users/groups permitted to modify the policy.

### 9.2. Inspecting Global/Regional Network Policies

1. Select the **project containing the VPC** (for Shared VPC, typically the host project).
2. List **global** policies and **regional** policies in the region under investigation.
3. Open **Associations** to see which networks the policy is actually attached to.
4. Review rules and target filtering; remember an unassociated policy does not apply to the VPC.
5. Open VPC network details to view **Firewall rule view / effective rules** and enforcement order where permitted.

### 9.3. Inspecting a VM Network Interface

From the **VM instances** page, select a VM and inspect **Network interfaces → effective firewalls** or the equivalent view. This shows the rule set after filtering out rules that do not target the interface. When troubleshooting areas with internal load balancers, use the view for the right **region** and **target type**, rather than extrapolating from the VM view to the load balancer.

## 10. Read-Only `gcloud` Commands for Investigation

The commands below are for **observation**. Replace placeholders with real values in authorized projects/organizations. They do not modify firewalls, networks, or routes.

~~~bash
# Confirm active account and project in Google Cloud CLI.
gcloud auth list
gcloud config get-value project

# Hierarchical firewall policies managed at organization/folder level.
gcloud compute firewall-policies list --organization=ORG_ID
gcloud compute firewall-policies list --folder=FOLDER_ID

# Details and rules of a hierarchical policy.
gcloud compute firewall-policies describe HFP_ID --organization=ORG_ID
gcloud compute firewall-policies list-rules HFP_ID --organization=ORG_ID

# Global network firewall policies in a project.
gcloud compute network-firewall-policies list \
  --project=HOST_PROJECT_ID \
  --global

# Regional network firewall policies in a project.
gcloud compute network-firewall-policies list \
  --project=HOST_PROJECT_ID \
  --regions=asia-southeast1

# VPC, classic rules, and network state.
gcloud compute networks describe prod-vpc \
  --project=HOST_PROJECT_ID
gcloud compute firewall-rules list \
  --project=HOST_PROJECT_ID \
  --filter="network:prod-vpc"
~~~

**Syntax reminder:** `gcloud compute firewall-policies` is for **hierarchical** policies; `gcloud compute network-firewall-policies` is for **global/regional network** policies. The names look similar, but the resource types and scopes differ.

### 10.1. Viewing Effective Firewall Rules

~~~bash
# Effective firewall layers for a VPC.
gcloud compute networks get-effective-firewalls prod-vpc \
  --project=HOST_PROJECT_ID

# Firewall layers relevant to a specific region of a VPC.
gcloud compute network-firewall-policies get-effective-firewalls \
  --region=asia-southeast1 \
  --network=prod-vpc \
  --project=HOST_PROJECT_ID
~~~

Effective firewall output shows applicable policy sources, evaluation order, and relevant rules. Do not just see a rule named "allow-https" and conclude it decides the traffic; you must verify the exact **target**, **priority**, **match**, and **enforcement order**.

### 10.2. Viewing a Global Policy

~~~bash
gcloud compute network-firewall-policies describe POLICY_NAME \
  --project=HOST_PROJECT_ID \
  --global
~~~

For a regional policy, replace `--global` with `--region=REGION`. For a specific rule, check `gcloud compute network-firewall-policies rules describe --help` to pass the right `--global-firewall-policy` or region flag for your CLI version.

**Read permissions:** a user with a network viewer role cannot necessarily view all organization policies or ancestor associations. If you hit `PERMISSION_DENIED`, verify project, organization, identity, IAM scope, and policy before requesting higher privileges.

## 11. Hands-On Example: Creating a Global Network Firewall Policy in a Sandbox

Practice only when you have permission to create network policies and have a dedicated **sandbox project/VPC for testing**. The commands below **modify infrastructure** if executed live; creating the association causes rules to take effect on matching targets.

### 11.1. Create the Policy

~~~bash
gcloud compute network-firewall-policies create lab-global-fw \
  --project=SANDBOX_PROJECT_ID \
  --global
~~~

Once created, the policy **does not affect** any VPC until an association is attached.

### 11.2. Create a Sample Rule

For example, block SSH connections from the documentation IP range `198.51.100.0/24` to selected target VMs in the sandbox:

~~~bash
gcloud compute network-firewall-policies rules create 1000 \
  --project=SANDBOX_PROJECT_ID \
  --firewall-policy=lab-global-fw \
  --global-firewall-policy \
  --direction=INGRESS \
  --action=DENY \
  --src-ip-ranges=198.51.100.0/24 \
  --layer4-configs=tcp:22 \
  --enable-logging
~~~

The `198.51.100.0/24` range is **illustrative only**; in controlled testing, use an approved test source IP range. The sample omits `--target-secure-tags` or `--target-service-accounts`, so the target scope is **broad** per rule behavior; use it only in a sandbox VPC and never copy it verbatim to production.

### 11.3. Associate with a Network

~~~bash
gcloud compute network-firewall-policies associations create \
  --project=SANDBOX_PROJECT_ID \
  --firewall-policy=lab-global-fw \
  --network=sandbox-vpc \
  --name=lab-global-fw-to-sandbox-vpc \
  --global-firewall-policy
~~~

After associating, **inspect effective firewalls**. If the VPC still uses `AFTER_CLASSIC_FIREWALL` and a classic rule already **allow**s SSH from that source, the deny in the network policy will not govern that flow. You must evaluate outcomes based on the **actual evaluation order**, rather than assuming the rule failed due to syntax.

### 11.4. Changing Enforcement Order Is a Separate Change

The illustrative command below **modifies a VPC attribute** and can impact all workloads:

~~~bash
gcloud compute networks update sandbox-vpc \
  --project=SANDBOX_PROJECT_ID \
  --network-firewall-policy-enforcement-order=BEFORE_CLASSIC_FIREWALL
~~~

Run this only after comparing effective rules and testing impact in a controlled manner. In production, require a change ticket/owner, maintenance window, before/after tests, and a rollback plan back to the **recorded previous value**; never assume every VPC starts out as `AFTER_CLASSIC_FIREWALL`.

### 11.5. Safe Rollback / Detachment

To stop applying a policy to a network, you can **delete the association** following appropriate procedures and permissions, then re-read effective rules. Do not accidentally delete an entire policy that is attached to other VPCs. Never edit a rule in a shared policy locally without checking all of its associations, as it will affect multiple networks simultaneously.

## 12. IAM, Change Governance, and Protecting Policies

### 12.1. Separating Organization and Project Administration

| Job role | Need | Appropriate permission scope |
|---|---|---|
| **Org Security / Network Governance** | Design baseline HFPs and associations at org/folder level | Permissions to manage hierarchical policies and associations in assigned scope |
| **Network Platform Team** | Manage VPCs, global/regional network policies, effective firewalls | Relevant project/VPC or policy, typically the host project |
| **App Team** | Propose application traffic, view effective rules, delegated local rules | View permissions and narrow scope; restrict baseline edits |
| **SRE** | View logs, diagnose networking, resolve incidents | Read access to Cloud Logging, Monitoring, network config |
| **Security Audit** | Review changes, IAM grants, and configurations for compliance | Read, audit, and appropriate retention access |

Built-in roles like `roles/compute.securityAdmin` or `roles/compute.orgSecurityResourceAdmin` carry broad permissions for their respective resource types and scopes; **inspect the actual permission list** before granting. Never grant `roles/owner` just because an operator needs to view firewall logs.

### 12.2. Managing Rules as Security Changes

- **Requester:** state the flow and business purpose, not just "open port."
- **Approver:** service owner and security when targets are in production.
- **Implementer:** verify associations and existing rules, and deploy via pipeline/IaC where used.
- **Verifier:** test both valid and invalid connections, and inspect logs and applications.
- **Decommissioner:** clean up expired exceptions; never let "temporary" rules live indefinitely.

When using **Terraform** or infrastructure as code, avoid manually editing pipeline-owned policies only to have the next `apply` overwrite them unexpectedly. Use change reviews, proper imports/state management, and drift detection.

## 13. Diagnosing Unexpected Traffic Behavior

### 13.1. Eight-Step Process

1. **Lock down the flow:** source IP, destination IP, protocol, port, direction, VPC, region, and target VM/network interface.
2. **Separate routing from firewall:** do outbound/return routes exist? Does DNS return the right IP? Are VPN/BGP healthy?
3. **Check the hierarchy:** which org/folder HFPs are associated? Does any terminal rule match?
4. **Check regional system policies:** are there system rules for the target/region?
5. **Confirm VPC enforcement order:** `AFTER_CLASSIC_FIREWALL` or `BEFORE_CLASSIC_FIREWALL`?
6. **Read effective rules:** classic VPC, global and regional network policies; inspect target tags/SA, source range, port, disabled, priority.
7. **Verify end-to-end:** OS firewall, listener, load balancer health, TLS, application, and access permissions.
8. **Record evidence:** rule ID/policy, test timestamp, logging/Connectivity Tests results, root cause, and minimal required fix.

### 13.2. Symptom Matrix

| Symptom | Likely cause | How to verify |
|---|---|---|
| Created network deny yet SSH is still allowed | `AFTER_CLASSIC_FIREWALL`, classic allow wins first | Check enforcement order and classic effective rules |
| Created classic allow yet request is still blocked | HFP deny or network deny under `BEFORE_CLASSIC_FIREWALL` | Read effective rules layer by layer |
| HFP rule does not affect dev project | Policy unassociated or different folder scope | Check org/folder ancestry and associations |
| Network policy rule has no effect | Policy unassociated from VPC or target mismatch | Check policy association/secure tags/SA |
| Only Singapore is unreachable | Regional policy, subnet, route, frontend, or system rule | Compare effective firewalls per region |
| Attached secure tag yet rule doesn't match | Wrong tag scope/binding, permissions/propagation, unsupported target type | Check effective tags and rule target |
| VM loses connectivity after changing service account | Rule targets the old service account | Compare VM NIC config and target account |
| GKE pod unreachable despite VPC allow | Kubernetes NetworkPolicy/GKE Dataplane, pod routing, DNS, or service mesh | Check both VPC firewall and in-cluster policies |
| Cloud Run API returns 403 despite VPC allow | IAM Invoker, ingress, identity, application auth | Inspect Cloud Run config and HTTP response |
| No firewall logs for a `goto_next` rule | `goto_next` is not a terminal decision | Check logs of the allow/deny rule that actually matched |
| Timeout despite effective rule `allow` | Routing, OS firewall, health check, TLS, backend | Use Connectivity Tests, logs, and protocol/port tests |
| Log costs spike after enabling logging on all rules | High flow volume and long retention | Filter critical rules, monitor log volume |

### 13.3. Logs and Connectivity Tests

**Firewall Rules Logging** records allowed or denied connections for rules with logging enabled. For policy rules, log fields help identify the relevant decision; do not enable logging on `goto_next` because it is not a terminal action. Logs may not capture every moment or traffic type and must be read according to the service's schema.

**VPC Flow Logs** provide IP traffic visibility within supported scopes using sampling/aggregation. **Connectivity Tests** (Network Intelligence Center) simulates paths using Google Cloud configuration—useful for spotting suspect routes/firewalls, though it cannot confirm every internal OS, on-premises peer, or application state.

Additional observability sources:

- **Cloud Audit Logs**: who created/modified/deleted policies, rules, and associations.
- **Cloud Monitoring**: failed connections, latency, application status, traffic shifts.
- **Cloud Logging**: rule hit/deny details when logging is enabled, correlated with request/application logs.
- **Policy/IaC revision history**: explains changes before and after the incident timestamp.

### 13.4. Do Not Fix Issues by Opening Everything Up

When a TCP/443 connection fails, never immediately add `allow all 0.0.0.0/0` at the organization level. Doing so can bypass lower-layer denies and impact hundreds of projects. Diagnosis must identify **the first matching terminal rule in the actual enforcement chain** and confirm there are no remaining issues in routing, DNS, or the application.

## 14. Cost, Reliability, and Cloud NGFW Limits

### 14.1. Cost

Cloud NGFW offers feature tiers such as **Essentials, Standard, and Enterprise**, with differing capabilities and pricing. Certain advanced match criteria (such as FQDNs, threat intelligence, address groups, Layer 7 inspection) have specific support prerequisites and pricing. Additionally:

- **Firewall logging** can incur Cloud Logging storage/ingestion/query charges at high volume.
- **Cloud Monitoring/Connectivity Tests** and monitoring products have their own limits and pricing per type.
- Traffic traversing VPN/Interconnect, load balancers, or egress still incurs network charges per respective pricing tables.
- Misconfigured policies can cause downtime or block health checks, increasing incident remediation costs.

Do not assume security policies are "infinitely free" just because you don't deploy firewall VMs. Check the **Cloud NGFW** pricing and regional/tier availability pages before production rollout.

### 14.2. Reliability and Large-Scale Changes

HFPs spanning many projects are powerful but carry a **large blast radius**. Before changing organization policies:

1. List affected folders/projects/VPCs.
2. Test in a small scope or limited set of target resources.
3. Put policies/rules under version control with an assigned owner and ticket.
4. Monitor critical connections: DNS, metadata/Google APIs, image registries, Cloud SQL, load balancer health checks, hybrid links, and pipelines.
5. Prepare rollback **at the appropriate policy layer**, without disabling all security to recover.
6. Monitor post-deployment and document lessons learned if disruptions occur.

## 15. Simulation Exercise Without Creating Resources

### 15.1. Problem Data

An enterprise has:

- Organization HFP `org-baseline`:
  - Priority 100: **deny** ingress TCP/22 from `0.0.0.0/0` to VMs.
  - Priority 200: **goto_next** ingress TCP/443 from `198.51.100.0/24`.
- Folder production HFP `prod-controls`:
  - Priority 300: **deny** ingress TCP/443 from `198.51.100.128/25`.
- Classic VPC:
  - Priority 500: **allow** ingress TCP/443 from `198.51.100.0/24`.
- Global network policy:
  - Priority 400: **deny** ingress TCP/443 from `198.51.100.0/24`.
- VPC `prod-vpc` contains supported frontend target VMs, the global policy is associated, and no regional system rules terminally match the simulated flows. Assume no other allow/deny rules.

### 15.2. Questions

1. Source `198.51.100.10` calls TCP/22 on a VM: what is the outcome and why?
2. Source `198.51.100.200` calls TCP/443: which rule decides?
3. Source `198.51.100.10` calls TCP/443 when the VPC uses `AFTER_CLASSIC_FIREWALL`: what is the outcome?
4. Same TCP/443 source when switched to `BEFORE_CLASSIC_FIREWALL`: what is the outcome?
5. If the global network policy association is removed, what decision remains for question 4?
6. If HFP rule priority 100 is removed, can a classic deny and a global allow (if present) determine the outcome on their own? What information is needed?
7. In a multi-project model, why can't you turn "deny SSH across all production" into a local rule in one arbitrary project and treat it as an organization baseline?
8. If a new policy uses `target-service-accounts` but a VM uses a different service account, does the rule apply?
9. If a resource is a Cloud Run service rather than a VM target, which protection layers should be used instead of relying solely on VM rules?
10. List at least five verification steps before changing a VPC's enforcement order.

### 15.3. Suggested Answers

- **Question 1:** denied by organization HFP, evaluated first.
- **Question 2:** organization HFP priority 200 `goto_next` forwards to the folder; folder `prod-controls` priority 300 denies because the source falls inside `198.51.100.128/25`.
- **Question 3:** after organization `goto_next`, the folder does not match, and classic VPC allow is evaluated before global under `AFTER_CLASSIC_FIREWALL`.
- **Question 4:** after HFP, global deny is evaluated before classic under `BEFORE_CLASSIC_FIREWALL`.
- **Question 5:** without the global rule, classic allow is evaluated (assuming no other terminal rules).
- **Question 6:** you need the exact direction, target, match criteria, policy associations, enforcement order, and all other rule layers; you cannot compare priority numbers across two different policies.
- **Question 7:** a local rule only applies to that project's VPC; it does not govern the whole organization and lacks HFP precedence.
- **Question 8:** target mismatch prevents the rule from applying to that VM.
- **Question 9:** Cloud Run ingress, IAM Invoker, load balancer/Cloud Armor, or appropriate application/network security controls.
- **Question 10:** gather effective rules, traffic matrix, confirm current terminal matches, test in sandbox, assess impact, prepare rollback and monitoring.

This is a **rule evaluation simulation exercise**, not a recommendation to use those illustrative CIDRs as real policies.

## 16. Common Design Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Thinking priority is global across all policies | Mispredicting allow/deny outcomes | Determine policy layer first, then priority within each policy |
| Assuming global network policy always precedes classic VPC rules | New denies may fail to block old allows | Check `networkFirewallPolicyEnforcementOrder` |
| Adding a broad HFP allow because "other teams will deny below" | Terminal HFP allow bypasses lower-level denies | Use `goto_next` and narrowly scoped allows |
| Interpreting `goto_next` as "check next rule in same policy" | Subsequent rules after `goto_next` are skipped | Understand it delegates to the next policy/layer |
| Forgetting to associate the policy | Rules have no effect on traffic | Verify association and target scope |
| Using labels/network tags instead of secure tags | Rules select wrong targets | Distinguish tag models and tag-binding permissions |
| Creating an all-targets rule when only one VM needs it | Large blast radius | Use supported service accounts/secure tags/target resources |
| Opening IPv4 ingress and assuming IPv6 is also open | IPv6 is blocked or governed by a different policy | Handle `::/0`, routing, and IPv6 rules separately |
| Inspecting only the VPC rule list | Missing HFPs, regional system, and network policies | Check effective firewalls for the right VPC/region/VM |
| Using VM firewalls to govern all of Cloud Run/Cloud SQL | Missing ingress IAM/service-level controls | Use the proper protection layers for each service |
| Enabling logging on every flow indiscriminately | Increased volume/cost, harder troubleshooting | Enable selectively and monitor log volume |
| Detaching a shared policy to fix one project's issue | Impacts all other projects | Check associations, make narrow fixes, and roll back cleanly |

## 17. Pre-Deployment Checklist

- [ ] Identified **organization/folder/project/VPC/region** and owner for each layer.
- [ ] Distinguished hierarchical, regional system, classic VPC, global network, and regional network policies.
- [ ] Recorded the **actual enforcement order** of the VPC.
- [ ] Reviewed **terminal** rules and `goto_next` across all relevant policy layers.
- [ ] Chosen appropriate priorities **within each policy**, leaving gaps for future rule insertions.
- [ ] Distinguished target service accounts, secure tags, network tags, labels, and target resources.
- [ ] Verified policy **associations** and blast radius, especially in Shared VPC.
- [ ] Defined source/destination, direction, IPv4/IPv6, protocol, and port for every flow.
- [ ] Tested both **allow cases** and **deny cases**, checking application, routing, DNS, and OS firewall.
- [ ] Inspected effective firewall rules for the exact network/region/VM interface.
- [ ] Enabled necessary logging, monitored cost, and protected log data.
- [ ] Established least-privilege IAM, approvals, policy versioning, rollback, and accountable owner.
- [ ] Verified post-deployment that Compute Engine/GKE/Cloud Run and data services operate as expected.

## 18. Official Google Cloud Documentation

Syntax, evaluation order, target types, and prerequisites for advanced features may change over time. When operating in live projects, verify against current documentation and tool versions:

- [Cloud NGFW — Firewall policies and rules](https://docs.cloud.google.com/firewall/docs/firewall-policies-overview)
- [Evaluation order for firewall policies and rules](https://docs.cloud.google.com/firewall/docs/firewall-policies-rule-eval-order)
- [Hierarchical firewall policies](https://docs.cloud.google.com/firewall/docs/hierarchical-firewall-policies)
- [Global network firewall policies](https://docs.cloud.google.com/firewall/docs/network-firewall-policies)
- [Regional network firewall policies](https://docs.cloud.google.com/firewall/docs/regional-firewall-policies)
- [Manage hierarchical firewall policies](https://docs.cloud.google.com/firewall/docs/manage-hierarchical-firewall-policies)
- [Manage global network firewall policies](https://docs.cloud.google.com/firewall/docs/manage-global-firewall-policies)
- [Manage regional network firewall policies](https://docs.cloud.google.com/firewall/docs/manage-regional-firewall-policies)
- [Cloud NGFW overview and pricing tiers](https://docs.cloud.google.com/firewall/docs/about-firewalls)
- [gcloud: network firewall policies list](https://docs.cloud.google.com/sdk/gcloud/reference/compute/network-firewall-policies/list)
- [gcloud: hierarchical firewall policies list](https://docs.cloud.google.com/sdk/gcloud/reference/compute/firewall-policies/list)

**Key takeaway:** Hierarchical firewall policies let organizations **establish top-down security boundaries**; global/regional network firewall policies **manage rules by VPC and region**. Any connection is decided by the **exact chain of applied policies**, the **first rule producing a terminal result**, and related network/application components. Mastering the default `AFTER_CLASSIC_FIREWALL` order and optional `BEFORE_CLASSIC_FIREWALL` mode is the key to designing, deploying, auditing, and troubleshooting Google Cloud consistently across multiple projects.
