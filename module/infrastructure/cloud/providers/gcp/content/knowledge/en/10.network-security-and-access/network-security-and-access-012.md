# Hands-On: Protecting Workloads Without Public IPs

> **Chapter:** Network Security and Access  
> **Module:** CLOUD_PROVIDERS_GCP

A production application server does not need a public IP address to do its job. A VM running Java, a GKE node, or a database can use strictly **internal IPs**, receive admin access via **Identity-Aware Proxy (IAP)**, call Google APIs via **Private Google Access**, and when outbound Internet access is truly needed, exit through **Public Cloud NAT**. This design shrinks direct Internet exposure, though it does not replace firewalls, IAM, application authentication, egress controls, or observability.

In the **CLOUD_PROVIDERS_GCP** module, learners explore Google Cloud from project organization, IAM, and VPCs to Compute Engine, GKE, Cloud Run, storage, databases, release automation, reliability monitoring, and cost. This hands-on lab for the **Network Security and Access** chapter builds a Compute Engine VM without an external IPv4 address as the primary scenario, then examines how to apply the same principles to GKE, Cloud Run, and Cloud SQL.

**Learning outcomes:** After this lesson, you will be able to:

1. Explain what "no external IP" protects against and what it does not protect against.
2. Create a custom VPC/subnet and a Linux VM using internal IPv4 only.
3. Enable SSH administration via **IAP TCP forwarding** and **OS Login** with proper IAM, without opening SSH to `0.0.0.0/0`.
4. Use **Private Google Access** so a VM can reach supported Google APIs without an external IP.
5. Enable **Public Cloud NAT** only when workloads genuinely require outbound Internet connectivity, understanding that NAT does not open inbound paths.
6. Verify firewalls, routing, service accounts, metadata, logs, and organization policies.
7. Write verification and safe resource-cleanup checklists after practice.

## 1. Context and Threat Model

Suppose an enterprise operates an ordering system:

- **Compute Engine VM:** scheduled Java job pulling data and publishing messages; Internet users never need direct access.
- **Cloud Run:** API accepting requests along identity- and ingress-controlled paths.
- **GKE:** internal workers processing orders.
- **Cloud SQL:** stores transactional data; only authorized workloads may connect.
- **Cloud Storage / Secret Manager / Artifact Registry:** APIs/services used to fetch files, secrets, images, or packages.

The goal is reducing risks of **port scanning, SSH brute-forcing, unauthorized access, and data exfiltration** caused by unmanaged connectivity. Omitting a public IP on a VM is a solid defensive layer, but **not sufficient protection on its own**:

| Risk | What does lacking external IPv4 solve? | Controls still required |
| --- | --- | --- |
| Internet sends packets directly to VM's public IP | VM has no external IPv4 address to receive packets on that direct path | Ingress firewalls, IAP, minimizing listening services |
| Unauthorized access by insiders or peered VPCs | **Does not block** private connections over VPC/VPN/Interconnect | Firewalls, IAM, app authentication, segmentation |
| VM sends data out to the Internet | May lack direct outbound path; **with NAT or proxy it can still send out** | Egress rules, NAT policy, proxy/inspection, IAM, VPC Service Controls where fitting |
| App exposed via an external load balancer | A VM without a public IP **can still back an external LB** | Audit LB frontend, Cloud Armor, IAP for web, IAM/auth |
| Workload service account compromise | Not solved by private IPs | Least-privilege IAM, metadata security, credential hygiene |
| Package or application vulnerabilities | Not solved | Patch management, image scanning, logging, hardening |
| Loss of admin access from bad firewall edit | Without a public IP, no direct SSH fallback exists | IAP, OS Login roles, testing, and recovery runbooks |

### 1.1. Distinguishing "No Public IP," "Private Workload," and "Private Service"

- **No external IP on a VM**: the VM's network interface has no external IPv4 access config; also check IPv6 if using dual-stack.
- **Private workload**: beyond IP addressing, inspect **who can call it**, **over which path**, **how callers authenticate**, and **where it can send outbound traffic**.
- **Private service endpoint**: an internal address reachable from connected networks, such as an internal load balancer or Cloud SQL private IP. It is not automatically an ACL or IAM policy.
- **Public frontend with private backends**: many Internet applications run a public load balancer in front while VM/GKE backends **have no external IPs**. This is a valid architecture when an enterprise needs controlled public APIs.

**Principle:** "Leaving a public IP off a machine" is just one attribute of a network interface. Evaluate **all ingress, egress, identity, and data paths** before claiming a workload is protected.

## 2. Hands-On Architecture

We will create a custom VPC and subnet with **Private Google Access** enabled. The VM gets an internal IPv4 address and no external IPv4 address. Administrators get SSH access through IAP, and the VM can call supported Google APIs. Public NAT is **optional**, added only when needing to reach external websites or package repositories outside Google Cloud.

~~~mermaid
flowchart TD
    ADMIN["Engineer with IAM"] -->|"SSH over TLS/IAP"| IAP["IAP TCP forwarding"]
    IAP -->|"Source 35.235.240.0/20, TCP:22"| FW["VPC ingress firewall with target tag"]
    subgraph VPC["Custom VPC: private-lab-net"]
      FW --> VM["Java lab VM\nInternal IPv4 only\nNo external IPv4"]
      VM --> PGA["Private Google Access\non subnet"]
      VM --> NAT["Public Cloud NAT\nonly when egress is needed"]
    end
    PGA --> GOOGLE["Supported Google APIs\ne.g. Cloud Storage"]
    NAT --> INTERNET["Outbound Internet\ne.g. Debian repository"]
    PEER["Other machines in VPC or via VPN"] -. "Separately controlled by firewall" .-> VM
~~~

### 2.1. Path of Each Traffic Type

| Flow | Path | Key prerequisites |
| --- | --- | --- |
| Engineer SSHs to VM | Engineer laptop → IAP → VM internal IP:22 | IAP + OS Login/SSH IAM, firewall for IAP range |
| VM calls Google APIs | VM internal IP → VPC → Google APIs via Private Google Access | Enabled on subnet, matching DNS/routes/firewalls/API/IAM |
| VM fetches file from arbitrary Internet host | VM internal IP → default route → **Public Cloud NAT** → Internet | NAT on right subnet/region, route, and egress allow |
| VM → another VM in VPC | VPC subnet routes | Ingress/egress firewalls, OS/app |
| VM → on-premises | Route over HA VPN/Interconnect | Return path, BGP/static routes, firewalls on both sides |
| Internet → VM directly | **No VM public IP path** | Separate LB/proxy frontend could still exist; check config |
| Internet → Public Cloud NAT → VM | **Uninitiated inbound connections are unsupported** | NAT is for outbound egress and replies to allowed flows |

**Public NAT is not a public IP attached to each VM.** The NAT gateway holds external IP(s) to translate addresses for connections initiated by eligible workloads; it never lets Internet users SSH directly to a VM.

## 3. Prerequisites and Lab Safety Boundaries

### 3.1. Illustrative Resources

This lab uses the following placeholder values; replace them with authorized IDs and **never copy them to production**:

| Item | Lab value |
| --- | --- |
| Project | `LAB_PROJECT_ID` |
| Region | `asia-southeast1` (Singapore) |
| Zone | `asia-southeast1-a` |
| VPC | `private-lab-net` |
| Subnet | `private-lab-subnet` |
| IPv4 subnet range | `10.70.0.0/24` |
| VM | `private-app-vm` |
| Network tag | `iap-ssh` |
| Firewall rule for IAP | `allow-iap-ssh-private-lab` |
| Cloud Router (optional) | `private-lab-router` |
| Cloud NAT (optional) | `private-lab-nat` |

Only use `10.70.0.0/24` if it **does not overlap** existing subnets, peered networks, or on-premises ranges. A GCP project may enforce organization policies restricting VPC, firewall, VM, or NAT creation; escalate to administrators rather than bypassing policies.

### 3.2. Required IAM

| Task | Typically required roles/permissions |
| --- | --- |
| Create VPC, subnet, firewall | Network admin permissions, e.g., `roles/compute.networkAdmin` and `roles/compute.securityAdmin` per task |
| Create VM | Compute Engine instance create and subnet/disk usage permissions, often in `roles/compute.instanceAdmin.v1` or custom roles |
| SSH via IAP | `roles/iap.tunnelResourceAccessor` on the target scope, plus VM read permissions as needed |
| Linux login via OS Login | `roles/compute.osLogin`, or `roles/compute.osAdminLogin` if sudo is needed |
| Use service account attached to VM (if any) | `roles/iam.serviceAccountUser` on the service account and VM attach permissions |
| Manage NAT | Permissions to create/edit Cloud Router/NAT in the project/VPC |
| Read logs/metrics | Corresponding Logging/Monitoring roles |
| Enable APIs | `serviceusage.services.enable` and appropriate project permissions |

**Two separate layers:** IAP governs *who can open a TCP tunnel*, while OS Login or the VM's SSH mechanism governs *who can log into the OS*. Holding an IAP role is insufficient if the VM rejects SSH. Effective IAM also depends on organization settings, service account bindings, policies, and project configuration.

**Lab design for VM identity:** In the initial VM creation command, we pass `--no-service-account --no-scopes` because we aren't yet running an app calling Google APIs as the VM identity. When Cloud Storage access is needed later, create/attach a **dedicated service account** granted exact bucket permissions for testing. Avoid granting Editor/Owner to the default service account or storing JSON keys on the VM.

### 3.3. Cost and Infrastructure Mutations

The `create`, `update`, and `delete` commands below **mutate real resources**; they are shown for learning and must only be executed in an approved sandbox. Compute Engine VMs, persistent disks, Public Cloud NAT, NAT external IPs, Logging, and network egress **can incur charges**. If studying purely conceptually, skip resource creation and use the tables/diagrams to plan verification steps.

Before starting:

- Ensure a budget/budget alert and agreed lab timeframe are set.
- Use a test project only; never alter firewalls/routes of live applications.
- Verify VPC/subnet/VM/NAT names aren't already used by other workloads.
- Never run delete commands without confirming **the resource was created specifically for this lab**.
- Keep records of executed commands, outputs, and rollback steps.

## 4. Step 0 — Verify Project, APIs, and CLI Config

These commands are read-only:

~~~bash
gcloud version
gcloud auth list
gcloud config get-value project
gcloud projects describe LAB_PROJECT_ID

# Enabled APIs
gcloud services list --enabled --project=LAB_PROJECT_ID
~~~

Pass `--project` explicitly on every resource command. If needed APIs are missing, an authorized admin can enable them:

~~~bash
# Project-mutating operation; run only in an authorized lab
gcloud services enable compute.googleapis.com iap.googleapis.com \
  --project=LAB_PROJECT_ID
~~~

Beyond APIs, you need a valid billing account and Compute Engine quota. Avoid bulk-enabling APIs if the lab already has them or if you do not manage the project.

**Region/zone check:** `asia-southeast1-a` is a zone in region `asia-southeast1`; firewalls/VPCs are VPC-scoped, subnets/NAT are regional, and VMs are zonal. Keep region/zone consistent to avoid "VM not in subnet" or "NAT in wrong region" errors.

## 5. Step 1 — Create Custom VPC and Private Subnet

Create a **custom-mode VPC** for explicit control over subnets and CIDRs:

~~~bash
gcloud compute networks create private-lab-net \
  --subnet-mode=custom \
  --project=LAB_PROJECT_ID
~~~

Create the subnet with **Private Google Access** enabled:

~~~bash
gcloud compute networks subnets create private-lab-subnet \
  --network=private-lab-net \
  --region=asia-southeast1 \
  --range=10.70.0.0/24 \
  --enable-private-ip-google-access \
  --project=LAB_PROJECT_ID
~~~

Verify with **read-only** commands:

~~~bash
gcloud compute networks describe private-lab-net \
  --project=LAB_PROJECT_ID

gcloud compute networks subnets describe private-lab-subnet \
  --region=asia-southeast1 \
  --format="yaml(name,ipCidrRange,privateIpGoogleAccess,network)" \
  --project=LAB_PROJECT_ID

gcloud compute routes list \
  --project=LAB_PROJECT_ID \
  --filter="network:private-lab-net"
~~~

**Expected result:** VPC is in `CUSTOM` subnet mode; subnet has the chosen CIDR; `privateIpGoogleAccess: true`; subnet routes are listed. A standard custom VPC includes a default `0.0.0.0/0` route to the default Internet gateway. **The default route does not assign a public IP to a VM.**

### 5.1. Private Google Access Does Not Mean "Open Internet"

Private Google Access lets VMs **without external IPs** reach supported Google APIs/services at their IP addresses. It is a **subnet** setting, not an external IP or NAT gateway.

Prerequisites:

- VM NIC resides in the subnet with Private Google Access enabled.
- A route to Google API IP ranges points to **next hop default internet gateway** per Google Cloud design; despite "Internet" in the next-hop name, traffic to Google APIs under this mechanism stays **inside Google's network**.
- DNS resolves Google APIs accurately, especially when using private VIPs.
- Egress firewalls do not block the required IPs/ports.
- The service API is enabled and the **service account holds valid IAM** for authenticated data access.

Do not treat Private Google Access as access to arbitrary websites or package repositories. A VM may call the Cloud Storage API (when authorized) and still **fail to download files from an arbitrary Internet host** without NAT/proxy.

## 6. Step 2 — Restrict SSH Ingress to IAP Only

### 6.1. Default Ingress Firewall in a Custom VPC

In Google Cloud VPCs, standard **implied firewall rules** are:

- **Deny ingress** by default unless a higher-precedence allow rule applies.
- **Allow egress** by default unless a higher-precedence deny rule/policy applies.

This is the default VPC firewall behavior, **not proof** every VPC is safe: the `default` network often carries broader pre-created rules (like SSH/RDP). Hence this lab uses a fresh **custom VPC** and creates only an SSH rule from IAP.

### 6.2. Create an SSH Rule for the IAP Source Range

Per IAP TCP forwarding docs, the IPv4 range used by Google IAP is **`35.235.240.0/20`**. Permit TCP/22 only from this range to VMs tagged `iap-ssh`:

~~~bash
gcloud compute firewall-rules create allow-iap-ssh-private-lab \
  --network=private-lab-net \
  --direction=INGRESS \
  --priority=1000 \
  --action=ALLOW \
  --rules=tcp:22 \
  --source-ranges=35.235.240.0/20 \
  --target-tags=iap-ssh \
  --enable-logging \
  --project=LAB_PROJECT_ID
~~~

**Meaning of each field:**

| Field | Lab value | Purpose |
| --- | --- | --- |
| `--direction=INGRESS` | Traffic entering VM | Does not replace egress controls |
| `--source-ranges` | `35.235.240.0/20` | Allows connections only from IPv4 IAP TCP forwarding |
| `--rules=tcp:22` | SSH | Avoids opening all ports |
| `--target-tags=iap-ssh` | Lab VMs carrying that tag | Avoids affecting every VM in the VPC |
| `--enable-logging` | Logs matching connections | Useful for observability; may incur charges |

In production, consider **target service accounts, secure tags/firewall policies**, and IAM governing tag edits, since an account able to edit VM tags can alter which VMs a network-tag rule covers. Do not grant broad tag-edit permissions that allow bypassing rules.

**Never create** a `tcp:22` rule from `0.0.0.0/0` as a "temporary SSH fix." With IAP, check **IAM authorization** and the **firewall from IAP's range**, rather than exposing SSH publicly.

## 7. Step 3 — Create a VM Without an External IP

Create a Linux VM attached to the lab subnet:

~~~bash
# CREATE command; run only in an approved sandbox
gcloud compute instances create private-app-vm \
  --zone=asia-southeast1-a \
  --machine-type=e2-micro \
  --subnet=private-lab-subnet \
  --no-address \
  --image-family=debian-12 \
  --image-project=debian-cloud \
  --tags=iap-ssh \
  --metadata=enable-oslogin=TRUE \
  --no-service-account \
  --no-scopes \
  --project=LAB_PROJECT_ID
~~~

**Key security choices:**

- `--no-address`: no external **IPv4** address is attached on creation.
- `--subnet`: selects the private subnet explicitly instead of relying on defaults.
- `--metadata=enable-oslogin=TRUE`: enables **OS Login** so SSH logins are governed by IAM. Project/org policies may also apply.
- `--no-service-account --no-scopes`: omits a Google API identity for the networking-only lab; when authenticated Google API calls are needed, attach a least-privilege service account.
- `--tags=iap-ssh`: places the VM under the IAP SSH firewall rule.
- Debian 12 and `e2-micro` are illustrative; verify zone support, quotas, pricing, and organizational OS standards.

**Do not treat** `--no-address` as a blanket IPv6 control. This lab uses an IPv4-only subnet. In dual-stack setups, inspect external IPv6 and all network interfaces so no public paths are overlooked.

### 7.1. Verify Absence of External IP

~~~bash
gcloud compute instances describe private-app-vm \
  --zone=asia-southeast1-a \
  --format="yaml(name,status,networkInterfaces,metadata.items)" \
  --project=LAB_PROJECT_ID

gcloud compute instances list \
  --filter="name=private-app-vm" \
  --format="table(name,zone,networkInterfaces[0].networkIP,networkInterfaces[0].accessConfigs[0].natIP)" \
  --project=LAB_PROJECT_ID
~~~

**Expected result:** Internal IPv4 exists inside `10.70.0.0/24`; no external NAT IP appears in the interface/access config. If the compact table is hard to read, inspect full `networkInterfaces` YAML/JSON to separate internal IPv4, external IPv4, and IPv6.

### 7.2. SSH via IAP and OS Login

The operator needs **IAP-secured Tunnel User** and **OS Login**/OS Admin Login as appropriate. Some CLI flows and Compute Engine management operations also require instance read/admin permissions or Service Account User if the VM carries a service account. Inspect IAM errors and request exact resource roles rather than Owner.

~~~bash
# Initiates SSH connection without using an external IP
gcloud compute ssh private-app-vm \
  --zone=asia-southeast1-a \
  --tunnel-through-iap \
  --project=LAB_PROJECT_ID
~~~

**Path:** engineer's machine → encrypted IAP channel → VM internal IP:22 → SSH service in guest OS. IAP authenticates **who opens the tunnel**; Linux OS Login/SSH authenticates **who logs into the OS**. One succeeding does not guarantee the other succeeds.

Inside the VM, you can check:

~~~bash
hostname
ip -4 addr show
ip route
whoami
~~~

In labs, **never** print credentials, metadata server access tokens, or private keys to the terminal and paste them into docs. Once logged in, operate with least privilege and invoke `sudo` only when the exercise genuinely requires it.

### 7.3. How Does IAP Connect Without an External IP?

IAP TCP forwarding uses Google's infrastructure as an authenticated gateway connecting to the VM's **internal IP** from the firewall-permitted IAP source range. This **does not require** the VM to have an external IP or Public NAT. If the VPC denies ingress from `35.235.240.0/20` or IAM is insufficient, SSH still fails.

If an organization already operates Cloud VPN or Interconnect, engineers can reach internal VMs over approved private links instead of IAP. Still verify IAM, VPC firewalls, guest OS, and corporate policies—a VPN does not grant SSH permissions.

## 8. Step 4 — Verify Private Google Access Before Adding NAT

After SSHing into the VM, run read-only network checks:

~~~bash
# Check VM internal IP
ip -4 addr show

# Check DNS resolution to Google service
getent ahostsv4 storage.googleapis.com

# Test HTTPS connectivity; HTTP 4xx still proves network reachability
curl -I --connect-timeout 8 https://storage.googleapis.com

# Test a public Internet endpoint outside Google APIs
curl -I --connect-timeout 8 https://example.com
~~~

**Interpreting results:**

- `storage.googleapis.com` may return HTTP 400/403 depending on the request and auth; that differs completely from a DNS failure, timeout, or TLS handshake failure.
- When Private Google Access, DNS, routes, and firewalls are aligned, the VM reaches supported Google APIs **without NAT**; reading private buckets still requires a service account and IAM.
- Before adding NAT, reaching arbitrary Internet sites from an internal-IPv4-only VM typically **fails**, even though the VPC has a default route.
- Internet results may differ if your organization already configured a proxy, Cloud NAT, Private Service Connect, gateway, or custom route on the subnet. Always inspect the live architecture rather than assuming a timeout.

### 8.1. Check Metadata Server Without Exposing Tokens

A VM can query the internal metadata server for basic instance attributes:

~~~bash
curl -sS \
  -H "Metadata-Flavor: Google" \
  http://metadata.google.internal/computeMetadata/v1/instance/name
~~~

**Never query and publicly expose metadata access tokens**, SSH keys, sensitive info, or configs containing secrets. The metadata server uses a special local link; reaching metadata **is not** proof the VM has Internet access.

### 8.2. Private Google Access and IAM Are Independent Prerequisites

A VM without a service account like in this lab can **test HTTPS connectivity** to an API, but cannot invoke authenticated Google API operations. For an optional extension:

1. Create a dedicated service account for the VM via the project's IAM workflow.
2. Grant only the needed role, e.g., `roles/storage.objectViewer` **on the exact test bucket**.
3. Attach the service account to the VM via an approved process with suitable OAuth scopes (IAM still governs access).
4. Use a client library/CLI to read **one non-sensitive test object**.
5. Revoke permissions after the lab if no longer needed.

Never download service account JSON keys to "fix" missing permissions when attached service accounts/metadata identity are supported.

## 9. Step 5 — Public Cloud NAT for Outbound Internet (Optional)

A VM without external IPv4 may still need Debian package updates, Maven dependencies, or calls to a third-party endpoint. **Public Cloud NAT** is a common outbound solution that keeps the "private VM" design intact.

### 9.1. When Should You Add Public NAT?

| Need | Is Public NAT needed? | Notes |
| --- | --- | --- |
| Admin SSH via IAP | **No** | IAP TCP connects to VM's internal IP |
| Accessing Google APIs with valid Private Google Access | **Not necessarily** | Check API, DNS, routes, and IAM |
| Reaching another private VM in the same VPC | **No** | Uses subnet routes and firewalls |
| Calling a third-party public API | **Possibly** | Approved Public NAT/proxy/egress gateway |
| Updating OS from non-Google mirrors | **Possibly** | Check package mirror policies, proxy, or NAT |
| Receiving unsolicited SSH from the Internet | **No** | Public NAT provides no inbound public endpoint |
| Serving a public API via an external Load Balancer | **Not just for the LB** | Inbound traffic enters via LB frontend, not outbound NAT |

### 9.2. Create Cloud Router and NAT

**The following commands create billable resources.** Run only after the team agrees to provide Internet egress for the lab subnet:

~~~bash
gcloud compute routers create private-lab-router \
  --network=private-lab-net \
  --region=asia-southeast1 \
  --project=LAB_PROJECT_ID

gcloud compute routers nats create private-lab-nat \
  --router=private-lab-router \
  --region=asia-southeast1 \
  --nat-custom-subnet-ip-ranges=private-lab-subnet \
  --auto-allocate-nat-external-ips \
  --project=LAB_PROJECT_ID
~~~

This configuration selects **only the primary IPv4 range of one subnet** in the region, rather than enabling NAT for every subnet in the project. In real deployments, inspect GKE secondary IP ranges, Cloud Run Direct VPC egress, port allocation, NAT IP pools, and capacity before scoping NAT.

**Cloud Router is a control-plane resource managing NAT configuration**, not a packet-forwarding VM and does not require BGP peers for Public NAT. Public NAT is distributed Google Cloud infrastructure; packets do not traverse a Cloud Router VM.

### 9.3. Verify NAT and Connectivity

~~~bash
# Describe Public NAT config
gcloud compute routers nats describe private-lab-nat \
  --router=private-lab-router \
  --region=asia-southeast1 \
  --project=LAB_PROJECT_ID

# Inspect NAT status and active mappings
gcloud compute routers get-nat-mapping-info private-lab-router \
  --region=asia-southeast1 \
  --project=LAB_PROJECT_ID
~~~

Then SSH into the VM via IAP and test:

~~~bash
curl -I --connect-timeout 8 https://example.com
~~~

If this succeeds, outbound Internet connectivity is working. Ensure a proper route exists (typically `0.0.0.0/0` to default Internet gateway), egress firewalls allow it, NAT covers the right source IP/subnet/region, and NAT IPs have sufficient ports. If an egress deny-all rule is active, adding NAT **does not automatically open** firewall rules.

**Do not enter the NAT IP into the VM's access config.** NAT external IPs belong to the NAT gateway and differ from external IPs attached to a VM NIC. Re-check the VM's `networkInterfaces`: the VM still has no external IP even with NAT active.

### 9.4. Public NAT Is Not a Destination-Filtering Control

A NAT gateway performs **address translation** when routes and firewalls permit outbound connections; it is not a URL allowlist. If a VM lacks an external IP yet has allow-all egress and NAT to the Internet, malware on the VM can still call public endpoints. To curb exfiltration, implement **egress controls**, proxies/secure web gateways, DNS policies, and IAM aligned with requirements rather than assuming "adding NAT makes it safe."

## 10. Controlling Egress: More Than Just "No External IP"

### 10.1. Why Can't You Rely Solely on Cloud NAT?

Cloud NAT translates addresses when workloads connect to eligible destinations. If a VPC retains its **implied allow egress** rule, adding NAT can make **the entire public Internet** reachable outbound. In production, determine:

- Which **destination IPs/ports** may workloads call?
- Can Google APIs traverse **Private Google Access/PSC** without arbitrary Internet access?
- Can package dependencies be fetched via internal mirrors/corporate proxies?
- Are static NAT egress IPs needed for partner allowlisting?
- Which sensitive data (metadata, secrets, payloads, URLs) must test commands avoid exposing?
- Who holds permissions to edit firewalls, tags, Cloud Router, and NAT?
- Can anomalous outbound flows to unfamiliar destinations be detected via logs/monitoring?

**Important:** VPC firewall rules operate mainly on network attributes like IP, protocol, and port; they **do not provide HTTP-layer domain/URL filtering** like a secure web proxy. Allowing TCP/443 to `0.0.0.0/0` remains very broad.

### 10.2. Egress Allowlist: Rule Priority Order

If an organization applies **deny-all egress** to a VM group, it must add **specific higher-priority allow rules** (lower priority numbers) for mandatory flows. Conceptual example:

| Egress rule | Priority | Destination | Protocol | Outcome |
| --- | ---: | --- | --- | --- |
| Allow to approved Google APIs | 900 | Designed IP/VIP ranges | TCP/443 | Permits matching connections |
| Allow internal DB connectivity | 900 | Specific private DB range | TCP/5432 | Permits per business requirement |
| Deny all other outbound | 1000 | `0.0.0.0/0` | All | Blocks unapproved flows |

**This is a conceptual policy table, not a ready-to-run script.** Before creating live rules, check DNS traffic, metadata server, monitoring agents, patching, certificate retrieval, LB health, logging, org-level policies, and mandatory dependencies. A misapplied deny-all can prevent workloads from booting or recovering.

When using Private Google Access with `private.googleapis.com` or `restricted.googleapis.com`, destination IPs and DNS mappings must match Google's guides; never guess an IP to place in a rule. For Zero Trust at URL/destination level or DLP controls, adopt an organization-approved complementary architecture.

### 10.3. VPC Firewalls, Hierarchical Firewalls, and IAM

Distinguish clearly:

1. **VPC firewall rules**: govern ingress/egress on VM network interfaces by source, destination, protocol/port, and target.
2. **Hierarchical firewall policies / network firewall policies**: inherited from organization/folder or applied at network scope; check evaluation order and centrally managed rules.
3. **IAM**: governs *who can create/edit resources* or *who can invoke Google APIs*; IAM never replaces network firewalls for arbitrary TCP connections.
4. **OS/app authentication**: e.g., OS Login SSH, DB credentials/IAM DB auth, OAuth/JWT for APIs.
5. **VPC Service Controls**: protects API boundaries for supported Google managed services; not a general firewall for arbitrary Internet IPs.

During an incident, a project's firewall allow rule can be blocked by a **higher-layer policy**. Never add broader rules blindly before understanding active policy precedence.

### 10.4. Organization Policy Restricting VM External IPs

Google Cloud provides the organization policy constraint:

~~~text
constraints/compute.vmExternalIpAccess
~~~

This restricts attaching external IPs to VMs within governed scopes. It helps **prevent future resource misconfigurations**, with important caveats:

- It does not automatically strip external IPs from VMs created before enforcement.
- It applies to VM resources in the governed project/org scope and can also affect GKE nodes, managed instance groups, or VM-backed services in that project.
- Rolling it out without testing autoscaling and autohealing can prevent MIGs/GKE from launching new instances.
- In Shared VPC, setting the constraint on the host project **does not automatically enforce it on VMs in service projects**.
- You still must govern load balancers, external IPv6, other products' public endpoints, and IAM.

Design this policy with org/security teams, test thoroughly, and prepare rollback. **Never toggle it broadly in a shared lab** where it could impact unrelated projects.

## 11. Private Access Paths to Google Cloud Services

Not every product with "private" in its name uses the same mechanism. Distinguish **accessing Google APIs** from **accessing a service with a private IP**.

| Mechanism | Destination | Commonly used with | Key prerequisites |
| --- | --- | --- | --- |
| **Private Google Access (PGA)** | Supported Google API/service addresses on Google infrastructure | VMs without external IPs calling Cloud Storage, Secret Manager, certain APIs | Subnet setting, DNS/routes/firewalls, IAM |
| **Private Service Connect (PSC) for Google APIs** | Endpoint with an **internal IP** inside the VPC pointing to supported API bundles | Controlling API access through a VPC endpoint | Endpoint/forwarding rule, DNS, `all-apis`/`vpc-sc` bundle, IAM |
| **Private services access (PSA)** | Managed services running in a producer network peered via dedicated mechanism | Certain Cloud SQL private IP and managed service setups | Allocated IP range, service networking connection, IAM |
| **PSC to managed service** | Private endpoint reaching a supported producer service | Cloud SQL PSC, services published via PSC | Service attachment/endpoint, DNS, permissions, service config |
| **Cloud VPN / Interconnect** | Private IPs in on-premises/hybrid networks | Internal DB/ERP, data systems | Bidirectional routes, BGP/tunnels/circuits, firewalls |
| **Public Cloud NAT** | Internet destinations via NAT IP | OS updates, third-party APIs | Right subnet/region, route, egress allow |

A VM **without an external IP** can use several mechanisms in this table simultaneously depending on **destination address**. One flow using PGA does not mean another flow to Cloud SQL's private IP uses PGA.

### 11.1. Google APIs with Default Domain, Private, and Restricted VIPs

Google provides multiple ways to reach `googleapis.com`. Two common VIPs in private architectures:

| Name | IPv4 VIP range | Meaning |
| --- | --- | --- |
| `private.googleapis.com` | `199.36.153.8/30` | Reaches most supported Google APIs/services, including services without VPC Service Controls support |
| `restricted.googleapis.com` | `199.36.153.4/30` | Reaches only APIs/services supporting VPC Service Controls |

Using these VIPs requires **DNS configuration** mapping target domains, **routes** to those Google API ranges, and matching **egress firewalls** per documentation. Enabling PGA on a subnet **does not automatically create DNS records** for these two VIPs.

Some services use distinct domains such as `pkg.dev`, `*.run.app`, or Artifact Registry and may require extra DNS records depending on access patterns. Both VIPs support specific protocols/endpoints under documented conditions—do not treat them as a general Internet substitute for arbitrary websites. Notably, `restricted.googleapis.com` does not expose every Google API, so misapplying it can break applications.

**Routing to Google APIs via PGA requires next hop default internet gateway**, yet packets for supported services **do not leave for the public Internet**. Check routes and firewalls carefully when authoring custom egress policies.

### 11.2. Service Account IAM Is an Independent Control Point

Example: a Java VM needs to read an object from Cloud Storage:

~~~mermaid
flowchart LR
    APP["Java app on VM\nno external IP"] --> NET["PGA/PSC and network policy"]
    NET --> API["Cloud Storage API"]
    ID["Attached service account"] -. "Token via metadata server" .-> APP
    API --> IAM["IAM checks bucket/object permissions"]
    IAM --> OBJ["Object read permitted"]
~~~

Having network reachability to the API **does not** grant permission to read objects. If the VM runs with an overly broad service account, data remains exposed if the app is exploited. Grant only `roles/storage.objectViewer` or narrower scoped roles on the exact resource; apply IAM Conditions, VPC Service Controls, and data policies as needed.

### 11.3. Cloud SQL Private IP and Managed Services

Cloud SQL supports private connectivity, yet connecting via **private IP** uses **Private Services Access** or **Private Service Connect** depending on configuration—**not** standard Private Google Access.

Check separately:

- Does the Cloud SQL instance still have a **public IPv4** address? An instance with a private IP can still keep a public IP if configured to allow it.
- Do application VMs/GKE/Cloud Run have a valid network path and DNS to the private endpoint?
- Are DB users/IAM DB auth, TLS, secrets, and network policies configured properly?
- Cloud SQL connectors/proxies can be used in supported setups, but **never assume** a connector magically bypasses private VPC routing if the client lacks VPC connectivity.
- Are PSC/private services access permitted across Shared VPC and VPC peering per design?

To restrict Cloud SQL public IPs organization-wide, Google provides dedicated **organization policies** separate from `compute.vmExternalIpAccess`, such as `constraints/sql.restrictPublicIp`. Never assume Compute Engine constraints apply to managed databases.

## 12. Extending Principles to GKE and Cloud Run

### 12.1. GKE: Private Nodes and Cluster Control

With **GKE private nodes**, node VMs hold internal IPs and no external IPs per config. However, GKE design also requires verifying:

- **Control plane endpoint:** may use DNS-based access or private endpoints depending on cluster type/mode; private nodes **do not prove the control plane is internal-only**.
- **Node ↔ Google APIs/Artifact Registry:** requires Private Google Access, Cloud NAT, or appropriate private connectivity.
- **Node/pod egress:** inspect IP alias ranges, NAT coverage across primary/secondary ranges, Kubernetes NetworkPolicy where supported, and VPC firewalls.
- **Services ingress:** GKE can still provision an external load balancer for a Service/Ingress even when nodes have no external IPs.
- **Identity:** Workload Identity Federation for GKE (if used) lets pods obtain scoped identities without JSON keys; keep IAM tightly scoped per workload.
- **Control plane to nodes, health checks, and management:** avoid blind deny-all rules across entire subnets or node tags.

Thus: **private GKE nodes ≠ private GKE cluster endpoint ≠ no public Services**. Verify all three independently.

Suggested read-only commands:

~~~bash
gcloud container clusters list --project=PROJECT_ID

gcloud container clusters describe CLUSTER_NAME \
  --location=CLUSTER_LOCATION \
  --project=PROJECT_ID \
  --format="yaml(privateClusterConfig,networkConfig,masterAuthorizedNetworksConfig,endpoint)"
~~~

Exact fields vary across GKE Standard/Autopilot, creation modes, and API versions. Always inspect live endpoint settings in Console rather than relying on a single legacy attribute.

### 12.2. Cloud Run: No VM Public IP Does Not Mean a Private Endpoint

Cloud Run is serverless, so users do not directly manage a VM NIC with a public IP like Compute Engine. Nevertheless, a **Cloud Run service defaults to having a `run.app` endpoint and ingress permitting Internet traffic**, while IAM authentication still blocks unauthenticated calls unless opened.

To make a service **internal**:

- Set **ingress = internal** to allow only sources Cloud Run considers internal.
- Or **internal and Cloud Load Balancing** when routing through a public load balancer protected by Cloud Armor/IAP.
- Enforce **Invoker IAM** / require authentication; changing ingress does not replace authentication.
- Optionally **disable the default `run.app` URL** if your architecture and integrations do not depend on it. Disabling the default URL can impact Cloud Scheduler, Eventarc, Pub/Sub, and other triggers.
- Configure **outbound VPC connectivity** separately: Direct VPC egress or a supported connector to reach DBs/private VPC resources.

Example **updating an existing service** (run only when authorized):

~~~bash
# Updates ingress setting; does not create a new service
gcloud run services update SERVICE_NAME \
  --region=REGION \
  --ingress=internal \
  --project=PROJECT_ID
~~~

An `internal`-ingress service still requires IAM and may require VPC setup so internal clients can reach it. **Never pass `--allow-unauthenticated`** in production labs just to "fix" a 403 without checking caller identity.

If Cloud Run needs Internet egress **via a VPC's Public NAT** with **Direct VPC egress**, documentation requires `all-traffic` routing and NAT covering the source subnet. `private-ranges-only` does not route general Internet traffic through VPC NAT. An example config shape:

~~~text
Cloud Run egress (Direct VPC):
  VPC network: private-lab-net
  Subnet:       private-lab-subnet (matching region)
  Egress:       all-traffic
  NAT:          matching subnet and endpoint capacity
  Firewall:     allow only genuinely needed destinations
~~~

Do not confuse **ingress controls** (who may call Cloud Run) with **egress controls** (which targets Cloud Run may call).

### 12.3. Other Public Resources May Still Sit in Front

An architecture might look like:

~~~text
Internet
   ↓
External Application Load Balancer (public frontend)
   ↓
VM/GKE/Cloud Run backend without external IPv4
   ↓
Cloud SQL private endpoint
~~~

This is **not** "a system with zero public entry points." It deliberately exposes a public frontend serving requests while protecting private backends with network rules, authentication, and web protection. How Cloud Armor, TLS certificates, CDN, IAP for HTTP(S), and load balancer health checks work depends on the frontend type.

**Never use Public Cloud NAT to publish a website.** NAT is for supported outbound connections; public ingress requires load balancers/proxies and appropriate application controls.

## 13. Monitoring, Verification, and Diagnostics

### 13.1. Read-Only Command Suite from Admin Workstation

~~~bash
# VM and network interfaces
gcloud compute instances describe private-app-vm \
  --zone=asia-southeast1-a \
  --format="json(networkInterfaces,serviceAccounts,metadata)" \
  --project=LAB_PROJECT_ID

# Does the subnet have Private Google Access enabled?
gcloud compute networks subnets describe private-lab-subnet \
  --region=asia-southeast1 \
  --format="value(privateIpGoogleAccess)" \
  --project=LAB_PROJECT_ID

# Lab-related firewall rules
gcloud compute firewall-rules list \
  --filter="network:private-lab-net" \
  --project=LAB_PROJECT_ID

# VPC routes
gcloud compute routes list \
  --filter="network:private-lab-net" \
  --project=LAB_PROJECT_ID

# NAT (if created)
gcloud compute routers nats describe private-lab-nat \
  --router=private-lab-router \
  --region=asia-southeast1 \
  --project=LAB_PROJECT_ID
~~~

Because `firewall-rules list` does not show hierarchical firewall policies, inspect effective policies via Console or dedicated commands. Never conclude there is no deny when a command only lists classic VPC firewall rules.

### 13.2. Useful Observability Tools

| Tool | What it observes | Limits to keep in mind |
| --- | --- | --- |
| **VPC Flow Logs** | Flow metadata for supported subnets/endpoints | Sampled/aggregated; not full packet capture |
| **Firewall Rules Logging** | Connections matching rules with logging enabled | Logs only per supported rule and mechanism |
| **Cloud NAT Logs/Metrics** | NAT connections, errors/drops/port allocation per config | Logging may be off initially; log costs and volume limits |
| **Cloud Audit Logs** | Who modified networks/firewalls/VMs/Org Policies | Data access logging config and viewer permissions vary |
| **Network Intelligence Center – Connectivity Tests** | Configuration analysis of paths, firewalls, next hops | Separate API/IAM; does not replace every end-to-end check |
| **Cloud Monitoring** | VM uptime, CPU, NAT/network metrics, alerting | Needs proper metrics; dashboards do not protect resources |
| **OS Login / IAP audit data** | Recorded admin identities and access events | Check audit scope, retention, and logging policy |

At the start of the lab, the IAP firewall rule enabled logging. **Cloud NAT logging must be configured separately** if you want NAT logs; do not assume creating NAT logs every connection by default.

### 13.3. Troubleshooting Table

| Symptom | Likely cause | How to verify |
| --- | --- | --- |
| `gcloud compute ssh` reports `Permission denied` | Missing IAP, OS Login, or Compute Engine/service account role | Check active user, IAM policy, and OS Login metadata |
| SSH via IAP times out | Missing ingress firewall from `35.235.240.0/20`, sshd stopped, or VM unhealthy | Check firewall target tags, VM health, port 22, and IAP |
| SSH works when VM has public IP but fails when removed | Tool connected directly instead of using `--tunnel-through-iap` | Check IAP role/firewall and connection path |
| VM has an external IP despite expecting "private" | Created without `--no-address`, multiple NICs, or external IPv6 | Inspect all `networkInterfaces`/accessConfigs |
| `curl storage.googleapis.com` times out before NAT | PGA disabled, bad route/DNS/firewall, or unsupported Google API | Check `privateIpGoogleAccess`, DNS, and next hop |
| Google API returns 403 | Network works, yet IAM/token/bucket permissions failed | Check service account, OAuth scopes, and IAM |
| Package update from Internet fails | No NAT/proxy, bad route, DNS, or egress denied | Check NAT subnet/region, default route, logs, and proxy |
| NAT created yet Internet still times out | VM outside NAT source ranges, wrong region, port exhaustion, firewall | Inspect NAT config/mappings/logs, `0.0.0.0/0` route |
| VM still reaches Internet without external IP | NAT, proxy, or egress gateway is configured | Inspect outbound architecture; not necessarily an error |
| Private VM accessed from external app | External load balancer/proxy/VPN/Peering or open private firewall | Trace ingress frontend and live resources |
| Cloud SQL private IP unreachable | PSA/PSC misconfigured, route/firewall, DB auth, or DNS | Inspect Cloud SQL network config and IAM DB settings |
| Cloud Run reachable from Internet | `all` ingress or intentional public frontend; auth may differ | Check ingress and Invoker IAM, not container IP |
| GKE node cannot pull container images | NAT/PGA, `pkg.dev` DNS, registry IAM, node scopes, or policy | Check layer by layer: DNS, network, auth, repository |
| Logs show no flows | Logging disabled, sampling, another policy, or data lag | Verify Logging settings and corresponding metrics |

### 13.4. Troubleshoot Layer by Layer—Never Edit Configs Blindly

~~~mermaid
flowchart TD
    START["Private workload reports connection failure"] --> SRC["Identify source, destination, IP, protocol, port"]
    SRC --> ADDR{"Unintended external IP on VM?"}
    ADDR -- "Yes" --> FIX["Review requirements and modify safely"]
    ADDR -- "No" --> INOUT{"Ingress or egress?"}
    INOUT -- "Ingress SSH" --> IAP["Check IAP IAM + OS Login + TCP22 firewall"]
    INOUT -- "Google API" --> PGA["Check PGA, DNS, routes, IAM"]
    INOUT -- "Internet outbound" --> NAT["Check NAT source subnet/region, route, egress"]
    INOUT -- "Private service" --> PSC["Check private IP, PSA/PSC, DNS, app auth"]
    IAP --> FINAL["Re-test from right client and inspect logs"]
    PGA --> FINAL
    NAT --> FINAL
    PSC --> FINAL
    FIX --> FINAL
~~~

**Safety rule:** When an API returns `403`, never rush to open `0.0.0.0/0` in the firewall; the network may already work while IAM is missing. On timeout, never grant Owner; routing or firewalls are likely blocking. Keep network, authentication, authorization, and application layers distinct.

## 14. Gradable Lab Verification Table

After completing the lab, record actual observed results:

| Check | How to verify | Expected result |
| --- | --- | --- |
| VM has no external IPv4 | `gcloud compute instances describe` | Internal IPv4 present; `accessConfigs` has no external NAT IP |
| SSH not exposed directly to Internet | Firewall rules + VM interface | No public VM IP; no broad SSH allow rule |
| SSH via IAP | `gcloud compute ssh --tunnel-through-iap` | Only users with IAM + OS Login can sign in |
| PGA on subnet | `gcloud compute networks subnets describe` | `privateIpGoogleAccess=true` |
| Google API reachability | DNS + HTTPS to supported API | Network response received; auth depends on IAM |
| VM Internet access before NAT | `curl` public site | Typically blocked in custom VPC lab lacking egress |
| VM Internet access after NAT | Configure NAT + `curl` | Outbound succeeds if routes/firewalls allow |
| VM still lacks external IP after NAT | Describe `networkInterfaces` | External IP still absent on VM |
| Firewall rule scoped cleanly | Describe `allow-iap-ssh-private-lab` | IAP range source and lab tag target TCP:22 only |
| Least-privilege IAM | Review IAM grants | Neither tester nor VM holds Owner/Editor |
| Logs | Logs/Monitoring within enabled scope | Evidence of SSH/IAP and network troubleshooting |
| Resource cleanup | List VMs/VPCs/routers/NAT and check billing | Zero lab resources left; untouched other resources |

**Security test case:** A user lacking the IAP role attempting SSH must be rejected at the IAP layer even though the firewall permits the IAP source range. A user holding the IAP role without OS Login must still fail to log into Linux. This demonstrates **defense in depth**, not merely "hiding the IP address."

## 15. Cleaning Up After Practice

**Delete only resources matching exact names created by this lab and unused by anyone else.** The following commands are destructive; never run in production and never use wildcards.

Before deleting, verify:

~~~bash
gcloud compute instances list \
  --filter="name=private-app-vm" --project=LAB_PROJECT_ID

gcloud compute routers list \
  --filter="name=private-lab-router" --project=LAB_PROJECT_ID

gcloud compute networks list \
  --filter="name=private-lab-net" --project=LAB_PROJECT_ID
~~~

If you **created Public NAT** in the optional step, delete NAT before deleting Cloud Router:

~~~bash
gcloud compute routers nats delete private-lab-nat \
  --router=private-lab-router \
  --region=asia-southeast1 \
  --project=LAB_PROJECT_ID

gcloud compute routers delete private-lab-router \
  --region=asia-southeast1 \
  --project=LAB_PROJECT_ID
~~~

Delete the VM (check persistent disks, snapshots, reserved IPs, and backups before confirming):

~~~bash
gcloud compute instances delete private-app-vm \
  --zone=asia-southeast1-a \
  --project=LAB_PROJECT_ID
~~~

Once certain no VMs or resources remain using the firewall/subnet, delete the lab's rule, subnet, and VPC:

~~~bash
gcloud compute firewall-rules delete allow-iap-ssh-private-lab \
  --project=LAB_PROJECT_ID

gcloud compute networks subnets delete private-lab-subnet \
  --region=asia-southeast1 \
  --project=LAB_PROJECT_ID

gcloud compute networks delete private-lab-net \
  --project=LAB_PROJECT_ID
~~~

Delete commands prompt for confirmation. If you skipped NAT, **skip the NAT/router delete commands**. If any other resource now uses the lab network, **do not force deletion**; check ownership and contact the administrator.

**Check for lingering costs:** Deleting the VM does not guarantee all persistent disks, snapshots, logs, images, NAT reserved external IPs, or auxiliary services are gone. Use Billing Reports/Budgets and resource inventories to verify. Never delete the entire project if other work lives in it.

## 16. Extension Scenario: Company Needs a Public API Without Exposing Backends

A company deploys an ordering website:

~~~mermaid
flowchart LR
  U["Internet users"] --> ALB["External Application Load Balancer"]
  ALB --> WAF["Cloud Armor / IAP if applicable"]
  WAF --> API["Cloud Run or GKE backend\nno public IP on nodes"]
  API --> DB["Cloud SQL private endpoint"]
  API --> LOG["Cloud Logging/Monitoring"]
  DEV["Engineer"] --> IAP["IAP TCP forwarding"] --> VM["Compute Engine worker\nno external IP"]
  VM --> NAT["Public Cloud NAT for outbound when needed"]
~~~

The goal of this architecture is not **eliminating every public IP**: the app still exposes a public frontend serving customers. Rather, **backend workers/DBs** never need direct public exposure. Key boundaries:

1. **Public frontend**: TLS, authentication, DDoS/WAF protection, and closing backend bypass paths.
2. **Private workload network**: only authorized sources reach backends, with controlled routes and egress.
3. **Data plane**: private DB, proper IAM/credentials, and encryption.
4. **Management plane**: IAP/OS Login, least-privilege IAM roles, audit logs.
5. **Outbound**: PGA/PSC for Google APIs; approved NAT/proxy for Internet.
6. **Reliability**: health checks, retries, autoscaling, monitoring, and safe rollouts.
7. **Cost**: firewall logs, Cloud NAT, private endpoints, load balancers, egress, monitoring.

**Example engineering decision:** "Disable external IP on worker VMs" is a clear requirement, yet **is insufficient to prove data cannot leave the environment** if workers hold IAM permissions to read every bucket alongside unrestricted Internet egress. The solution must unite network policies, service identities, data permissions, logs, and change approvals.

## 17. Review Questions and Suggested Answers

1. **Can a VM without an external IP be accessed via SSH through IAP?** Yes, if IAP IAM, OS Login/SSH, and the firewall rule for the IAP source range are configured properly.
2. **Why not open TCP/22 from 0.0.0.0/0?** It widens the allowed network sources for connection attempts, violating exposure-reduction goals.
3. **Why is Private Google Access different from Cloud NAT?** PGA reaches supported Google APIs/services privately; NAT translates addresses for eligible outbound traffic, typically to the Internet.
4. **Does adding NAT give the VM a public IP?** No, the external IP sits on the NAT gateway, not on the VM NIC.
5. **Does NAT let Internet users SSH inward to a private VM?** No—unsolicited inbound connections not initiated by the workload are unsupported.
6. **Does PGA automatically grant IAM to read Cloud Storage?** No. Network reachability and resource authorization are two independent layers.
7. **Why can a cloud VM without an external IP still be compromised?** It may be reachable via private VPC/VPN/LB, hold an over-privileged service account, or run vulnerable software.
8. **Is Cloud Run automatically private because it has no VM public IP?** No; verify ingress settings, the `run.app` URL, load balancer frontends, and Invoker IAM.
9. **Do GKE private nodes mean a Service of type LoadBalancer cannot be public?** No; a public frontend can still be provisioned if configuration allows it.
10. **Does Cloud SQL private IP use Private Google Access?** Not through standard PGA; it requires PSA/PSC and service networking paths.
11. **Why isn't allow-all egress + Public NAT equivalent to Zero Trust?** Because workloads can still call arbitrary Internet destinations; destination policies and data access controls are needed.
12. **When a 403 occurs, should you add a firewall allow rule?** Usually not; 403 typically indicates IAM/auth rejection, whereas network blocks manifest separately.
13. **Are the IAP role and OS Login role interchangeable?** No; one authorizes the tunnel, the other authorizes OS login.
14. **Does an org constraint banning VM external IPs strip existing addresses?** Not retroactively per documentation; legacy resources must be remediated individually.
15. **During lab cleanup, should you delete the entire project?** No if other teams/resources share it; delete only verified lab resources.

## 18. Safety Checklist Before Production Adoption

- [ ] Classified workloads: internal-only, public frontend/private backend, or hybrid.
- [ ] Zero unintended external IPv4/IPv6/NICs; audited every interface.
- [ ] Audited public frontends, Cloud Run ingress, GKE Services/Ingress, and Cloud SQL public IP.
- [ ] IAP, OS Login, and admin IAM granted strictly to exact groups/users/resources.
- [ ] Ingress/egress firewalls and hierarchical policies follow least privilege.
- [ ] Private Google Access/PSC/PSA selected appropriately per Google API or managed service.
- [ ] Cloud NAT scoped solely to required subnets/regions/sources, never treated as a firewall.
- [ ] Service accounts hold least privilege; unnecessary JSON keys eliminated.
- [ ] Logging/monitoring, audit trails, and network/IAM change alerts configured.
- [ ] End-to-end tests from real sources/destinations verifying DNS, routes, firewalls, IAM, TLS, and app behavior.
- [ ] Safe patching plan established for private VMs lacking open Internet access.
- [ ] Budgeted for VMs, disks, NAT, logs, egress, and endpoints.
- [ ] Rollback plans and runbooks prepared in case IAP/NAT/Private Google Access fails.

## 19. Official Google Cloud Documentation

Verify these pages during real deployments, as endpoint types, IAM roles, CLI flags, IPv6 support, and security requirements evolve:

- [Connect to Linux VMs using IAP](https://docs.cloud.google.com/compute/docs/connect/ssh-using-iap) — SSH to VMs without external IPs.
- [Use IAP for TCP forwarding](https://docs.cloud.google.com/iap/docs/using-tcp-forwarding) — IAP source ranges, firewalls, IAM.
- [Configure OS Login](https://docs.cloud.google.com/compute/docs/oslogin/set-up-oslogin) — IAM and Linux login.
- [VPC firewall rules](https://docs.cloud.google.com/firewall/docs/firewalls) — implied rules, priorities, and scope.
- [Private Google Access overview](https://docs.cloud.google.com/vpc/docs/private-google-access) — prerequisites for private VMs reaching APIs.
- [Configure Private Google Access](https://docs.cloud.google.com/vpc/docs/configure-private-google-access) — subnets, DNS, routes, `private.googleapis.com`/`restricted.googleapis.com`.
- [Private access options for services](https://docs.cloud.google.com/vpc/docs/private-access-options) — PGA, PSC, private services access.
- [Public Cloud NAT overview](https://docs.cloud.google.com/nat/docs/public-nat) — outbound NAT and limitations.
- [Set up Public NAT](https://docs.cloud.google.com/nat/docs/set-up-manage-network-address-translation) — Cloud Router and NAT gateway.
- [Compute Engine: create VMs](https://docs.cloud.google.com/compute/docs/instances/create-start-instance) — private VMs and network interfaces.
- [Restrict VM external IP with organization policy](https://docs.cloud.google.com/compute/docs/ip-addresses/configure-static-external-ip-address#restrict_external_ip_addresses_to_specific_instances) — `compute.vmExternalIpAccess` constraint.
- [GKE private clusters](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/private-cluster-concept) — private nodes and control plane access.
- [Cloud Run ingress](https://docs.cloud.google.com/run/docs/securing/ingress) — internal vs. external ingress and default URL.
- [Cloud Run Direct VPC egress](https://docs.cloud.google.com/run/docs/configuring/vpc-direct-vpc) — all-traffic, private-ranges-only.
- [Cloud NAT interactions with Cloud Run](https://docs.cloud.google.com/nat/docs/nat-product-interactions) — NAT sources with Direct VPC egress.
- [Cloud SQL private IP](https://docs.cloud.google.com/sql/docs/mysql/configure-private-ip) — private connectivity for managed databases.
- [VPC Flow Logs](https://docs.cloud.google.com/vpc/docs/flow-logs) — network flow metadata.
- [Connectivity Tests](https://docs.cloud.google.com/network-intelligence-center/docs/connectivity-tests/concepts/overview) — path simulation and configuration checks.

**Core takeaway:** **A VM without an external IP is only the first layer of defense.** A genuinely protected workload requires **authenticated ingress (IAP or controlled frontends), minimal egress (controlled PGA/PSC/NAT), scoped IAM/service identities, appropriate firewalls, and observability**. Verify every flow by source–destination, permissions, and application state rather than treating the absence of a public IP as sole proof of security.
