# VPC Firewall Rules and Priority Evaluation on Google Cloud

> **Chapter:** Network Security and Access  
> **Module:** **CLOUD_PROVIDERS_GCP** — Explore Google Cloud from project organization, IAM, and VPC to Compute Engine, GKE, Cloud Run, storage services, and databases. Through deployment scenarios, learners gain the skills to choose services, protect resources, automate releases, and monitor reliability and cost.

When an application cannot call an API running on Compute Engine or a VM unexpectedly receives connections from the Internet, the root cause may lie in **VPC firewall rules**. To explain it accurately, you need to know **where the request originates and goes, through which VPC, whether it is ingress or egress, which rules apply, and which priority is evaluated first**. If the organization also attaches hierarchical/network firewall policies, you must account for the evaluation order across policy layers as well.

This lesson guides you through reading, configuring, comparing, and verifying VPC firewall rules. The core focus is **priority**: lower numbers are evaluated first, more specific rules do not automatically win, and DENY only beats ALLOW at the same priority within the classic VPC rules layer.

## Learning Objectives

After this lesson, learners will be able to:

1. Explain the role and limitations of VPC firewall rules for VM NICs, GKE nodes, load balancers, and hybrid connections.
2. Identify all required fields: **network, direction, action, priority, target, source, destination, protocol/port, disabled, logging**.
3. Accurately determine the ALLOW/DENY outcome in scenarios with overlapping rules, tied priorities, and implied actions.
4. Distinguish classic VPC firewall rules from hierarchical, global/regional network, and regional system firewall policies.
5. Use network tags or service accounts in a controlled manner to specify targets and sources.
6. Practice inventorying rules, setting up a rule priority lab with gcloud, and reading effective firewall rules and logs.
7. Analyze connectivity failures and design appropriate rules for Compute Engine, GKE, Cloud Run, VPC/VPN, storage services, and databases.

## 1. How Does VPC Firewall Control Traffic?

A VPC is a logical network on Google Cloud. VPC firewall rules are configured at the scope of **a single VPC network**, but enforced at supported **target network interfaces/resources**. The easiest case to picture is a Compute Engine VM's NIC: a rule can allow or block a new incoming or outgoing connection.

~~~mermaid
flowchart LR
    C["Client"] --> R["DNS / route / VPN / NAT"]
    R --> F["Firewall evaluation"]
    F --> VM["VM backend"]
    VM --> G["Guest OS + application + IAM/TLS"]
    VM --> E["Egress evaluation"]
    E --> D["DB / API / other networks"]
~~~

A complete connection typically has to pass through **multiple independent layers**:

| Layer | Example question |
|---|---|
| Routing | Does the sender have a route to the destination IP, and is the return path valid? |
| VPC firewall | Which rule allows/blocks new connections on the destination/source NIC? |
| Operating system | Do the guest firewall and daemon allow that port? |
| Application | Is the backend listening and accepting requests, and are TLS/auth configured properly? |
| IAM | Does the principal have permission to call Cloud Run, Cloud Storage, or the database through the appropriate mechanism? |

An **ALLOW tcp:443** rule only addresses the firewall portion within its scope. It does not create routes, grant IAM permissions, or start a web server.

### 1.1. Ingress and Egress from the Target's Perspective

| Direction | Target | Illustrated new connection |
|---|---|---|
| **INGRESS** | VM NIC receiving packets | 10.60.0.10 → 10.60.0.20:8080 |
| **EGRESS** | VM NIC sending packets | 10.60.0.20 → 172.20.5.20:5432 |

Each rule has only **one direction**. To control new connections initiated from either side, you must analyze each direction according to the appropriate target. Do not use a server's INGRESS rule as proof that a client is permitted for EGRESS.

### 1.2. Stateful: Return Traffic Is Handled Differently from New Connections

VPC firewall rules are **stateful**. Once a new connection is allowed, return packets matching the connection state are also allowed through. The connection tracker uses information corresponding to the **5-tuple** (source IP, destination IP, source port, destination port, protocol), with source and destination reversed for the response.

~~~mermaid
sequenceDiagram
    participant C as Client 10.60.0.10
    participant F as VPC firewall
    participant B as Backend 10.60.0.20
    C->>F: TCP SYN to 10.60.0.20:8080
    F->>F: Evaluate new connection
    F->>B: ALLOW if a matching rule exists
    B-->>F: TCP SYN-ACK response
    F->>F: Match connection tracking
    F-->>C: Allow valid response
~~~

You do not need a reverse ingress allow rule just to permit the SYN-ACK of an already-allowed connection. However, if the backend **initiates a new connection** back to the client, that is a separate flow and requires checking the corresponding direction.

Stateful tracking does not guarantee every response reaches the client: routing, NAT, local firewalls, and connection tracking limits still apply. For fragmented traffic or expired connection states, check the documentation for the specific protocol.

### 1.3. Implied Actions for VM NICs

If none of the relevant policy layers produce a decision and evaluation reaches the final step, Google Cloud applies implied actions:

- **Ingress to a VM NIC:** **DENY**.
- **Egress from a VM NIC:** **ALLOW**.

These are the final fallback outcomes when no prior rule decides; they are not two visible rules that users can always edit directly. For **certain managed Envoy proxies/forwarding rules of internal load balancers**, the implied ingress action can be **ALLOW**. Therefore, do not mechanically apply the conclusion "all ingress is denied" to every target resource type.

A **default** VPC may be created with pre-populated rules such as **default-allow-internal, default-allow-ssh, default-allow-rdp, default-allow-icmp**, typically at priority 65534. These are **pre-created** rules that can be listed, edited, or deleted depending on permissions; they are distinct from implied actions. A newly created **custom VPC** normally does not include that set of ingress allow rules.

## 2. Components of a Classic VPC Firewall Rule

| Attribute | Meaning | Example value |
|---|---|---|
| **Name** | Unique name of the rule within the project | allow-api-from-private |
| **Network** | VPC containing the rule | app-vpc |
| **Direction** | INGRESS or EGRESS | INGRESS |
| **Action** | ALLOW or DENY | ALLOW |
| **Priority** | Integer **0–65535**, lower number means higher priority | 900 |
| **Target** | NICs/VMs to which the rule applies | target tag backend |
| **Source** | IP ranges or source tag/SA depending on direction | 10.60.0.0/24 |
| **Destination** | Destination IP ranges if used | 10.60.0.20/32 |
| **Protocol/port** | TCP, UDP, ICMP, and destination ports | tcp:8080 |
| **Disabled** | Skip rule evaluation when disabled | false |
| **Logging** | Record information about connections matching the rule | enabled |

**Risky defaults:** priority defaults to **1000**, default direction is **INGRESS**, default target is **all VMs in the network** if unspecified, and when no ingress source is chosen, IPv4 can default to **0.0.0.0/0**. Therefore, never create an allow rule with just a name and port without explicitly specifying source and target.

### 2.1. Network, Target, and Source Have Distinct Roles

~~~text
VPC: app-vpc
  VM A: 10.60.0.10, network tag=client
  VM B: 10.60.0.20, network tag=backend
  VM C: 10.60.0.30, network tag=admin
~~~

A rule with **network=app-vpc**, **target-tags=backend**, **source-ranges=10.60.0.0/24**, and **rules=tcp:8080** only matches new connections to VM B on TCP 8080 from sources within that CIDR. It does not automatically open ports on VM A or VM C.

**Target tags** are different from **source tags**. The target of INGRESS is the **receiving** instance; the target of EGRESS is the instance **initiating the outbound connection**.

### 2.2. Protocol/Port Is Not Just a Service Name

- **tcp:22** is TCP with destination port 22.
- **tcp:443** is TCP with destination port 443.
- **udp:53** is UDP with destination port 53; DNS may also use TCP 53.
- **icmp** is ICMP, not TCP; ping may fail while TCP still works.
- **tcp** without a port list can match all TCP destination ports depending on configuration.

Specify only the protocol/ports actually needed. Avoid opening **all protocols** for troubleshooting when the exact traffic flow is not yet known.

### 2.3. IPv4, IPv6, and Limitations

The CIDR **0.0.0.0/0** covers all IPv4 addresses but **does not cover IPv6**. If the VPC uses IPv6, you must evaluate IPv6 rules/source ranges such as **::/0** according to supported product configurations. A single classic VPC rule cannot mix IPv4 and IPv6 ranges in the same rule.

Additionally, certain traffic types such as the Compute Engine metadata server have special rules and are not necessarily governed by classic VPC firewall in the same way. Do not rely on a deny-all egress rule to replace access controls to the metadata server.

## 3. Priority Evaluation Algorithm in Classic VPC Rules

To evaluate a new connection, first filter only the classic rules that:

1. Belong to the **correct VPC** and are **enabled**.
2. Have the matching **direction**.
3. Have a **target** matching the NIC/VM.
4. Have valid source/destination criteria and **match the IP** of the traffic.
5. Have a protocol/port matching the request.

Then:

- Select the **lowest priority number** among the remaining matching rules.
- If both **ALLOW** and **DENY** exist at the same priority, **DENY wins**.
- If multiple rules share the same priority and same action, the result is the same, though you should not rely on which specific rule name is reported as applied in logs.
- If no rule matches, evaluation may **fall through to network firewall policies** according to the VPC's enforcement order; only at the very end does it reach the implied action.

~~~mermaid
flowchart TD
    S["New connection"] --> F["Filter network, enabled, direction, target, IP, protocol/port"]
    F --> M{"Any classic rule matches?"}
    M -- "No" --> NEXT["Next policy layer or implied action"]
    M -- "Yes" --> P["Select lowest priority number"]
    P --> T{"Both ALLOW and DENY at same priority?"}
    T -- "Yes" --> D["DENY"]
    T -- "No" --> A["Apply action of highest-priority rule"]
~~~

### 3.1. Lower Number Has Higher Priority

| Rule | Priority | Source | Port | Action |
|---|---:|---|---|---|
| allow-app | **800** | 10.60.0.0/24 | tcp:8080 | ALLOW |
| deny-app | 1000 | 10.60.0.0/24 | tcp:8080 | DENY |

A request from **10.60.0.10** to backend TCP 8080 is **ALLOW**ed within the classic rules layer, because 800 is evaluated before 1000.

### 3.2. DENY Only Beats ALLOW at the Same Priority

| Rule | Priority | Source | Port | Action |
|---|---:|---|---|---|
| allow-admin-ssh | 900 | 10.60.0.10/32 | tcp:22 | ALLOW |
| deny-subnet-ssh | 900 | 10.60.0.0/24 | tcp:22 | DENY |

The request **10.60.0.10 → backend:22** matches both rules, resulting in **DENY**. If you change allow-admin priority to **800** and keep deny at 900, requests from admin are **ALLOW**ed, while client **10.60.0.30** remains denied.

### 3.3. Specificity Does Not Automatically Win

| Rule | Priority | Source | Port | Action |
|---|---:|---|---|---|
| deny-ssh-all | **500** | 0.0.0.0/0 | tcp:22 | DENY |
| allow-specific-admin | 800 | 10.60.0.10/32 | tcp:22 | ALLOW |

Requests from **10.60.0.10** are still denied. Routing's **longest prefix match** principle does not apply when determining firewall priority. A more specific /32 source does not beat a /0 source when it has a lower priority (higher number).

### 3.4. Duplicate Priorities Are Permitted but Should Be Limited

Classic VPC rules allow multiple rules to share the same priority. If two rules share the same priority, the same ALLOW action, and both match a request, the outcome is still ALLOW, but which rule name is logged as the winning rule may be nondeterministic. For firewall policy rules within the same policy, uniqueness/priority rules differ.

To make inserting new rules and interpreting logs easier, teams can space priorities in increments such as **100, 200, 300...** rather than incrementing by 1. This is an internal convention, not a numbering scheme reserved by Google Cloud.

## 4. Evaluating a Matrix with Overlapping Rules

Suppose VPC **lab-vpc** has a backend VM with network tag **backend** and the following classic rules:

| Rule | Priority | Direction | Source/destination | Protocol | Action |
|---|---:|---|---|---|---|
| R1 allow-admin-ssh | 800 | INGRESS | Source 10.60.0.10/32 | tcp:22 | ALLOW |
| R2 deny-ssh | 900 | INGRESS | Source 10.60.0.0/24 | tcp:22 | DENY |
| R3 allow-app | 1000 | INGRESS | Source 10.60.0.0/24 | tcp:8080 | ALLOW |
| R4 deny-app-other | 1200 | INGRESS | Source 0.0.0.0/0 | tcp:8080 | DENY |
| R5 deny-external | 1000 | EGRESS | Destination 203.0.113.0/24 | tcp:443 | DENY |

Assume no hierarchical/network policies decide beforehand. Addresses **203.0.113.0/24** and **198.51.100.0/24** are used for documentation examples.

| New flow | Matching rules | Result |
|---|---|---|
| 10.60.0.10 → backend:22 | R1 and R2 | **ALLOW**, priority 800 |
| 10.60.0.30 → backend:22 | R2 | **DENY**, priority 900 |
| 10.60.0.30 → backend:8080 | R3 and R4 | **ALLOW**, priority 1000 |
| 10.61.0.10 → backend:8080 | R4 | **DENY**, priority 1200 |
| backend → 203.0.113.5:443 | R5 | **DENY egress** |
| backend → 198.51.100.5:443 | Does not match R5 | May reach implied **ALLOW egress** |
| 10.60.0.30 → backend:3306 | No matching ingress allow | Implied **DENY ingress VM** if no other layer decides |
| Client → VM without backend tag | Rules targeting backend do not apply | Must evaluate other rules and implied action |

**Try changing priorities:** If R2 moves from 900 to **700**, admin SSH is denied because 700 beats 800. If R1 also moves to **700**, it is still denied because both rules have the same priority and conflicting actions.

## 5. Implied Actions Do Not Replace Routing, NAT, or IAM

**ALLOW egress** does not guarantee a VM can reach the Internet. To reach the Internet, a VM still needs a route, an external IP or Cloud NAT/equivalent solution, DNS, and an operational destination service.

**ALLOW ingress** does not guarantee a successful TCP handshake. The receiving host might not be listening on the port, its guest firewall might block it, or the return route might fail.

The **default** network may contain the rule **default-allow-ssh** at priority 65534. A matching classic rule **deny-ssh** at priority 1000 will block traffic before that default rule. Do not confuse **default-allow-ssh** with the implied ingress action.

### 5.1. Source Tags and Service Accounts Can Broaden the Source Set

In an ingress classic rule, if you set both:

~~~text
source-ranges = 10.60.0.0/24
source-tags   = trusted
~~~

then the effective source set is the **union (OR)** of the IP ranges and sources matching the tag under supported conditions, **not the intersection (AND)**. The same consideration applies to supported combinations of source ranges and source service accounts.

### 5.2. Egress Deny and Ingress Allow Are Two Separate Evaluations

If VM A has **egress DENY tcp:5432**, while VM B has **ingress ALLOW tcp:5432** from A, a new connection initiated by A can still be blocked at A. An ingress rule on B does not override an egress deny on A.

## 6. When Multiple Firewall Policy Layers Exist

Google Cloud provides **Cloud Next Generation Firewall (Cloud NGFW)** with multiple policy layers. If an organization attaches a hierarchical policy or a VPC attaches a network firewall policy, **you cannot directly compare the priority numbers of two rules located in different layers**.

Layers to distinguish:

- **Hierarchical firewall policies:** policies attached at the organization or folder level, which can be inherited down to VPCs in child projects.
- **Regional system firewall policies:** Google-managed policies to support specific products; not typical user-created policies.
- **Global network firewall policy:** a policy attached to a VPC with network-wide scope.
- **Regional network firewall policies:** policies applied in the corresponding region of the VPC.
- **Classic VPC firewall rules:** rules created with **gcloud compute firewall-rules create**, each belonging to a single VPC.
- **Implied actions:** final outcome when preceding layers do not terminate evaluation.

### 6.1. Two Important Enforcement Orders

The VPC attribute **networkFirewallPolicyEnforcementOrder** controls whether global/regional network firewall policies are evaluated **before or after** classic VPC rules.

| Order | **AFTER_CLASSIC_FIREWALL** (default) | **BEFORE_CLASSIC_FIREWALL** |
|---:|---|---|
| 1 | Hierarchical firewall policies | Hierarchical firewall policies |
| 2 | Regional system firewall policies | Regional system firewall policies |
| 3 | **Classic VPC firewall rules** | **Global network firewall policy** |
| 4 | Global network firewall policy | Regional network firewall policies |
| 5 | Regional network firewall policies | **Classic VPC firewall rules** |
| 6 | Implied actions | Implied actions |

Within the hierarchical layer, the **organization's** policy is evaluated first, followed by ancestor folders from top to bottom. Within each policy, rules are evaluated according to that policy's target/direction/priority.

~~~mermaid
flowchart TD
    S["New connection"] --> H["Hierarchical policies: org → folders"]
    H --> SYS["Regional system policies"]
    SYS --> MODE{"VPC enforcement order?"}
    MODE -->|"AFTER_CLASSIC"| C1["Classic VPC rules"]
    C1 --> G1["Global network policy"]
    G1 --> R1["Regional network policies"]
    MODE -->|"BEFORE_CLASSIC"| G2["Global network policy"]
    G2 --> R2["Regional network policies"]
    R2 --> C2["Classic VPC rules"]
    R1 --> I["Implied action"]
    C2 --> I
~~~

The diagram illustrates **the evaluation path if preceding layers have not yet determined a result**. A matching ALLOW or DENY rule in an evaluated layer can terminate evaluation; a packet does not necessarily traverse every box.

### 6.2. goto_next Differs from ALLOW and DENY

In certain firewall policies:

- **ALLOW:** permits traffic and stops evaluation according to the policy mechanism.
- **DENY:** blocks traffic and stops evaluation.
- **goto_next:** delegates evaluation to the next policy/layer.
- Matching no rule in a policy typically passes evaluation onward accordingly.

Classic VPC firewall rules only have two actions, **ALLOW/DENY**; **goto_next** is not used as an action in classic rules.

Some policies support additional actions for advanced network inspection, such as delegating to a security profile group. That capability depends on the policy type and Cloud NGFW configuration and should not be inferred from classic firewall behavior.

### 6.3. Priorities Are Only Comparable Within Their Evaluation Scope

Suppose an organization has a hierarchical **DENY tcp:22 from Internet at priority 2000**. Inside the VPC, a classic **ALLOW tcp:22 at priority 100** also matches.

**The result is DENY** because the hierarchical policy is evaluated first; the number 100 being lower than 2000 does not make the classic rule win. To create a legitimate exception, you must modify the policy at the appropriate scope or use a mechanism supported by that policy, after security review.

Similarly, a network policy **DENY tcp:8080** and a classic VPC **ALLOW tcp:8080** can yield different results depending on the network firewall policy enforcement order:

- **AFTER_CLASSIC_FIREWALL:** classic ALLOW can decide first.
- **BEFORE_CLASSIC_FIREWALL:** network policy DENY can decide first.
- Hierarchical and regional system policies still precede both in either case.

**Do not change enforcement order in production** just to test fixing a single connection without assessing the impact on all applications.

### 6.4. How to Verify Multi-Layer Evaluation

Answer these questions in order:

1. Which enforcement order is the VPC using?
2. Are there any hierarchical policies attached to the project's organization or ancestor folders?
3. Are there regional system policies or global/regional network policies?
4. Which rule in the **first-evaluated layer** matches direction, target, source, destination, and protocol?
5. If that rule is **goto_next** or no rule matches, evaluate the next layer.
6. Within classic VPC rules, compare priorities **0–65535** and resolve any ALLOW/DENY tie.
7. When all layers pass evaluation forward, check the implied action for the **specific target type**.

## 7. Network Tags, Service Accounts, and Target Selection

### 7.1. Network Tags

A **network tag** is a string attached to a VM to group instances subject to the same rule. For example, three VMs in a VPC:

~~~text
web-1:    tag=frontend
api-1:    tag=backend
admin-1:  tag=admin
~~~

A rule with **target-tags=backend** applies to the corresponding NICs of VMs carrying the backend tag in that VPC. Tag names do not create routes or grant IAM permissions. Anyone with permission to modify a VM's network tags can change which firewall rules apply to that VM, so that permission must be protected.

**Network tags** are not **resource labels**, nor are they identical to **secure tags** used in certain Cloud NGFW firewall policies.

### 7.2. Target Service Account

Classic VPC rules can also target by the **service account attached to a VM**, for example **api-runtime@PROJECT_ID.iam.gserviceaccount.com**.

The advantage is that VM identity is generally governed more strictly than an arbitrary tag string. However:

- A single classic rule **cannot simultaneously use** both target network tags and target service accounts.
- Restrictions also apply when combining source tags with target service accounts or source service accounts with target tags.
- In a standalone VPC, service accounts used in criteria must fit project scope rules; Shared VPC has specific rules across host/service projects.
- Changing a VM's service account may require stopping/restarting the VM.
- On GKE, the VPC rule's service account criterion applies to the **node VM**, not the Kubernetes ServiceAccount of individual Pods.

### 7.3. Limitations of Source Tags and Source Service Accounts

In classic ingress rules, source network tags/service accounts only resolve to **documented, supported** source IP addresses of VM network interfaces in the same VPC. They do not arbitrarily cover all source alias IP ranges, public IPs, or on-premises clients.

If the source is an on-premises network via Cloud VPN/Interconnect, you typically need to use a **source CIDR** matching the IP plan, check NAT, and combine with IAM/application controls. Do not assign a source tag in Google Cloud assuming it represents all on-premises machines.

## 8. Hands-On: Reading Current Configuration with gcloud

This section is **read-only** and can be run on any project where you have read permissions. There is no need to create VMs or modify policies.

~~~bash
PROJECT_ID="YOUR_PROJECT_ID"
VPC="YOUR_VPC_NAME"

# Classic VPC firewall rules in the project.
gcloud compute firewall-rules list \
  --project="$PROJECT_ID" \
  --format="table(name,network,direction,priority,disabled)"

# Rules for a single VPC only.
gcloud compute firewall-rules list \
  --project="$PROJECT_ID" \
  --filter="network:$VPC" \
  --format="table(name,direction,priority,sourceRanges,allowed,denied)"

# Details of a single rule.
gcloud compute firewall-rules describe "RULE_NAME" \
  --project="$PROJECT_ID" \
  --format=yaml

# VPC config; inspect enforcement order and network details.
gcloud compute networks describe "$VPC" \
  --project="$PROJECT_ID" \
  --format=yaml
~~~

For each rule, record:

| Question | Field to check |
|---|---|
| Is the rule enabled? | disabled |
| Which network does it apply to? | network |
| What is the direction? | INGRESS/EGRESS |
| Priority and action? | priority, allowed or denied |
| Who is the target? | targetTags/targetServiceAccounts or all instances |
| Source/destination? | sourceRanges, destinationRanges, sourceTags, sourceServiceAccounts |
| Which ports? | allowed/denied protocol/ports |
| Is logging enabled? | logConfig |

If a rule does not show up here, do not conclude traffic is permitted: **network firewall policies, hierarchical policies, regional system policies**, and implied actions still apply.

### 8.1. Effective Firewall Rules of a VM NIC

~~~bash
gcloud compute instances network-interfaces get-effective-firewalls \
  "VM_NAME" \
  --zone="ZONE" \
  --network-interface="nic0" \
  --project="$PROJECT_ID"
~~~

This command displays the firewall rules applied to the **selected NIC**, including supported policy sources. Seeing a rule listed here **does not prove that rule wins for all traffic**: you still need to check the IP/protocol/port tuple and the layer/priority order.

In **Shared VPC**, the network belongs to the **host project** while the VM may reside in a **service project**. Investigators must inspect the VM's NIC as well as the host network's policies/rules, rather than looking only inside the service project.

## 9. Lab: Creating Firewall Rules with Priority Exceptions

This lab **creates resources and may incur charges**; perform it only in an authorized learning project. The example chooses a custom VPC to avoid the pre-created ingress allow rules of the default VPC.

### 9.1. Parameters and Requirements

| Component | Lab value |
|---|---|
| Project | YOUR_PROJECT_ID |
| VPC | firewall-priority-lab |
| Subnet/region | demo-subnet / asia-southeast1 |
| CIDR | 10.60.0.0/24 |
| Admin VM | 10.60.0.10 |
| Ordinary client VM | 10.60.0.30 |
| Backend VM | 10.60.0.20, network tag backend |
| API | TCP 8080 |
| SSH | TCP 22 |

Desired policy:

- ALLOW TCP **8080** from **10.60.0.0/24** to backend.
- DENY TCP **22** from the subnet to backend.
- Create an ALLOW TCP **22** exception specifically for admin IP **10.60.0.10/32**, with higher priority than the deny rule.
- Do not open an SSH/RDP rule for **0.0.0.0/0**.

~~~mermaid
flowchart LR
    ADMIN["10.60.0.10 admin"] -->|"TCP 22 ALLOW; TCP 8080 ALLOW"| B["10.60.0.20 backend"]
    CLIENT["10.60.0.30 client"] -->|"TCP 22 DENY; TCP 8080 ALLOW"| B
    INTERNET["Internet"] -. "No new ingress allow" .-> B
~~~

### 9.2. Create the VPC and Subnet

~~~bash
PROJECT_ID="YOUR_PROJECT_ID"
REGION="asia-southeast1"
VPC="firewall-priority-lab"
SUBNET="demo-subnet"

# MUTATING — run only in a lab project.
gcloud compute networks create "$VPC" \
  --project="$PROJECT_ID" \
  --subnet-mode=custom

gcloud compute networks subnets create "$SUBNET" \
  --project="$PROJECT_ID" \
  --network="$VPC" \
  --region="$REGION" \
  --range="10.60.0.0/24"

# READ-ONLY — verify.
gcloud compute networks describe "$VPC" --project="$PROJECT_ID"
gcloud compute networks subnets describe "$SUBNET" \
  --project="$PROJECT_ID" --region="$REGION"
~~~

Before choosing a CIDR, ensure it does not overlap with other connected VPCs or hybrid networks. Firewall rules cannot fix routing failures caused by overlapping CIDRs.

### 9.3. ALLOW TCP 8080 Rule

~~~bash
# MUTATING — target only VMs with the backend tag.
gcloud compute firewall-rules create "lab-allow-api" \
  --project="$PROJECT_ID" \
  --network="$VPC" \
  --direction=INGRESS \
  --priority=1000 \
  --action=ALLOW \
  --source-ranges="10.60.0.0/24" \
  --target-tags="backend" \
  --rules="tcp:8080" \
  --enable-logging
~~~

### 9.4. DENY TCP 22 Rule

~~~bash
# MUTATING — deny SSH from the subnet to backend.
gcloud compute firewall-rules create "lab-deny-ssh" \
  --project="$PROJECT_ID" \
  --network="$VPC" \
  --direction=INGRESS \
  --priority=900 \
  --action=DENY \
  --source-ranges="10.60.0.0/24" \
  --target-tags="backend" \
  --rules="tcp:22" \
  --enable-logging
~~~

### 9.5. ALLOW TCP 22 Exception for Admin

~~~bash
# MUTATING — allow only 10.60.0.10/32 with higher priority than deny.
gcloud compute firewall-rules create "lab-allow-admin-ssh" \
  --project="$PROJECT_ID" \
  --network="$VPC" \
  --direction=INGRESS \
  --priority=800 \
  --action=ALLOW \
  --source-ranges="10.60.0.10/32" \
  --target-tags="backend" \
  --rules="tcp:22" \
  --enable-logging
~~~

**Verification by priority:**

| Source | Destination port | Rule in classic layer | Result |
|---|---:|---|---|
| 10.60.0.10 | 22 | lab-allow-admin-ssh, priority 800 | ALLOW |
| 10.60.0.30 | 22 | lab-deny-ssh, priority 900 | DENY |
| 10.60.0.10 | 8080 | lab-allow-api, priority 1000 | ALLOW |
| 10.60.0.30 | 8080 | lab-allow-api, priority 1000 | ALLOW |
| IP outside CIDR | 8080 | No lab allow | Implied deny VM if no other policy decides |

This is an **example to understand priority**, not a recommendation to expose direct SSH in production. In production, you can use IAP, OS Login, and approved administrative access mechanisms.

### 9.6. Verify the Created Rule Set

~~~bash
gcloud compute firewall-rules list \
  --project="$PROJECT_ID" \
  --filter="network:$VPC" \
  --sort-by="priority" \
  --format="table(name,priority,direction,sourceRanges,allowed,denied,targetTags)"

gcloud compute firewall-rules describe "lab-allow-admin-ssh" \
  --project="$PROJECT_ID" \
  --format=yaml
~~~

**To perform real end-to-end testing**, you need a backend VM with the network tag **backend**, the right IP, an appropriate OS firewall, and an application listening on TCP 8080. Creating a firewall rule alone **does not start a service**. You can use VMs pre-provisioned in your learning project.

If creating new VMs, note:

- Only use test instances authorized to incur costs.
- Avoid external IPs when unnecessary; IAP or private admin paths require corresponding IAM and firewall configuration.
- Check the subnet, unused IP, network tag, and guest OS.
- Do not use **ping** results to verify TCP 22 or TCP 8080, since ping uses ICMP.

Example check from the client/admin VM when netcat is available and backend is listening:

~~~bash
# RUN INSIDE THE LAB CLIENT/ADMIN VM.
nc -vz -w 5 10.60.0.20 8080
nc -vz -w 5 10.60.0.20 22
~~~

When a request returns **connection refused**, the backend may lack a listener. On timeout, distinguish between firewall, routing, and host firewall. When receiving HTTP 401/403, you may need to check authentication and application authorization.

## 10. Advanced Cases Requiring Separate Reasoning

### 10.1. Overly Broad Allow Beats Narrow Deny

| Rule | Priority | Source | Protocol | Action |
|---|---:|---|---|---|
| allow-all-tcp | **300** | 0.0.0.0/0 | tcp | ALLOW |
| deny-ssh | 500 | 0.0.0.0/0 | tcp:22 | DENY |

Both match when a client calls TCP 22. The result is **ALLOW** because 300 beats 500 even though the deny specifically targets TCP 22. You must evaluate the ordering and narrow the allow rule rather than just looking at the name deny-ssh.

### 10.2. Same Priority 900: DENY Wins

Two classic rules both match TCP 443:

- allow-https priority 900.
- deny-https priority 900.

The result is **DENY**, regardless of creation order.

### 10.3. Hierarchical Deny Cannot Be Overridden by Classic Allow

An organization-level hierarchical policy **DENY SSH from Internet** coexists with a VPC classic **ALLOW SSH priority 0**. If the hierarchical rule matches and terminates evaluation, the request is still **blocked**.

### 10.4. Network Enforcement Order Changes the Outcome

Given a matching network policy **DENY 8080** and classic VPC **ALLOW 8080**:

- **AFTER_CLASSIC_FIREWALL:** classic ALLOW can decide first.
- **BEFORE_CLASSIC_FIREWALL:** network policy DENY can decide first.

Any conclusion must still check hierarchical/system policies first, not just the two rules in the example.

### 10.5. Different Directions Are Not a Conflict

An **EGRESS deny TCP 5432** on the client VM can block new connections to the database even if the DB VM has **INGRESS allow TCP 5432**. The two rules apply to **different NICs/directions**, so the server's allow does not "beat" the client's deny.

## 11. GKE, Cloud Run, Load Balancers, and Hybrid

### 11.1. GKE

GKE uses Compute Engine nodes and VPC networking, so VPC firewalls can apply to node NICs. However:

- Rules based on a **VM service account** identify the node, not the Kubernetes ServiceAccount of individual Pods.
- In VPC-native GKE, Pod IPs can reside in **secondary alias ranges**; source tags/service accounts have limitations in identifying source IPs and do not automatically cover alias IPs.
- GKE may create/maintain rules for clusters, nodes, or load balancers; directly modifying GKE-managed rules can cause issues when the controller reconciles.
- For Pod-to-Pod isolation requirements, examine **Kubernetes NetworkPolicy** or GKE-supported pod security mechanisms.

### 11.2. Cloud Run

Do not use classic VM target tags to govern inbound HTTP requests to a Cloud Run service. Cloud Run has **ingress settings**, IAM, load balancer mechanisms, and Cloud Armor depending on the architecture.

When Cloud Run accesses a VPC via **Direct VPC egress** or a supported connector, you must check how firewall/network policies affect the **actual egress path** per connectivity mode. A firewall allow is only one piece and does not replace permissions to call Cloud SQL, Storage, or internal services.

### 11.3. Load Balancers and Health Checks

Many load balancers require ingress rules for **health checks** and traffic from proxies to VMs/backends.

- For Google Front Ends, check the health-check/proxy source ranges for the specific load balancer type.
- For certain Envoy-based load balancers, the backend sees connections from the **proxy-only subnet**.
- Unhealthy backends can result from denied health checks, even when clients can still connect to the frontend.

Do not take a generic health-check source IP list and apply it to every LB type; consult the documentation for the specific load balancer being deployed.

### 11.4. Cloud VPN, Interconnect, Shared VPC

Connections from on-premises to VMs over Cloud VPN/Interconnect still require matching ingress on the VM, typically based on the **actual CIDR** after NAT. On-premises firewalls and bidirectional routes must also be correct.

In Shared VPC, firewall rules and logs belong to the **host project** owning the VPC; VMs may reside in service projects. A classic rule is not automatically shared with another VPC simply because VPC Peering or VPN exists.

## 12. Firewall Rules Logging and Effective Rule Troubleshooting

### 12.1. Enable Logging Purposefully

In the lab, **--enable-logging** was added to the three classic firewall rules. Depending on rule type and logging options, Google Cloud writes information about processed connections to **Cloud Logging**.

~~~bash
# READ-ONLY — inspect logging and priority of a rule.
gcloud compute firewall-rules describe "lab-deny-ssh" \
  --project="$PROJECT_ID" \
  --format="yaml(name,priority,logConfig)"

# MUTATING — enable only after authorization and accounting for log costs.
gcloud compute firewall-rules update "RULE_NAME" \
  --project="$PROJECT_ID" \
  --enable-logging
~~~

In **Logs Explorer**, you can filter by the firewall log source:

~~~text
resource.type="gce_subnetwork"
logName="projects/YOUR_NETWORK_PROJECT/logs/compute.googleapis.com%2Ffirewall"
~~~

**YOUR_NETWORK_PROJECT** is the project owning the VPC; in Shared VPC this is typically the **host project**. Log fields can contain VM name, firewall rule, action, protocol, source/destination, and metadata according to configuration.

**Seeing no logs does not mean there is no traffic**:

- The logged rule was preempted by a rule/policy in an earlier layer, so it was never reached.
- Source/destination, direction, target, or protocol did not match.
- Logging was not enabled or the updated configuration has not fully propagated.
- The user lacks Logs Viewer permission, or selected the wrong project or time range.
- Traffic was dropped at an earlier network layer before reaching the inspected NIC/rule.

Enabling logs incurs storage/ingestion costs based on usage. Retention periods and access permissions must be controlled because logs can expose topology, internal IPs, and application activity.

### 12.2. How Do VPC Flow Logs and Audit Logs Differ?

| Log source | Question answered |
|---|---|
| **VPC Firewall Rules Logging** | How were matching connections handled by firewall rules? |
| **VPC Flow Logs** | What flows traversed supported infrastructure, and how much traffic? |
| **Cloud Audit Logs** | Who created/modified/deleted a firewall rule, VPC, or policy? |
| **Guest OS logs** | Which service is running/listening on which port, or blocked by the OS firewall? |
| **Application logs** | Did the request reach the app, and what TLS/auth/business logic error was returned? |

VPC Flow Logs use sampling/aggregation rather than full packet capture. Do not use a flow log to prove that application IAM permitted a call.

### 12.3. Network Intelligence Center — Connectivity Tests

**Connectivity Tests** helps verify network paths based on Google Cloud network configuration. The tool can identify which route, firewall rule, or policy is the blocking factor according to the configuration model.

Workflow:

1. Identify the **source IP/resource**, **destination IP/resource**, **protocol, port**, and associated project/VPC.
2. Run the test with those exact parameters.
3. Read the results for routing, firewall decision, VPC/hybrid path, and backend where supported.
4. If the model reports blocked, inspect the exact policy layer, rule, priority, and target.
5. If the model reports reachable but live requests fail, inspect listener, guest firewall, DNS, TLS, IAM, and service health.

Connectivity Tests cannot observe all devices or network paths outside Google Cloud. When investigating Cloud VPN/Interconnect, combine it with telemetry from on-premises devices.

## 13. Troubleshooting Procedure for Failed Connections

Example: VM **client 10.60.0.30** cannot reach backend **10.60.0.20:8080**.

~~~mermaid
flowchart TD
    A["Request failed"] --> D{"DNS resolves to right IP?"}
    D -- "No" --> DNS["Check DNS"]
    D -- "Yes" --> R{"Bidirectional routes valid?"}
    R -- "No" --> ROUTE["Check routing, VPN, NAT"]
    R -- "Yes" --> E["Inspect effective firewalls + policy order"]
    E --> F{"Which rule decides?"}
    F -- "Hierarchical/network" --> H["Check association, rule action, and goto_next"]
    F -- "Classic VPC" --> C["Check direction, target, source, port, priority"]
    F -- "No deny" --> OS["Check OS firewall, listener, TLS, IAM"]
    H --> L["Connectivity Tests + logs"]
    C --> L
    L --> FIX["Make minimal change then re-verify"]
~~~

### 13.1. Eight Investigative Questions in Order

1. What is the **actual source** IP? Does NAT or a load balancer rewrite the source IP?
2. What is the **actual destination** IP/port? Does DNS/redirect send the request to a different backend?
3. Which VPCs do the **destination NIC and source NIC** belong to? Does the VM have multiple NICs?
4. Are you analyzing a **new ingress/egress connection**, or only **return traffic**?
5. Do the VM's **target tags/service accounts** match the rule?
6. Do any **hierarchical, regional system, or global/regional network policies** apply before classic rules?
7. In the classic layer, which rule has the lowest priority number? Is there an **ALLOW and DENY priority tie**?
8. If the firewall allows it, is there an issue with **routing, OS firewall, app listener, or TLS/IAM**?

### 13.2. Common Symptoms

| Symptom | Possible cause | Check |
|---|---|---|
| SSH allow exists yet connection is still blocked | Hierarchical deny or higher-priority classic deny; missing IAP/OS Login | Effective firewalls, IAM, actual source |
| Client A reaches API, client B cannot | Different /32, CIDR, source tag, or route | Compare 5-tuple and matching rules |
| Firewall allows but TCP is refused | Service not listening, host firewall, or wrong destination | Guest logs, port listener |
| API returns HTTP 403 | IAM/authorization at app or gateway; connection likely reached server | Request logs, principal, and permissions |
| VM has egress allow but cannot reach Internet | Missing Cloud NAT/external IP, route, or DNS | Check routing, NAT, DNS |
| GKE service turns unhealthy after rule edit | Blocked node, proxy/health check, or GKE-managed rule | Backend health, GKE controller, policy |
| Classic allow behaves differently after new VPC config | Network firewall policy enforcement order changed | Read VPC attributes and policy associations |
| No firewall logs appear | Wrong project, rule didn't win, logging disabled | Effective rules and Cloud Logging |
| Combining source-ranges with source-tags widens access | The two criteria combine via OR | Verify all sources that actually match |
| IPv6 request misses IPv4 rule | Only 0.0.0.0/0 configured | Check IPv6 ranges/dual stack |
| On-premises to VM times out | Ingress firewall, BGP/VPN routing, NAT, peer firewall | Connectivity Tests and logs on both ends |

Never temporarily enable an **allow all** rule just to prove the network can work: doing so can expose the VM to the Internet and still fails to pinpoint the root cause. Check layer by layer and keep changes tightly scoped.

## 14. Designing Firewall Rules for Production Systems

### 14.1. Principle of Least Privilege

- Only **allow necessary ports/protocols**.
- Restrict **source IP ranges** or supported source identities to actual traffic flows.
- Use appropriate **target tags/service accounts**, avoiding targeting all instances unnecessarily.
- Protect permissions that can **modify network tags**, service accounts, and firewall policies.
- Restrict SSH/RDP from the Internet; prefer IAP, OS Login, bastions, or approved administrative paths.
- Separate development/staging/production environments cleanly using projects/VPCs/policies.
- Use hierarchical policies for shared security boundaries when required by the organization.
- Before applying broad denies, check **health checks, proxy-only subnets, internal traffic, and system services**.
- Maintain a register of owners, justifications, tickets, and review dates for exception rules.

### 14.2. Document Intent Rather Than Just a Rule Name

A good change request:

~~~text
Application: checkout-api
Environment: production
VPC / Project: [identifier]
Source: GKE backend node/workload by actual IP/subnet
Destination: VM legacy-api
Protocol/Port: TCP 8080
Direction: INGRESS at VM legacy-api
Target selector: controlled target service account or network tag
Policy layer: classic VPC / network policy / hierarchical
Priority: [number and rationale]
Action: ALLOW
Review date: [date]
Owner / approver: [team]
Test results: allowed flow PASS, denied flow PASS
Rollback: [PR/config version]
~~~

Avoid arbitrary names like allow-test123 lacking purpose. During audits, explaining **which source, which destination, which port, and why** matters more than the total rule count.

### 14.3. Terraform Example

~~~hcl
resource "google_compute_firewall" "allow_api_from_private" {
  name    = "allow-api-from-private"
  network = "firewall-priority-lab"

  direction = "INGRESS"
  priority  = 1000

  source_ranges = ["10.60.0.0/24"]
  target_tags   = ["backend"]

  allow {
    protocol = "tcp"
    ports    = ["8080"]
  }

  log_config {
    metadata = "INCLUDE_ALL_METADATA"
  }
}
~~~

This is an illustrative configuration for a classic rule and omits full provider/project/version blocks and VPC lifecycle management. In real deployments, manage Terraform state, run plan/diff, and review IAM and effective policies before applying.

### 14.4. Controlled Change Process

1. Describe the request using source IP, destination IP, port, protocol, and direction.
2. Read the current state, effective rules, and policy layers.
3. Determine the minimal change needed, avoiding unnecessary expansion of targets or sources.
4. Check IaC plan/Connectivity Tests; document the rollback plan.
5. Deploy in a test environment or appropriate change window.
6. Test both **flows that should be allowed** and **flows that should be blocked**, observing logs/SLOs.
7. Save evidence, record the owner, and schedule reviews for exception rules.

When enabling new deny/allow rules on a shared network serving multiple services, account for load balancer traffic, monitoring agents, CI/CD, and backup systems; a single rule can cause outages outside the immediate application team.

## 15. Case Study: Checkout, GKE, Legacy VM, and Cloud SQL

Suppose an enterprise runs a Cloud Run frontend, containerized APIs on GKE, a legacy task backend on a Compute Engine VM, and a Cloud SQL database. Workloads connect within a production VPC, alongside a Cloud VPN link to an on-premises network.

### 15.1. Flow and Control Matrix

| Flow | Layers to evaluate | Additional controls |
|---|---|---|
| GKE workload → legacy VM TCP 8080 | GKE node egress if denied; VM ingress by actual source IP | GKE NetworkPolicy, mTLS, app auth |
| Legacy VM → database | VM egress; private service connectivity and network config per Cloud SQL type | DB credentials, TLS, IAM if used |
| Cloud Run → private API | Cloud Run ingress, IAM, and network path per configuration | ID token, Cloud Run Invoker |
| Ops → VM TCP 22 | VPC ingress and IAP/admin path | IAM, OS Login, SSH keys |
| On-premises → VM | VPC ingress by post-NAT CIDR, VPN/BGP | On-prem firewall, TLS, and bidirectional routes |
| Internet → VM SSH | No matching allow or intentional deny policy | Do not attach unnecessary external IPs |

### 15.2. Pitfall One: Classic Allow Has No Effect

The organization applies a hierarchical policy **deny SSH from 0.0.0.0/0** for production. The application team adds a classic **allow SSH priority 0** yet still cannot connect. Adding an even lower-numbered classic rule will not help, because the hierarchical policy already decided beforehand.

Resolution: identify an approved admin path (IAP/OS Login or organization-approved alternative), and submit an exception request to the policy-owning team if needed.

### 15.3. Pitfall Two: API 403 Mistaken for Firewall Deny

GKE calls an API and receives **HTTP 403** from the server. This indicates the HTTP request likely reached the application/gateway and was rejected by IAM or business authorization. The team must inspect logs and headers/identity safely rather than opening more ports to "fix" a 403 without evidence of a network block.

### 15.4. Pitfall Three: Tunnel Is UP but Database Is Unreachable

Both the Cloud VPN tunnel and BGP session are UP, yet the VM cannot connect to the on-premises database. Checks must cover outbound/return routes, post-NAT source IP, on-premises firewall, VPC egress, and database port. **A firewall ALLOW rule is only one prerequisite** and does not replace verifying the full path and DB authentication.

### 15.5. Measuring Effectiveness After Changes

After modifying rules, the team checks:

- Do required flows succeed?
- Are unauthorized flows still denied?
- Are load balancer health checks and workload latency stable?
- Do logs confirm the intended rule handled the traffic?
- Was there any unexpected spike in log volume and cost?

## 16. Self-Check Exercises

### 16.1. Questions

1. ALLOW TCP 443 priority **800** and DENY TCP 443 priority **900** both match in classic rules. What is the outcome?
2. ALLOW source **10.60.0.10/32 priority 900** and DENY source **10.60.0.0/24 priority 900** both match. What is the outcome?
3. DENY TCP 22 priority 500 source 0.0.0.0/0 and ALLOW TCP 22 priority 800 source /32. Is the /32 source allowed?
4. Why should **source ranges + source tags** in an ingress rule not be interpreted as an AND operation?
5. Can classic VPC firewall rules be used to grant **roles/run.invoker** for Cloud Run?
6. A VPC in **BEFORE_CLASSIC_FIREWALL** mode has a matching network policy DENY and a classic ALLOW. What is the outcome if the earlier policy terminates evaluation?
7. Can you compare classic rule priority **100** against hierarchical rule priority **1000** to conclude the classic rule wins?
8. Is implied ingress deny for VMs the default result for every internal proxy load balancer forwarding rule?
9. VPC firewall ALLOWs egress yet the VM cannot reach the Internet: name two non-firewall causes.
10. Why should you not evaluate TCP 8080 connectivity using only ping?
11. A GKE node has a service account matching a rule's target SA. Does that rule automatically create a NetworkPolicy for individual Pods?
12. When logging is enabled on a rule but no logs appear, what should you check?
13. How do you view the list of firewall rules actually applied to a VM NIC?
14. When preparing to change a production rule, which traffic directions/flows must be tested?

### 16.2. Suggested Answers

1. **ALLOW** because 800 beats 900 within the same layer.
2. **DENY** because priorities are tied and both rules match.
3. **No**; deny at priority 500 is evaluated first.
4. Because the effective source set is an **OR/union** per rule behavior.
5. **No**; IAM/Cloud Run controls service invocation permissions.
6. **DENY** if the network policy decides and does not delegate further.
7. **No**; you must determine policy layer order first before comparing priorities within a layer.
8. **No**; implied actions depend on the target resource type.
9. Missing route, Cloud NAT/external IP, DNS, or unreachable/down endpoint.
10. Because ping uses **ICMP**, whereas the request requires testing **TCP 8080**.
11. **No**; VM service account selectors do not replace Pod network isolation.
12. The rule may not have matched/won, missing logs permissions, wrong network project, or logs not yet ingested.
13. Use **get-effective-firewalls** on the right NIC, and verify policy associations and traffic 5-tuple.
14. Test both **requests that must be allowed** and **requests that must be blocked**, including health checks and associated return paths.

## 17. Official References

These Google Cloud documentation pages should be used to verify current behavior/syntax:

- [VPC firewall rules — Concepts](https://docs.cloud.google.com/firewall/docs/firewalls)
- [Use VPC firewall rules — Console and gcloud](https://docs.cloud.google.com/firewall/docs/using-firewalls)
- [Evaluation order for firewall policies and rules](https://docs.cloud.google.com/firewall/docs/firewall-policies-rule-eval-order)
- [Firewall policies and rules overview](https://docs.cloud.google.com/firewall/docs/firewall-policies-overview)
- [Hierarchical firewall policies](https://docs.cloud.google.com/firewall/docs/firewall-policies)
- [Global network firewall policies](https://docs.cloud.google.com/firewall/docs/network-firewall-policies)
- [Network tags for Compute Engine VM](https://docs.cloud.google.com/vpc/docs/add-remove-network-tags)
- [Manage VPC firewall rules logging](https://docs.cloud.google.com/firewall/docs/manage-vpc-firewall-rules-logging)
- [Troubleshoot firewall policy logs](https://docs.cloud.google.com/firewall/docs/troubleshoot/firewall-policies-logs)
- [Load balancer firewall rules](https://docs.cloud.google.com/load-balancing/docs/firewall-rules)
- [Cloud Run ingress settings](https://docs.cloud.google.com/run/docs/securing/ingress)

Cloud NGFW configurations, policy types, CLI versions, target support, and logging costs are subject to change. In real deployments, verify with **effective firewalls** and the current settings of the organization/VPC in use.

---

**Connection to the CLOUD_PROVIDERS_GCP track:** VPC firewall rules are one network control layer for Compute Engine and GCP workloads with appropriate VPC access paths. A secure architecture also requires organization/IAM policies, VPC routes, DNS, Cloud VPN, GKE/Cloud Run security, and database permissions. When analyzing a request, **identify the flow → check the right policy layer → filter target/source/destination/port → compare priority → verify with effective rules and logs → test both allowed and blocked flows**. The results can be codified into IaC/CI/CD for consistent governance, reliability monitoring, and cost control over time.
