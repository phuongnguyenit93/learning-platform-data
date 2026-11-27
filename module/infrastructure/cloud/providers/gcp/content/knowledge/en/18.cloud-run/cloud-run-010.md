# Direct VPC Egress and Serverless VPC Access in Cloud Run

> **Chapter:** Cloud Run  
> **Lesson:** Direct VPC egress and Serverless VPC Access  
> **Module:** CLOUD_PROVIDERS_GCP

In the **CLOUD_PROVIDERS_GCP** module, learners progress from project management, IAM, and VPCs to Compute Engine, GKE, Cloud Run, storage, and databases; the goal is to deploy services securely, automate releases, monitor reliability, and control cost. With **Cloud Run**, a Java HTTP API runs on serverless infrastructure yet sometimes needs to connect to a **Cloud SQL private IP**, Redis, internal VMs, or on-premises systems over VPN/Interconnect. Doing so requires selecting the right **egress (outbound traffic)** path.

Google Cloud provides two primary mechanisms for a Cloud Run service or job to reach a VPC: **Direct VPC egress** and **Serverless VPC Access connectors**. Both solve **connectivity from Cloud Run into a VPC**; neither exposes nor blocks Cloud Run's HTTP endpoint by itself. This lesson explains the architecture, deployment commands, security, cost, common pitfalls, and a real-world Java scenario. It prioritizes self-contained guidance with sandbox-ready examples without needlessly repeating foundational networking.

**Selection principle:** For Cloud Run services and jobs, Google Cloud recommends **Direct VPC egress** whenever requirements are met because no separate connector is needed. Choose **Serverless VPC Access** only when feature constraints, legacy network layouts, or operational needs make a connector a better fit.

## 1. Learning Outcomes

After this lesson, you can:

1. Distinguish **egress to a VPC** from **ingress to Cloud Run**, IAM, and application access permissions.
2. Explain the data flow of Direct VPC egress and Serverless VPC Access, along with service/job limitations.
3. Choose between `private-ranges-only` and `all-traffic`, and understand when **Cloud NAT** is needed.
4. Size subnets for Direct VPC (**at least /26**, with IP headroom for scaling/rolling revisions) and connectors (a **dedicated /28**).
5. Use `gcloud run deploy` to configure both options and read back service revisions, VPC settings, and connectors.
6. Integrate firewalls, IAM, DNS, Shared VPC, and Cloud SQL private connectivity.
7. Diagnose timeouts, permission errors, IP exhaustion, startup latency, and public egress failures.
8. Select the right option based on a Java API's **latency, scalability, reliability, and cost**.

## 2. Egress vs. Ingress: Defining the Right Problem

~~~mermaid
flowchart LR
    Client["Users / systems calling API"] -->|"Ingress + auth"| CR["Cloud Run Orders API"]
    CR -->|"Egress into VPC"| VPC["VPC app-vpc"]
    VPC --> DB["Cloud SQL private IP<br/>or internal VM/Redis"]
    VPC --> Hybrid["Cloud VPN/Interconnect<br/>on-premises"]
    CR -->|"Public egress if policy allows"| Public["External APIs / Google APIs"]
~~~

- **Ingress:** who can send HTTP requests to the Cloud Run URL? Controlled via `--ingress`, Invoker IAM, Load Balancers, IAP, or application policies.
- **Egress:** when the Java container initiates outbound connections to a DB, Redis, or another endpoint, which network path do packets take?
- **Cloud Run runtime service account:** which **Google APIs** the app is authorized to call; it **does not** automatically grant network reachability to private IPs.
- **Firewall/VPC routes:** which IP/port flows are permitted; they **do not** replace IAM or database authentication.

For **Cloud Run services and jobs**, Direct VPC is an **egress** configuration; it does not turn a container into a VM with a fixed inbound IP address. Certain other Cloud Run resource types (such as worker pools/instances) have specific Direct VPC ingress features, and you should **not** extrapolate those behaviors to standard HTTP services.

### 2.1. When Does Cloud Run Need VPC Egress?

| Target called from Java | Needs a VPC path? | Notes |
|---|---|---|
| Private IP VM in the same VPC | **Yes** | Needs routes/firewalls, service port, and proper DNS |
| Cloud SQL via **private IP** | **Yes** | Also requires Cloud SQL private networking setup and DB authentication |
| Memorystore/Redis private endpoint | Usually **yes** | Verify supported network and region |
| On-premises database via Cloud VPN/Interconnect | **Yes** | Needs bidirectional routes, firewalls, and hybrid DNS |
| Cloud Storage/Pub/Sub via standard Google APIs | **Not by default** | Google APIs can be reached over HTTPS via the default path; IAM still required |
| Partner public API | **Not by default** | If you must pin an outbound public IP, use VPC `all-traffic` + Cloud NAT/static NAT IP |
| Cloud Run receiving public requests | **Unrelated to egress** | Controlled by ingress, auth, and frontend |

**Key lesson:** do not configure a connector or Direct VPC simply because "a Cloud Run service ought to use a VPC." Route traffic through a VPC only when targeting private endpoints or enforcing explicit egress routing/controls.

## 3. Quick Comparison of Both Options

| Criterion | **Direct VPC egress** | **Serverless VPC Access** |
|---|---|---|
| Path | Cloud Run attaches directly to a VPC/subnet | Cloud Run routes through a **connector** into the VPC |
| Intermediary resource | No separate connector | Connector made of managed instances |
| Default choice for new Cloud Run services/jobs | **Preferred when suitable** | Choose when Direct does not meet requirements |
| Address sizing | Subnet **/26 or larger**, with scaling buffer | Dedicated **/28 range/subnet**, not shared with other resources |
| Scaling behavior | Scales with Cloud Run; subnet must have enough IPs | Connector has min/max instances and finite throughput |
| Baseline cost when Cloud Run scales to 0 | No always-running connector fee | Connector enforces **minimum instances**, so baseline cost persists |
| Firewall controls | Can attach **network tags on revisions**; subnet-scoped IPs | Uses /28 CIDR or appropriate connector tags/rules |
| Cold-start latency | May incur slight network setup delay at instance start | Connector keeps warm capacity, occasionally helping startup |
| `private-ranges-only` / `all-traffic` | Both supported | Both supported |
| Cloud Run service/job inbound via VPC | **No** | **No** |

**Core trade-off:** Direct is simpler and typically saves operational cost; a connector adds an intermediary resource and baseline cost, yet may fit specific connectivity or cold-start needs. Neither option replaces HTTPS, IAM, firewalls, or database authentication.

## 4. How `private-ranges-only` and `all-traffic` Routing Work

Both VPC methods use the same egress routing modes:

~~~mermaid
flowchart TD
    Java["Java service sends TCP/HTTPS request"] --> Mode{"Cloud Run VPC egress mode"}
    Mode -->|"private-ranges-only"| Private{"Target in internal/private range?"}
    Private -->|"Yes"| VPCA["VPC/subnet or connector"]
    Private -->|"No"| Default["Default Cloud Run egress path"]
    Mode -->|"all-traffic"| VPCB["All traffic sent to VPC"]
    VPCB --> Internal["Internal IPs, VPN, or peering"]
    VPCB --> Public{"Public Internet target?"}
    Public --> NAT["Cloud NAT / routes / firewalls<br/>if public egress is needed"]
    VPCA --> Internal
~~~

### 4.1. `private-ranges-only`

Traffic destined for **addresses classified by Google Cloud as internal/private** traverses the VPC. Traffic to public destinations follows the default egress path. Suitable when a Java API calls a private database while still calling Google APIs or normal public services.

**Do not misunderstand:** a hostname with an internal-sounding suffix whose DNS resolves to a public IP will not automatically traverse the VPC. Check the **resolved IP**, routes, and target ranges. For prefixes not classified as recognized private/internal ranges, traffic may require `all-traffic`.

### 4.2. `all-traffic`

All outbound traffic from Cloud Run routes through the VPC, including requests to public IPs. Choose this when the organization wants to:

- Enforce firewall rules and network inspection on all egress.
- Use **Cloud NAT** with a **static external IP** for partner allowlisting.
- Route all outbound traffic through private network infrastructure per approved architecture.

**Important:** When switching to `all-traffic`, if the VPC **has no path to the public Internet**, HTTP requests to external APIs will time out. You typically need **Cloud NAT** (plus appropriate routes/firewalls) or a dedicated egress path. Accessing Google APIs must also account for **Private Google Access**, Private Service Connect, or NAT per design—never assume enabling VPC egress automatically grants Internet access.

| Goal | Suggested option |
|---|---|
| Java → Cloud SQL private IP, plus Pub/Sub/Cloud Storage via standard APIs | `private-ranges-only` |
| Java → private VM, no requirement to control public egress | `private-ranges-only` |
| Partner requires allowlisting **one external IP** | `all-traffic` + Cloud NAT with managed static external IP |
| All outbound traffic must pass through firewalls/proxies | `all-traffic` with complete egress infrastructure |

## 5. Direct VPC Egress: Architecture and Subnet Sizing

~~~mermaid
flowchart LR
    CR["Cloud Run revision<br/>Orders API"] -->|"Direct VPC egress"| SUB["Subnet cr-egress-subnet<br/>10.42.0.0/24"]
    SUB --> VM["Backend VM private IP"]
    SUB --> DB["Cloud SQL private connection"]
    SUB --> VPN["VPN/Interconnect"]
    SUB --> NAT["Cloud NAT<br/>only if public traffic traverses VPC"]
~~~

Cloud Run receives **ephemeral IPv4 addresses from the subnet**; addresses are not pinned per instance. The subnet must reside in the **same region** as the Cloud Run service/job. Multiple services/jobs can share one subnet if sufficient IPs exist.

### 5.1. IP Allocation Traps During Scaling

Per current guidance:

- A Direct VPC egress subnet must have an IPv4 range of **/26 or larger** (for example, `/24` has more addresses than `/26`).
- Cloud Run allocates addresses in **/28 blocks** to accelerate scaling.
- For a **service**, steady state can consume roughly **2× the number of container instances**. After scale-down, IPs can remain held for **up to ~20 minutes**.
- During a **rolling update** with both old and new revisions running concurrently, IP demand spikes sharply. Plan for at least **2× total coexisting instances**, plus buffer.
- For a **job**, each task has IP demand and post-completion retention; account for **concurrent tasks** and overlapping executions.
- After detaching a service, it can take **1–2 hours** for Cloud Run to release all addresses before the subnet can be deleted.

**Sizing example:** an old revision up to 40 instances and a new revision up to 40 instances overlap. Applying a 2× buffer requires at least `(40 + 40) × 2 = 160` addresses, before counting any other resources sharing the subnet. A **/24** subnet is usually a far safer starting point than `/26` here. Never put an ephemeral instance-assigned IP into a long-lived allowlist.

### 5.2. Inspecting the Subnet and VPC

Assume the network team created:

~~~text
Project:  PROJECT_ID
Region:   asia-southeast1
VPC:      app-vpc
Subnet:   cr-egress-subnet (10.42.0.0/24)
Backend:  private IP in a valid routed subnet
Image:    asia-southeast1-docker.pkg.dev/PROJECT_ID/java-images/orders-api:1.0.0
~~~

The following commands are read-only:

~~~bash
gcloud compute networks describe app-vpc --project=PROJECT_ID

gcloud compute networks subnets describe cr-egress-subnet \
  --project=PROJECT_ID \
  --region=asia-southeast1

gcloud run services list \
  --project=PROJECT_ID \
  --region=asia-southeast1
~~~

With **Shared VPC**, the subnet may live in a **host project** separate from the service project; grant **Compute Network User** or equivalent permissions on the subnet to the required Cloud Run/service agent identities per documentation. Never switch VPC host projects or grant Owner just to bypass a deploy error.

## 6. Practice A — Deploying Cloud Run with Direct VPC Egress

**Prerequisites:** Cloud Run API/Compute API enabled, Java image available, VPC and subnet created, deployer holds required IAM, and private backend is running. The command below **modifies a Cloud Run service** and can incur charges. Do not run against production without approval.

~~~bash
gcloud run deploy orders-api \
  --project=PROJECT_ID \
  --region=asia-southeast1 \
  --image=asia-southeast1-docker.pkg.dev/PROJECT_ID/java-images/orders-api:1.0.0 \
  --network=app-vpc \
  --subnet=cr-egress-subnet \
  --network-tags=cr-orders-egress \
  --vpc-egress=private-ranges-only \
  --no-allow-unauthenticated
~~~

**Meaning:**

- `--network` and `--subnet`: attach **directly** to the VPC/subnet in that region.
- `--network-tags`: attaches tags to the **revision** for tag-based egress firewall rules, where supported by the firewall tier.
- `--vpc-egress=private-ranges-only`: only internal traffic routes through the VPC.
- `--no-allow-unauthenticated`: requires authentication when calling the Cloud Run service; **not a VPC egress parameter**.
- `--image`: Docker/OCI image in Artifact Registry, not a local Maven JAR path.

Read back the configuration:

~~~bash
gcloud run services describe orders-api \
  --project=PROJECT_ID \
  --region=asia-southeast1
~~~

In the output, look for **VPC access: Network, Subnet, Egress**, and check the active revision. Because network tags belong to a revision, if traffic still hits an older revision, inspect every serving revision rather than only the latest.

### 6.1. Testing `all-traffic` Where NAT Already Exists

Once the VPC has an appropriate outbound path:

~~~bash
gcloud run deploy orders-api \
  --project=PROJECT_ID \
  --region=asia-southeast1 \
  --image=asia-southeast1-docker.pkg.dev/PROJECT_ID/java-images/orders-api:1.0.0 \
  --network=app-vpc \
  --subnet=cr-egress-subnet \
  --network-tags=cr-orders-egress \
  --vpc-egress=all-traffic \
  --no-allow-unauthenticated
~~~

Do not run this command merely to "turn on higher security" without first verifying reachability to **Cloud Storage, Artifact Registry, partner APIs, DNS, and Cloud SQL**, plus routes and firewalls. It can immediately break calls to public endpoints.

### 6.2. Inspecting Addresses Used by Cloud Run

~~~bash
gcloud compute addresses list \
  --project=PROJECT_ID \
  --filter="purpose=SERVERLESS"
~~~

These IP addresses are **reserved for serverless infrastructure**; never manually edit or delete them. If a deploy reports subnet IP exhaustion, expand the subnet or secondary range and capacity plan per docs rather than trying to delete active IPs.

## 7. Serverless VPC Access Connector: When Is It Needed?

A connector is a managed intermediary networking resource attached to **one VPC and region**. Cloud Run services/jobs use the connector to send outbound traffic into that network.

~~~mermaid
flowchart LR
    CR["Cloud Run Java service"] --> C["Serverless VPC Access connector<br/>cr-java-conn"]
    C --> R["Dedicated /28 IP range<br/>10.42.10.0/28"]
    R --> V["VPC app-vpc"]
    V --> DB["Private backend / Cloud SQL"]
    V --> NAT["Cloud NAT if all-traffic"]
~~~

A connector fits when:

- Workloads or serverless setups do not yet match current Direct VPC capabilities.
- The organization has standardized on connectors with specific operational requirements and accepts the baseline cost.
- Benchmarks comparing Direct VPC + Cloud NAT vs. a connector show the connector meets cold-start or connection SLOs better.

**Do not choose a connector simply because one already exists.** Connectors run minimum instances; charges persist even while Cloud Run scales to zero.

### 7.1. Connector Subnets and Limits

- Requires a **non-overlapping /28 range**: either an empty `/28` subnet or an unused `/28` CIDR for Google Cloud to provision.
- The connector and Cloud Run service/job must share the **same region**; the VPC may live in the same project or a supported Shared VPC.
- Connectors have **min-instances** (commonly starting at 2) and **max-instances** within supported limits; connector machine types include `f1-micro`, `e2-micro`, or `e2-standard-4`.
- Connectors can scale up instances under load, yet **do not automatically scale back down** like standard workloads; plan capacity and cost carefully.
- Protocol support differs from Direct: connectors currently **do not support IPv6**; verify TCP/UDP/ICMP requirements.
- A connector hitting its throughput ceiling can raise latency and timeouts across every service sharing it.

## 8. Practice B — Creating a Connector and Switching the Cloud Run Service

**Impacting, billable example:** assume `10.42.10.0/28` is unused in the VPC and does not overlap the Direct VPC subnet or VPN/peering ranges. Create the connector with the Google Cloud CLI:

~~~bash
gcloud compute networks vpc-access connectors create cr-java-conn \
  --project=PROJECT_ID \
  --region=asia-southeast1 \
  --network=app-vpc \
  --range=10.42.10.0/28 \
  --min-instances=2 \
  --max-instances=3 \
  --machine-type=e2-micro
~~~

Wait for the connector state to become `READY` and verify:

~~~bash
gcloud compute networks vpc-access connectors describe cr-java-conn \
  --project=PROJECT_ID \
  --region=asia-southeast1
~~~

When using an **existing /28 subnet**, supply `--subnet=SUBNET_NAME` instead of `--network`/`--range` per valid syntax; with Shared VPC, `--subnet-project=HOST_PROJECT_ID` and host-project roles may be required.

Deploy a revision using the connector:

~~~bash
gcloud run deploy orders-api \
  --project=PROJECT_ID \
  --region=asia-southeast1 \
  --image=asia-southeast1-docker.pkg.dev/PROJECT_ID/java-images/orders-api:1.0.0 \
  --vpc-connector=cr-java-conn \
  --vpc-egress=private-ranges-only \
  --no-allow-unauthenticated
~~~

**Note when switching methods:** Do not leave **Direct network/subnet flags** and the **connector flag** mixed in the same revision. When updating an existing Cloud Run service, inspect the new revision to confirm the Direct VPC fields were actually replaced rather than copying one flag and assuming old annotations cleared automatically.

### 8.1. Inspecting Connector and Traffic

~~~bash
gcloud run services describe orders-api \
  --project=PROJECT_ID \
  --region=asia-southeast1

gcloud compute networks vpc-access connectors describe cr-java-conn \
  --project=PROJECT_ID \
  --region=asia-southeast1
~~~

Check **connector name, region, state, and min/max capacity**, and monitor **throughput/instance count**. When multiple Cloud Run services share one connector, aggregate throughput affects all of them; plan capacity globally rather than looking at one service in isolation.

## 9. Firewalls, IAM, Shared VPC, and DNS

### 9.1. Network Sources Differ Between the Two Options

| Aspect | Direct VPC egress | Serverless VPC Access |
|---|---|---|
| Source IP arriving in VPC | Ephemeral IP from the Direct subnet | IP from the connector `/28` |
| Egress firewall identity | **Cloud Run revision network tags** or subnet/source ranges per policy | Connector tag/CIDR and matching firewall rules |
| Ingress rule on backend VM | Must allow source subnet and target port | Must allow connector CIDR and target port |
| Deployment IAM | Cloud Run roles, VPC subnet/Shared VPC roles | Cloud Run roles + connector management/usage, host project if Shared VPC |
| Other limits | IP exhaustion at scale, missing subnet permissions | Connector not `READY`, insufficient capacity/throughput |

**Example backend VM** with network tag `internal-backend` listening on TCP/8081; strictly in a sandbox, create an ingress allow rule from the Direct subnet:

~~~bash
gcloud compute firewall-rules create allow-cr-to-backend-lab \
  --project=PROJECT_ID \
  --network=app-vpc \
  --direction=INGRESS \
  --priority=900 \
  --action=ALLOW \
  --rules=tcp:8081 \
  --source-ranges=10.42.0.0/24 \
  --target-tags=internal-backend
~~~

The rule above **allows the entire /24 subnet**, not just Orders API; if multiple workloads share that subnet, add segmentation policies and backend-level controls. When switching to a connector, the source becomes `10.42.10.0/28` and the rule must be updated accordingly. Never open `0.0.0.0/0` to a database port just to resolve a timeout.

With Direct VPC egress, you can use **network tags on revisions** for finer-grained **egress** firewall rules; if applying a deny-all policy, ensure DNS, Google APIs, and required backends remain explicitly permitted. **Adding an allow rule does not restrict access** if the network already has a default allow-egress rule or broader rules.

### 9.2. Separate IAM Concerns

- **Deployer:** needs permission to update Cloud Run and use the network/subnet/connector in scope.
- **Runtime service account:** needs API/Cloud SQL IAM or Secret Manager permissions per workload; those roles **do not open firewalls**.
- **Backend:** authenticates via database credentials/mTLS/IAM separately, even when the source is inside the VPC.
- **Shared VPC:** the host project owns the subnet; the service project hosts Cloud Run. The Cloud Run service agent and relevant principals need subnet permissions per documentation—never use `roles/owner` as a shortcut.

### 9.3. DNS, Private Service Connect, and Hybrid

When Java connects by hostname:

1. Determine whether the hostname actually resolves to a **private** or **public** IP.
2. Verify Cloud DNS private zones/peering/forwarding are bound and configured for the VPC.
3. For on-premises targets, check return routes, VPN/Interconnect, firewalls on both sides, and DNS forwarding.
4. When using Private Service Connect, verify the private endpoint and DNS pointing to that endpoint.
5. With `all-traffic`, verify public destinations have NAT or Google APIs traverse Private Google Access/PSC appropriately.

Never use a DNS workaround putting public IPs into config to bypass private networking policies; investigate DNS failures and TCP failures separately.

## 10. Java API: Testing the TCP Path to a Private Backend

Suppose Orders API runs on Cloud Run and must reach a TCP backend (PostgreSQL or a test server) in the VPC. Testing a **TCP handshake** separates "cannot reach IP:port" from **database authentication** errors.

A Java 17 helper using only the JDK:

~~~java
import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.Socket;

public final class EgressProbe {
    private EgressProbe() {}

    public static boolean canConnect() {
        String host = System.getenv("TARGET_HOST");
        String portText = System.getenv("TARGET_PORT");
        if (host == null || portText == null) {
            throw new IllegalStateException("Missing TARGET_HOST or TARGET_PORT");
        }
        int port = Integer.parseInt(portText);

        try (Socket socket = new Socket()) {
            socket.connect(new InetSocketAddress(host, port), 2_000);
            return true;
        } catch (IOException error) {
            return false;
        }
    }
}
~~~

Call this inside an **IAM-protected diagnostic endpoint**; never let callers specify arbitrary hosts/ports to prevent SSRF or port scanning. `TARGET_HOST` and `TARGET_PORT` must hold only administrator-managed values. Invoking on-demand is handy in a lab, while production should use rate-limited health checks, retry/backoff, and clear telemetry.

**Interpreting results:**

- `true`: Cloud Run established TCP to `host:port`; **does not prove** JDBC authentication, SSL, SQL queries, or data permissions succeed.
- `false`: could be DNS, routes, firewall, service not listening, or timeout; check safe logs and connectivity tests.
- If TCP succeeds yet PostgreSQL returns `password authentication failed`, fix DB authentication rather than changing VPC egress.

For **Cloud SQL private IP**, you also need Cloud SQL private networking (e.g., Private Services Access or PSC per product/architecture), IAM/DB credentials, and JDBC TLS/Auth Proxy/connector if chosen. Attaching a subnet to Cloud Run alone does not create a Cloud SQL private IP.

## 11. Selecting an Option for a Real-World Java System

**Context:** `orders-api` runs on Cloud Run, uses Cloud SQL PostgreSQL private IP, Cloud Storage for invoices, and a public payment API.

| Requirement | Recommended option | Reason |
|---|---|---|
| Reach Cloud SQL private IP | Direct VPC egress, `private-ranges-only` | No connector needed; internal network route |
| Cloud Storage/Google APIs | HTTPS calls using runtime IAM | No need to route through VPC unless an `all-traffic` policy mandates it |
| Public payment API | Default public path if permitted | Avoids NAT when using `private-ranges-only` egress |
| Payment API requires public IP allowlisting | Direct VPC `all-traffic` + Cloud NAT static IP | Gives third party a stable NAT IP |
| Ultra-sensitive startup SLO where Direct+NAT benchmarks slow | Evaluate connector + NAT | Trades connector baseline cost for startup latency |
| Existing Shared VPC with GKE/Compute Engine | Direct/connector per Shared VPC IAM | Requires subnet permissions and routes/firewalls |

### 11.1. Common Migration Pitfalls

- Switching `private-ranges-only` to `all-traffic` without configuring NAT, breaking external payment APIs.
- Using a nearly full `/26` Direct subnet when rolling deployments launch a new revision, throttling scaling.
- Switching to a connector without updating firewall rules from the Direct subnet to the connector `/28` CIDR.
- Concluding Cloud Run cannot reach the DB due to "missing network" when the DB only listens on `127.0.0.1` or lacks a private endpoint.
- Raising concurrency/max-instances to paper over network timeouts, **exhausting Cloud SQL connections** or subnet IPs even faster.
- Treating **inbound HTTP requests to Cloud Run** as part of VPC egress; ingress and egress are completely separate configurations.

## 12. Observability, Troubleshooting, and Rollback

### 12.1. Layered Diagnostic Workflow

~~~mermaid
flowchart TD
    E["Java backend call fails"] --> D{"DNS resolves to right IP?"}
    D -->|"No"| DNS["Cloud DNS/forwarding/hostname"]
    D -->|"Yes"| Route{"Private/internal IP?"}
    Route -->|"Yes"| VPC["Check VPC egress method<br/>subnet/connector/routes"]
    Route -->|"No"| NET["private-ranges-only or all-traffic?<br/>NAT/Private Google Access"]
    VPC --> FW{"Bidirectional firewall,<br/>backend listening on port?"}
    NET --> FW
    FW -->|"No"| FIX["Fix routes/firewalls/service"]
    FW -->|"Yes"| AUTH["TLS, DB auth, IAM, and app logs"]
~~~

### 12.2. Safe Inspection Commands

~~~bash
gcloud run services describe orders-api \
  --project=PROJECT_ID \
  --region=asia-southeast1

gcloud compute networks subnets describe cr-egress-subnet \
  --project=PROJECT_ID \
  --region=asia-southeast1

gcloud compute networks vpc-access connectors describe cr-java-conn \
  --project=PROJECT_ID \
  --region=asia-southeast1

gcloud compute firewall-rules list --project=PROJECT_ID

gcloud run services logs read orders-api \
  --project=PROJECT_ID \
  --region=asia-southeast1 \
  --limit=100
~~~

Only describe the connector if one actually exists. Use **Cloud Monitoring**, **VPC Flow Logs** (if enabled on the subnet), **Firewall Rules Logging**, **Cloud NAT logs**, and **Cloud SQL logs** to correlate source/destination, timing, and policy hits. Never log secrets, JDBC passwords, or access tokens to Cloud Logging.

### 12.3. Root-Cause Matrix

| Symptom | Likely cause | Action to take |
|---|---|---|
| Cloud Run deploy rejects subnet | Wrong region, Shared VPC IAM, or org policy | Match service region, subnet region, and service agent permissions |
| Direct deploy fails due to IPv4 exhaustion | Subnet too small/full, overlapping rolling revisions | Check `purpose=SERVERLESS`, capacity, and buffer |
| Connector stuck not `READY` | Overlapping `/28` CIDR, permissions/APIs, resource or quota shortage | Describe connector, check subnet and events |
| Private backend times out | Firewall, routes, backend not listening, or DNS | Verify Direct subnet or connector CIDR as source |
| Google APIs fail after `all-traffic` | Missing NAT/PGA/PSC, routes, or firewalls | Check public path and Google API reachability |
| Partner API sees changing source IPs | Using default egress or ephemeral NAT IPs | Use `all-traffic` + static NAT IP per design |
| Cold starts increase with Direct enabled | VPC attachment setup adds latency | Configure startup probes with retries, measure SLO, evaluate connector |
| Latency spikes when connector is busy | Connector hitting throughput/instance cap | Monitor throughput, scale up connector, or migrate to Direct |
| Cloud SQL returns `permission denied` / auth failure | IAM/DB credentials/TLS, not necessarily networking | Check DB logs and JDBC errors |
| Public client gets 403 calling Cloud Run | Ingress/Invoker IAM | Never change egress to fix an inbound error |

### 12.4. Safe Rollback

Changing Direct VPC or connector settings creates a new service revision/configuration. Before shifting production traffic:

1. Record the current revision, save the approved config, and capture baseline latency.
2. Create the new revision and test private backends, Google APIs, and public partner endpoints.
3. Use **traffic splitting** or a canary workflow if supported and prepared by the team.
4. Monitor connection errors, p95/p99 latency, startup time, concurrency, and Cloud SQL connection counts.
5. If targets are missed, shift traffic back to the **verified previous revision**; ensure the old connector/subnet remains active during rollback.
6. Only decommission the unused connector and subnet in dependency order once no revision still depends on them.

Never delete an in-use connector: other services may still reference it, and deletion does not always warn exhaustively about every consumer.

## 13. Cost, Reliability, and Cleanup

| Component | Direct VPC egress | Serverless VPC Access |
|---|---|---|
| Baseline connector compute | None | **Yes**, min instances run even when Cloud Run scales to zero |
| IP planning | Sufficiently large subnet and IP retention window | Dedicated `/28` CIDR; connector capacity |
| Networking usage | Related VPC traffic/egress fees | Traffic/egress fees plus connector instances |
| Cloud NAT when `all-traffic` | May be needed; billed separately | May be needed; billed separately |
| Logging/monitoring | Per ingested volume | Per ingested volume + connector telemetry |
| Operations | Manage subnets/IPs/firewalls/revisions | Manage connector health, max scaling, firewalls |

**Decision guidance:** compare by **cost per SLO-compliant request** and **connection setup time at peak load**, not CPU price alone. Direct generally eliminates intermediary resources, provided sufficient IPv4 space and cold-start checks are in place. Connectors carry a baseline cost, so adopt them only when measured benefits justify it.

**Sandbox cleanup** order: check which revisions/services still reference the connector or subnet → migrate or delete test revisions → delete connectors with zero remaining consumers → wait for Direct IPs to release → delete dedicated firewall rules/subnets/VPCs if no longer needed. Never delete shared VPCs or production Cloud NAT gateways. Check Billing because disks, NAT/IPs, and logging can keep accruing charges even while the service scales to 0.

## 14. Exercises and Self-Assessment Questions

### Exercise 1 — Choosing Egress

A Java API needs to call a **Cloud SQL private IP** and the **Cloud Storage public API**. There is no requirement to inspect all outbound traffic via the VPC. Should you choose Direct or a connector, `private-ranges-only` or `all-traffic`? Explain.

**Hint:** Direct + `private-ranges-only` is usually sufficient; the service account still needs IAM permissions for Cloud Storage.

### Exercise 2 — IP Demand

A Cloud Run service using Direct VPC has an old revision at 50 instances and a new revision at 50 instances running simultaneously during rollout. Using the ~2 IP/instance buffer rule, at least how many addresses should be reserved and why not use a `/26` subnet?

**Hint:** roughly 200 IPs before extra buffers or other resources; a `/24` subnet is more appropriate.

### Exercise 3 — NAT and Static IP

A partner allowlists only public egress IP `203.0.113.10`. The Java service uses `private-ranges-only` and Cloud NAT is already configured.

**Question:** is traffic to the partner API guaranteed to pass through NAT? What needs to change?

**Hint:** no; default public egress can bypass the VPC. You must use `all-traffic`, a static external IP on NAT, and matching routes/firewalls. The example address is from a documentation range.

### Exercise 4 — Connector `/28`

An enterprise VPC uses subnet `10.42.0.0/24` for Direct. An engineer plans to create a connector on `10.42.0.0/28` without checking first.

**Question:** will this work, and what must be done?

**Hint:** the connector CIDR cannot overlap an already-used range; pick a dedicated `/28` with no overlapping resources or routes.

### Exercise 5 — 403 Errors and Timeouts

After deployment, Cloud Run connects to the private backend over TCP, yet JDBC returns `password authentication failed`. An operator proposes granting Network Admin and opening the firewall across the entire VPC.

**Question:** is this reasonable? Which layer actually needs fixing?

**Hint:** networking already connects; inspect database authentication/secrets/SSL rather than widening permissions.

### Exercise 6 — Recoverability

A team migrates from a connector to Direct; p99 startup latency rises while the subnet runs out of IPs during a rolling update. Write a remediation plan covering **measuring startup**, **adding IP capacity**, **canary/rollback**, and evaluating when keeping a connector makes sense.

**Hint:** size for peak overlapping revisions; use startup probes and metrics; trade off connector baseline cost against SLOs.

### Exercise 7 — Distinguishing Ingress and Egress

A service uses `--no-allow-unauthenticated` and Direct VPC `all-traffic`. Can unauthenticated outsiders send requests to the Cloud Run URL? Can a VM in the same VPC connect directly to the Cloud Run service's **instance IP**?

**Hint:** Invoker IAM is still enforced; configuring egress does not turn a Cloud Run service into a VM accepting direct inbound connections via the VPC.

## 15. Pre-Production Checklist

- [ ] Genuine reason exists for Cloud Run to access a private network or control public egress.
- [ ] Evaluated Direct VPC egress before a connector unless specific constraints dictate otherwise.
- [ ] Kept ingress, Invoker IAM, and runtime service account distinct from VPC egress settings.
- [ ] Cloud Run region matches subnet/connector region; Shared VPC permissions are valid.
- [ ] Direct subnet is **at least /26**; capacity accounts for peak load, rolling revisions, and IP retention.
- [ ] Connector uses a **dedicated /28**, adequate min/max throughput, and budgeted baseline cost.
- [ ] `private-ranges-only` or `all-traffic` chosen with all destinations accounted for.
- [ ] If using `all-traffic`, verified Cloud NAT, Google APIs routing, DNS, and public egress IP.
- [ ] Firewall allow/deny rules target the exact source subnet or connector range and port.
- [ ] Cloud SQL/Redis/on-prem endpoints have private networking and symmetric return routes.
- [ ] Java app enforces connection timeouts, retry/backoff, pooling, and secret-free logging.
- [ ] Tested private/backend paths, Google APIs, and external partners against SLOs.
- [ ] Measured throughput, cold starts, connector/IP exhaustion errors, Cloud NAT, and cost.
- [ ] Canary/revision rollback and safe connector/subnet teardown procedure documented.

## 16. Official Documentation

Verify regional limits, IP allocation rules, connector machine types, and CLI syntax at deployment time:

- [Cloud Run — Direct VPC egress](https://docs.cloud.google.com/run/docs/configuring/vpc-direct-vpc)
- [Cloud Run — Connect with Serverless VPC Access connectors](https://docs.cloud.google.com/run/docs/configuring/vpc-connectors)
- [VPC — Serverless VPC Access overview](https://docs.cloud.google.com/vpc/docs/serverless-vpc-access)
- [VPC — Configure Serverless VPC Access](https://docs.cloud.google.com/vpc/docs/configure-serverless-vpc-access)
- [Cloud Run — VPC with Shared VPC](https://docs.cloud.google.com/run/docs/configuring/shared-vpc-direct-vpc)
- [Cloud NAT overview](https://docs.cloud.google.com/nat/docs/overview)
- [Cloud SQL — Connect from Cloud Run](https://docs.cloud.google.com/sql/docs/postgres/connect-run)
- [Cloud Run — Service ingress settings](https://docs.cloud.google.com/run/docs/securing/ingress)
- [Cloud Run pricing](https://cloud.google.com/run/pricing)
- [Serverless VPC Access pricing](https://cloud.google.com/vpc/docs/serverless-vpc-access#pricing)

**Key takeaways:** **Direct VPC egress** connects a Cloud Run service or job to a VPC **without a connector** and is generally the preferred choice; **Serverless VPC Access** adds a connector with baseline cost and capacity limits yet remains useful in fitting scenarios. Choosing `private-ranges-only` vs. `all-traffic` dictates **how public traffic routes**, so routing everything through a VPC usually requires designing **Cloud NAT and Google APIs routing**. Reliable connectivity depends simultaneously on **subnets/IPs, firewalls, IAM, DNS, backends, and the Java application**, and must be verified with real traffic alongside a rollback plan.
