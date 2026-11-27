# Diagnosing Connectivity with Connectivity Tests and Network Intelligence Center

In the `CLOUD_PROVIDERS_GCP` module, learners explore Google Cloud from project organization, IAM, and VPC to Compute Engine, GKE, Cloud Run, storage services, and databases. Through deployment scenarios, learners know how to select services, protect resources, automate releases, and monitor reliability and costs. The **Operations and Troubleshooting** chapter turns network configuration into testable evidence so operations teams can pinpoint where packets are dropped and separate network failures from application bugs.

This lesson walks through using **Connectivity Tests** and tools in **Network Intelligence Center** to investigate connectivity across VMs, GKE, Cloud Run, load balancers, Cloud SQL, on-premises networks, and the Internet. You will run a TCP test, read step-by-step traces, correlate firewalls/routes, inspect the limits of live data plane analysis, and combine Network Analyzer, Network Topology, Firewall Insights, Flow Analyzer, and Performance Dashboard.

## 1. Real-World Scenario and Objectives

Suppose a Java system includes:

- `orders-api` running on a Compute Engine VM inside VPC `orders-vpc`.
- PostgreSQL on Cloud SQL using a private IP.
- A group of workers in GKE calling the internal API over TCP 8080.
- An office network connected to the VPC via Cloud VPN or Cloud Interconnect.

A new release causes requests from a VM to the API to time out. The application team suspects the firewall blocked traffic; the network team claims the app is not listening on the port. Instead of changing rules blindly, operations needs to answer:

1. Which exact VM, interface, and IP is the source endpoint?
2. Do the destination IP, port, and protocol match the request?
3. Which routes, firewalls, peering links, VPNs, or load balancers sit on the path?
4. At which step does Connectivity Tests predict the packet is dropped?
5. For supported scenarios, do live data plane probes reach the destination?
6. If the network path works, could the remaining fault lie in DNS, TLS, authentication, the application listener, or the database?

The acceptance criterion is an evidence-backed conclusion: **the bottleneck, accountable layer, required change, and post-fix verification test**.

## 2. What Tools Make Up Network Intelligence Center?

**Network Intelligence Center (NIC)** is Google Cloud's suite for network observability, analysis, and troubleshooting. Not every module answers the same question.

| Tool | Primary Question | When to Use |
| --- | --- | --- |
| **Connectivity Tests** | Which steps is a packet expected to traverse, and where does configuration drop it? | Diagnosing a specific source → destination path with a given protocol/port. |
| **Network Analyzer** | Are any VPC configurations misconfigured or suboptimal? | Continuously discovering route, firewall, topology, dependency, and connectivity issues. |
| **Network Topology** | How do VPCs, VMs, hybrid links, and services connect? | Viewing topology graphs and traffic metrics over time. |
| **Firewall Insights** | How are firewall rules used? Are any overly broad or unused? | Reviewing firewall hygiene, rule usage, and tightening recommendations. |
| **Flow Analyzer** | Which IPs/ports/protocols carry actual traffic flows? | Analyzing VPC Flow Logs by 5-tuple to find top talkers, anomalies, or traffic costs. |
| **Performance Dashboard** | What are network latency and packet loss between zones/VMs? | Investigating network-layer performance after endpoints are identified. |
| **Cloud Network Insights** | Which hop has application/network performance issues across hybrid/multicloud? | Observing broader end-to-end paths in supported architectures. |

~~~mermaid
flowchart TB
    INCIDENT[Incident: timeout / packet loss / unreachable]
    INCIDENT --> CT[Connectivity Tests\nSpecific packet path]
    INCIDENT --> NA[Network Analyzer\nContinuous config detection]
    INCIDENT --> TOPO[Network Topology\nRelationships and traffic view]
    INCIDENT --> FW[Firewall Insights\nFirewall rule evaluation]
    INCIDENT --> FLOW[Flow Analyzer\nVPC Flow Logs analysis]
    INCIDENT --> PERF[Performance Dashboard\nLatency / packet loss]
    CT --> RCA[Root cause + evidence]
    NA --> RCA
    TOPO --> RCA
    FW --> RCA
    FLOW --> RCA
    PERF --> RCA
    RCA --> FIX[Reviewed change]
    FIX --> VERIFY[Rerun test + verify application]
~~~

**Tool selection rule:** if you need to know whether a specific TCP packet can travel from VM A to VM B through firewalls, start with Connectivity Tests. If you need broad misconfiguration detection, check Network Analyzer. If you need to know what traffic actually traversed the network, check VPC Flow Logs/Flow Analyzer. If you need inter-zone latency/packet loss, check Performance Dashboard. These tools complement rather than replace one another.

## 3. What Does Connectivity Tests Analyze?

Connectivity Tests takes an input equivalent to a **5-tuple excluding source port**:

- Source endpoint and source IP/interface.
- Destination endpoint/IP.
- IP protocol (e.g., TCP or UDP).
- Destination port (for TCP/UDP).

It analyzes the expected packet path through VPCs, routes, firewalls, Cloud VPN, VLAN attachments, peering, load balancers, and supported network configurations. Results present a logical step-by-step trace: interface selection, egress/ingress firewall checks, route lookup, network attachment/peering traversal, and destination reachability.

### 3.1. Configuration Analysis

**Configuration analysis** simulates behavior from Google Cloud resource configurations. It constructs a forwarding model to answer: *under current configuration, can a packet traverse these steps?*

It helps uncover:

- Egress firewall rules blocking the source.
- Ingress firewall rules blocking the destination.
- Missing routes or routes pointing to the wrong next hop.
- Missing paths across VPC peering, VPNs, or VLAN attachments.
- Incompatible load balancer or endpoint configurations.
- Configuration inconsistencies after migrations or network changes.

The trace highlights **the first step that may drop the packet**. When reading results, do not read only the final summary line; expand every hop and record the resource, rule, route, priority, and network involved.

### 3.2. Live Data Plane Analysis

For supported scenarios, Connectivity Tests also sends **multiple TCP or UDP probe packets** through the live data plane to verify whether packets actually reach the destination. Results report probes sent, probes delivered, reachability status, and median/p95 one-way latency.

| Live Analysis Status | Probes Reaching Destination |
| --- | --- |
| **Reachable** | At least 95% |
| **Unreachable** | Zero probes arrived |
| **Partially reachable** | Some probes arrived, but fewer than 95% |

Live analysis is valuable for cross-checking configuration against the data plane. However, it is **not a synthetic application test**: TCP/UDP probes do not log into databases, execute HTTP business API contracts, validate TLS certificates, or test user authentication.

### 3.3. Two Outcomes Never to Confuse

| Configuration Analysis | Live Data Plane Analysis | Interpretation |
| --- | --- | --- |
| Packet could be delivered | Reachable | Simulated config is valid and live probes reached the target during measurement. Application testing is still required. |
| Packet could not be delivered | Unreachable | Clear config failure and probes failed to arrive. Start at the dropped hop. |
| Packet could be delivered | Unreachable/Partially reachable | Config looks valid yet the data plane has an issue, or certain paths/endpoints were not sufficiently probed. Inspect dynamic state, routes, firewalls, backend health, and probe limits. |
| Packet could not be delivered | Reachable | Configuration analysis may not have propagated yet, paths/endpoints may differ, or the model does not represent the actual request. Re-verify source/destination/interface and allow propagation. |

**"Packet could be delivered" does not guarantee live data plane delivery.** Configuration analysis only evaluates drops inferable from configuration and does not track the live health of all internal Google production infrastructure. Live probes add evidence for supported routes, but remain bounded by probe count and selected paths.

## 4. Supported Endpoints and Important Limitations

Connectivity Tests supports many source/destination types, but **configuration analysis and live data plane analysis do not have identical support matrices**.

| Endpoint | Testable Roles | Notes |
| --- | --- | --- |
| Compute Engine VM | Source/destination | Live data plane analysis requires a running VM; for multi-NIC VMs, select the exact interface. |
| GKE cluster control plane | Source/destination per supported cases | Some endpoints only support internal IPs; check the support matrix and PSC limitations. |
| GKE Pod | Source/destination | Requires exact cluster, namespace, Pod/IP, and port. |
| Cloud Run service/job/revision | Source in certain scenarios | Live analysis depends on serverless VPC access settings; check the support matrix before assuming Direct VPC egress is supported. |
| Cloud SQL instance | Source/destination in supported cases | For Cloud SQL in a Google-owned VPC, configuration analysis may show only an overall summary at the end without exposing Google's internal config. |
| Load balancer forwarding rule | Destination | Checks VIP/forwarding rule and backend path; probes may pick a random backend. |
| Internal/external IP | Source/destination | Must specify the matching network/IP type. |
| On-premises IP | Source/destination per connectivity | Typically involves Cloud VPN, Cloud Interconnect, or a router appliance. |
| Private Service Connect endpoint | Destination in certain models | Do not generalize support across every PSC service type. |

Key limitations to remember:

- For **Cloud SQL and the GKE control plane**, some test types do not support endpoints using Private Service Connect; consult the current support matrix for the exact source/destination direction.
- Live data plane analysis from a Cloud Run source currently carries specific Serverless VPC Access conditions. Do not assume one result for a Cloud Run service applies to all revisions or egress types.
- For Google-managed services, Connectivity Tests can trace the path from your VPC and report overall reachability, but does not display internal configuration details inside Google-managed projects/VPCs.
- When the destination is an Internet IP, live analysis measures up to Google's network edge location; it does not prove the remote Internet server processed the request.
- If the destination is a load balancer with multiple backends, probes may choose a backend randomly. Not every backend is guaranteed to be tested.
- With ECMP, each probe may follow a random route; probe counts may not cover every path.
- The tool does not generally evaluate VMs configured to act as routers, firewalls, NAT gateways, or VPN appliances.

Before concluding "the feature is broken," check whether your endpoint type, network type, port, IP family, region, and resource state are within the support matrix.

## 5. Preparing Project, APIs, and IAM

### 5.1. Enable the Network Management API

Connectivity Tests uses the **Network Management API**. Enable it in the project hosting the tests:

~~~bash
gcloud services enable networkmanagement.googleapis.com \
  --project=PROJECT_ID
~~~

The project needs active billing and the Google Cloud CLI installed. Opening Connectivity Tests for the first time in the Console may also prompt you to enable the API.

### 5.2. Roles for Operators

Predefined roles for Connectivity Tests:

| Role | Key Permissions | Who Should Hold It |
| --- | --- | --- |
| `roles/networkmanagement.viewer` | List/get tests and view Network Management resources within scope | NOC, auditors, report readers |
| `roles/networkmanagement.editor` | Create, update, rerun, and delete Connectivity Tests plus related Network Management permissions | Network engineers running diagnostics |
| `roles/networkmanagement.admin` | Full control over Network Management resources | Platform/network owners responsible for administration |

Some operations also require metadata read permissions on source/destination resources, projects, or networks; holding `roles/networkmanagement.viewer` alone does not let a user view every resource across all projects. For cross-project tests, review IAM in both the test project and endpoint projects.

Do not grant Network Management Admin to all developers just so they can view a result. Separate **read tests**, **create/rerun tests**, and **modify network/firewall** into distinct responsibilities. Someone running a Connectivity Test does not automatically need permission to edit VPC firewalls.

### 5.3. Verify Identity Before Running

~~~bash
gcloud auth list
gcloud config get-value project
gcloud services list \
  --enabled \
  --project=PROJECT_ID
~~~

Check the active principal, current project, and enabled APIs. For CI/CD, use Workload Identity Federation or service account impersonation; avoid storing long-lived JSON keys. When working across multiple projects, pass `--project` explicitly to avoid creating tests in the wrong project.

## 6. Lab Practice: VPC VM to Internal VM

### 6.1. Lab Diagram

Assume two staging VMs in the same VPC:

- Source VM: `orders-client`, internal IP `10.10.1.10`.
- Destination VM: `orders-api-vm`, internal IP `10.10.2.20`.
- VPC: `orders-vpc`.
- Destination app listens on TCP `8080`.
- Ingress firewall only allows approved source subnets or service accounts.

~~~mermaid
flowchart LR
  SRC[orders-client\n10.10.1.10] -->|TCP 8080| ROUTE[VPC orders-vpc\nroute lookup]
  ROUTE --> FW[Firewall evaluation]
  FW -->|allow| DST[orders-api-vm\n10.10.2.20:8080]
  FW -->|deny| DROP[Packet dropped]
  DST --> APP[Java listener]
~~~

Use only **existing staging resources** in the lab. Never spin up VMs, open firewalls, or send test traffic into production just to experiment. If two VMs are unavailable, use a pre-provisioned training environment or work through the sample output analysis.

### 6.2. Verify Pre-Test Conditions

On the destination VM, verify the application has a TCP 8080 listener using an OS-appropriate command (e.g., `ss -lntp` on Linux). Record the internal IP and network interface of both VMs.

Inspect firewall rules:

~~~bash
gcloud compute firewall-rules list \
  --project=PROJECT_ID \
  --filter="network:orders-vpc"
~~~

Check these fields: direction, priority, source/destination ranges, target tags/service accounts, allowed/denied protocols/ports, and disabled state. Never stop at finding one `allow` rule: a higher-priority rule or hierarchical firewall policy can override the outcome.

### 6.3. Create a Connectivity Test with gcloud

For two private IPs in the same VPC, use an equivalent configuration:

~~~bash
gcloud network-management connectivity-tests create orders-client-to-api-8080 \
  --source-ip-address=10.10.1.10 \
  --source-network=projects/PROJECT_ID/global/networks/orders-vpc \
  --source-network-type=GCP_NETWORK \
  --destination-ip-address=10.10.2.20 \
  --destination-port=8080 \
  --protocol=TCP \
  --round-trip \
  --project=PROJECT_ID
~~~

Replace project ID, VPC URI, IPs, and port with actual staging values. The command creates and immediately runs the test; the test persists as a Connectivity Test resource until deleted. `--round-trip` requests both forward and return path analysis when supported.

To target a specific VM as source, provide its full URI and the source IP belonging to the right NIC:

~~~bash
gcloud network-management connectivity-tests create orders-client-to-api-8080 \
  --source-instance=projects/PROJECT_ID/zones/ZONE/instances/orders-client \
  --source-ip-address=10.10.1.10 \
  --destination-ip-address=10.10.2.20 \
  --destination-port=8080 \
  --protocol=TCP \
  --round-trip \
  --project=PROJECT_ID
~~~

For multi-NIC VMs, explicitly specify the source interface/IP. Specifying only the VM URI may default to the primary interface, simulating the wrong network path compared to what the application actually uses.

### 6.4. Inspect Results

~~~bash
gcloud network-management connectivity-tests describe \
  orders-client-to-api-8080 \
  --project=PROJECT_ID
~~~

In the output, examine:

- Actual source and destination, IPs, protocol, destination port.
- Operation status and test timestamp.
- Configuration analysis result and trace steps.
- Selected route, matching firewall rules, and any network attachments/peering.
- The exact drop step or conclusion that packets can be delivered.
- Live data plane analysis result if the route and endpoints are supported.

If a newly created test has not finished, check operation state and re-describe. If network changes were applied right before the test, wait **20–120 seconds** for configuration analysis to ingest the updates. Live data plane analysis does not share the exact same config propagation delay, so the two results may temporarily diverge.

### 6.5. Rerun After Fixing

After a reviewed fix is deployed to staging:

~~~bash
gcloud network-management connectivity-tests rerun \
  orders-client-to-api-8080 \
  --project=PROJECT_ID
~~~

Compare before/after traces: verify the drop step is gone, no unexpected route changes occurred, and live probes reach the destination. Archive before/after outputs alongside the change ID for auditing.

## 7. Testing from a VM to a Cloud SQL Private IP

This is a common scenario when Spring Boot runs on Compute Engine or a VM in a GKE node network and needs to reach Cloud SQL.

### 7.1. Pre-Check Configuration

Verify:

1. The Cloud SQL instance has a private IP and uses the expected VPC/Private Services Access or chosen private connectivity method.
2. The VM has a route to the private IP from the correct source interface.
3. Firewalls/routing allow the database TCP port (e.g., PostgreSQL 5432, MySQL 3306).
4. The database instance is running and listening.
5. If using PSC, check the Connectivity Tests support matrix for that exact endpoint; do not apply private-service-access conclusions to every PSC topology.

### 7.2. Create a Test with a Google-Managed Service Endpoint

~~~bash
gcloud network-management connectivity-tests create orders-vm-to-cloudsql-5432 \
  --source-instance=projects/PROJECT_ID/zones/ZONE/instances/orders-client \
  --source-ip-address=SOURCE_VM_PRIVATE_IP \
  --destination-cloud-sql-instance=projects/DB_PROJECT_ID/instances/SQL_INSTANCE \
  --destination-port=5432 \
  --protocol=TCP \
  --round-trip \
  --project=PROJECT_ID
~~~

`--destination-cloud-sql-instance` takes the Cloud SQL instance resource URI. By default, Connectivity Tests targets the private IP of a Google-managed service if present; otherwise it may fall back to the public IP. Verify the tested endpoint matches your architecture.

Configuration analysis traces egress firewalls and routes inside the customer VPC, but upon entering Cloud SQL's Google-owned VPC, it provides only **overall reachability** without exposing Google's internal configuration.

### 7.3. When Connectivity Tests Reports Packets Can Reach Cloud SQL

That result does not prove PostgreSQL authentication works. Run an application-layer check from the VM:

~~~bash
nc -vz PRIVATE_DB_IP 5432
~~~

Once TCP connects, use `psql` or JDBC with securely managed credentials to execute `SELECT 1`. If the socket opens yet JDBC throws a password/authentication/TLS error, the fault lies at the database/application layer rather than routing/firewalls. Never put passwords in shell history or logs.

## 8. Diagnosing Paths to the Internet and On-Premises Networks

### 8.1. VM to the Internet

Verify whether the source VM has an external IP or uses Cloud NAT, a default route `0.0.0.0/0`, egress firewall rules, and a DNS resolver. For a test sourced from an internal VPC IP:

~~~bash
gcloud network-management connectivity-tests create orders-vm-to-internet-443 \
  --source-ip-address=SOURCE_INTERNAL_IP \
  --source-network=projects/PROJECT_ID/global/networks/orders-vpc \
  --source-network-type=GCP_NETWORK \
  --destination-ip-address=DESTINATION_PUBLIC_IP \
  --destination-port=443 \
  --protocol=TCP \
  --round-trip \
  --project=PROJECT_ID
~~~

When the destination is an Internet IP, live data plane analysis may measure only up to **Google's network edge location**. The result does not replace `curl` against the hostname, TLS validation, or testing the target application. DNS must also be verified separately: resolve the hostname to the expected IP before running the test.

### 8.2. VPC to On-Premises via Cloud VPN / Interconnect

When testing a private IP destination on-premises, verify:

- Are routes from the VPC to on-premises ranges learned/advertised by Cloud Router or properly configured statically?
- Are Cloud VPN tunnels or Interconnect VLAN attachments up?
- Are advertised and received prefixes filtered or overlapping?
- Do firewalls in both GCP and on-premises permit the protocol/port?
- Does a return route exist from on-premises back to the GCP subnet?
- Could MTU or policy-based routing drop only large packets or specific flows?

Connectivity Tests simulates Google Cloud networking steps and supported dynamic states such as tunnels and routes. It cannot read firewall configs on on-premises appliances not managed via Google Cloud. Reachability to a VLAN attachment or network edge does not prove the on-premises application received the request.

### 8.3. Forward and Return Paths

A TCP request requires a forward path to the destination and a return path for responses. Use `--round-trip` where appropriate, but always inspect both traces carefully. Stateful firewalls allow return traffic via connection tracking; configuration analysis simulates certain connection-tracking behaviors for outbound-initiated tests, but cannot inspect live VM connection tables.

If the forward path passes yet responses never return, check asymmetric routing, egress/ingress firewalls, NAT, intermediate appliances, and remote-side policies. Never open `0.0.0.0/0` in both directions as a temporary workaround.

## 9. Using Network Analyzer for Automatic Misconfiguration Detection

**Network Analyzer** continuously monitors VPC configurations and generates insights when it detects misconfigurations or suboptimal setups. It analyzes topology, firewalls, routes, configuration dependencies, and connectivity to services/applications; when detecting an issue, it attempts to correlate recent configuration changes and suggest fixes.

Workflow:

1. Open **Network Intelligence Center → Network Analyzer**.
2. Select the appropriate project or supported scope.
3. Filter insights by category, severity, resource, and time.
4. Open an insight to inspect affected resources, root cause, and suggested resolution.
5. Correlate with recent Terraform or Cloud Audit Logs changes.
6. Verify with Connectivity Tests or application tests before applying changes.
7. After fixing, wait for the analyzer to refresh and confirm the insight resolves or does not recur.

Network Analyzer excels at **continuous discovery**, but does not replace Connectivity Tests for simulating a specific packet. An insight may flag an overly broad firewall rule, missing route, or dependency issue; you still must verify whether live requests traverse that resource.

## 10. Using Network Topology to Understand Relationships and Traffic

**Network Topology** visualizes network infrastructure, including VPC networks, hybrid connectivity, connections to Google-managed services, and associated traffic metrics. For projects with GKE Enterprise enabled, additional views of clusters, namespaces, workloads, and Pods may be available.

Use it when:

- It is unclear whether two workloads share a VPC or cross peering/Shared VPC.
- You need to inspect cross-region or on-premises traffic.
- You want to detect a service exchanging traffic with an unexpected network or region.
- You need to correlate topology with throughput or operational metrics.

Reading topology:

1. Select the relevant project and time window.
2. Choose the infrastructure view or GKE Enterprise view if available.
3. Expand nodes/edges to inspect resources, connections, and metrics.
4. Filter by network, region, project, or resource type.
5. Cross-check traffic against architecture diagrams and data residency policies.

Network Topology shows relationships and traffic, not packet-level traces. An edge carrying traffic does not prove all ports/protocols are allowed; an edge without traffic could reflect the selected window, sampling, or an idle workload.

## 11. Using Firewall Insights and Flow Analyzer

### 11.1. Firewall Insights

**Firewall Insights** shows how VPC firewall rules are used, surfaces overly permissive or unnecessary rules, and recommends tightening configurations. Use it to audit:

- Rules with zero matched traffic during the observation window.
- Rules allowing broader source ranges than needed.
- Rules shadowed by other rules or effectively inactive.
- Rules with unexpected priorities or target scopes.

Never delete a rule simply because no traffic matched over a short window. A rule may exist for disaster recovery, quarterly batch jobs, or infrequent traffic. Review with owners, logs, and change history before modifying.

### 11.2. Flow Analyzer and VPC Flow Logs

**Flow Analyzer** analyzes VPC Flow Logs by 5-tuple:

\[
(\text{source IP},\ \text{destination IP},\ \text{source port},\ \text{destination port},\ \text{protocol})
\]

It answers: which VMs generate the most traffic, which destinations/ports are active, when traffic spiked, and whether anomalous flows exist. This view relies on **collected traffic logs**, rather than configuration simulation like Connectivity Tests.

To collect data:

1. Identify the subnets/networks to monitor.
2. Enable VPC Flow Logs with appropriate sampling, aggregation, and metadata.
3. Wait for logs to populate and verify log scope and retention.
4. Use Flow Analyzer to filter by source, destination, port, protocol, project, and time window.
5. For deeper investigation, open raw log entries or export via an approved analytics pipeline.

Flow Logs use sampling and aggregation; do not treat a record as a full packet capture. Flow Analyzer only inspects collected logs, so if logging is disabled or the wrong subnet is selected, empty results do not prove zero network traffic.

### 11.3. Combining Both Tools

| Connectivity Tests | Flow Analyzer | Suggested Conclusion |
| --- | --- | --- |
| Config drop at firewall | No matching flow records | Traffic may never reach the logging point; check source/target subnets and log sampling. |
| Config can deliver | Actual flow records exist | Path carries traffic; check app listener, TLS/auth, and return path. |
| Config can deliver | No flow records | Requests may not be generated, wrong source selected, logging disabled, or sampling missed them. |
| Config drop | Flow records still exist | Test inputs may be wrong, flows belong to another path, or config analysis has not updated. Cross-check timestamp, 5-tuple, and endpoints. |

Never use Flow Logs to conclude IAM or database user permissions succeeded. Flow logs record network traffic, not application authentication outcomes.

## 12. Using Performance Dashboard to Separate Network Latency from Application Latency

**Performance Dashboard** displays Google Cloud network packet loss and latency, including inter-zone performance between VMs. It shows whether underlying network degradation exists and provides historical performance trends.

When an API is slow:

1. Check application traces to separate app processing time, database wait time, and network calls.
2. Open Performance Dashboard and select the region/zone and incident time window.
3. Inspect latency/packet loss between the relevant zones.
4. Compare with Cloud Monitoring metrics for VMs, GKE, load balancers, or Cloud SQL.
5. If the network dashboard is healthy while app latency rises, investigate CPU, GC, connection pools, SQL queries, retries, or thread saturation.
6. If network packet loss/latency rises, investigate routes, firewalls, hybrid links, and infrastructure changes.

Performance Dashboard does not measure business logic execution time. Low latency between two zones does not make an API fast if a database query takes 2 seconds or the JVM hits a GC pause.

## 13. Analyzing Traces: Finding the Exact Dropped Hop

A Connectivity Test result can span many steps. Read traces in order:

1. **Source selection:** verify source resource, interface, source IP, and project. On multi-NIC VMs, choosing the wrong interface simulates the wrong path.
2. **Source egress firewall:** inspect egress rules, priority, target, protocol/port, and hierarchical firewall policies.
3. **Route lookup:** check destination prefix, route priority, next hop, peering/VPN/Interconnect, or default route.
4. **Network transition:** identify whether packets cross VPC peering, Cloud VPN, VLAN attachments, load balancers, or PSC endpoints.
5. **Destination ingress firewall:** check source ranges, target tags/service accounts, and matching allow/deny rules.
6. **Google-managed endpoint:** if the destination is Cloud SQL or GKE control plane, review the reachability summary and remember limited visibility inside Google-owned VPCs.
7. **Return path:** for round-trip tests, inspect return routes and firewalls.
8. **Data plane:** if live analysis ran, compare probe counts, reachability, and latency against configuration results.

A trace may show multiple candidate routes due to ECMP or policy-based routing. The tool may not know the exact internal hash selecting a route for each packet. Use live probes, Flow Logs, and application-level tests for corroborating evidence.

## 14. End-to-End Troubleshooting Workflow

Use this checklist for network incidents:

~~~mermaid
flowchart TD
  A[Error reported: source, dest, time, port] --> B[Check DNS and endpoint IP]
  B --> C[Verify resource/interface/route context]
  C --> D[Run Connectivity Test]
  D --> E{Config trace shows drop?}
  E -->|Yes| F[Inspect hop, firewall, route, peering, policy]
  E -->|No| G{Live analysis supported?}
  F --> H[Review change and fix in staging]
  G -->|Yes| I[Check probe reachability/latency]
  G -->|No| J[Run TCP/application test and check logs]
  I --> K[Network Analyzer / Flow Logs / Topology]
  J --> K
  K --> L[Separate network from TLS/auth/app]
  H --> M[Rerun Connectivity Test]
  L --> M
  M --> N[Verify end-to-end request]
  N --> O[Document RCA, evidence, and runbook]
~~~

### 14.1. Gathering Inputs Before Running

Every incident needs:

- Project and resource IDs for source and destination.
- Region/zone, network, subnet, and NIC.
- Source IP, destination IP, or resolved FQDN.
- Protocol, destination port, and error timestamp.
- Any Cloud NAT, proxy, firewall appliance, PSC, VPN, or Interconnect in use.
- Whether traffic is one-way or round-trip; affecting one VM/Pod or all workloads.
- Whether failures are continuous or tied to specific times/traffic peaks.

Without accurate IPs and ports, a Connectivity Test can succeed while failing to represent live failing requests.

### 14.2. After Finding the Drop Point

1. Save the test name, trace, timestamp, and pre-change snapshot.
2. Check Terraform/Cloud Audit Logs to see which rule or route changed recently.
3. Identify the rule owner and blast radius.
4. Draft a specific change proposal: source range, target, protocol, port, route, or policy.
5. Perform security review; avoid opening `0.0.0.0/0` or deleting general deny rules.
6. Deploy to staging and wait for configuration analysis to pick up the change.
7. Rerun the Connectivity Test and run TCP/application tests.
8. Only promote the change through approved release processes after verification.

**Do not change multiple firewall rules at once** without justification. Changing one controlled variable makes root cause confirmation and rollback much easier.

## 15. Practice Lab Matrix

| ID | Scenario | Primary Tools | Evidence to Archive |
| --- | --- | --- | --- |
| CT-01 | VM → VM same VPC, TCP 8080 | Connectivity Tests | Source trace, route, firewall, destination |
| CT-02 | VM → Cloud SQL private IP, TCP 5432 | Connectivity Tests + TCP/JDBC | Reachability summary, `nc` result, `SELECT 1` |
| CT-03 | VM → Internet IP, TCP 443 | Connectivity Tests + DNS/curl | Network edge probe, DNS resolution, TLS response |
| CT-04 | VM → on-premises IP via VPN | Connectivity Tests + Cloud VPN logs | Route/tunnel/return path |
| CT-05 | GKE Pod → internal service | Connectivity Tests + Flow Logs | Pod IP, namespace, policy/route, and 5-tuple |
| CT-06 | Cloud Run → private endpoint | Support matrix + live/real workload test | VPC connector/egress config, TCP result |
| NA-01 | Detect route/firewall misconfiguration | Network Analyzer | Insight, affected resource, recommendation |
| TOPO-01 | Verify cross-region traffic | Network Topology | Graph, throughput, region/edge |
| FW-01 | Find overly broad/unused rules | Firewall Insights | Rule, usage window, owner, review |
| FLOW-01 | Identify top talkers | Flow Analyzer | 5-tuple, traffic volume, and timestamps |
| PERF-01 | Investigate inter-zone packet loss | Performance Dashboard | Loss/latency chart and time window |

### 15.1. Lab PASS Criteria

- Test uses the exact source IP/NIC, destination IP, protocol, and port.
- Configuration trace identifies either the drop step or expected forwarding path.
- Live analysis is explicitly documented as **supported/not supported**; never inferred from config results.
- Cloud SQL tests include separate TCP and database-level checks.
- On-premises tests include evidence from the remote network/device owner.
- Firewall/route changes have an owner, ticket, and rollback plan.
- Post-change tests show no unexpected drops.
- The application completes real requests; logs/traces confirm at matching timestamps.
- Incident report cleanly separates network issues from app/auth/DNS/TLS issues.

## 16. Common Symptoms and Classification

| Symptom | Possible Cause | Investigation Path |
| --- | --- | --- |
| `Packet could not be delivered` at egress | Egress deny, wrong source route, or wrong source interface | Check source NIC, egress rule, and route match |
| Drop at destination ingress | Firewall rule missing source range, target mismatch, or higher-priority deny | Check target tags/service accounts, hierarchical policies, and priority |
| No matching route | Missing route, wrong subnet/peering, or route propagation issue | Inspect route table, dynamic routes, and Cloud Router |
| VPN tunnel up yet test fails to arrive | Prefix not advertised/received, missing return route, on-prem firewall | Check BGP routes, tunnel, policies, and remote side |
| Cloud SQL reachable yet JDBC fails | DB user/password/TLS, port listener, or database state | Run TCP check then separate JDBC/SQL query |
| Config passes yet live probes fail | Dynamic data plane, ECMP, backend, endpoint, or config propagation | Check support matrix, probes, backend health, and Flow Logs |
| Live probes reachable yet app times out | Probes do not test app protocol/auth; wrong DNS/hostname or TLS | Test with `curl`/`psql`/JDBC from the actual source |
| New test misses recent firewall change | Configuration analysis has not updated yet | Wait ~20–120 seconds and rerun |
| Test to load balancer is intermittent | Multiple backends and random probe selection | Inspect individual backends, LB logs/health, and synthetic tests |
| Cloud Run source lacks live results | Endpoint/config not in support matrix | Check Serverless VPC Access and support matrix; run real test from workload |
| Flow Analyzer has no data | VPC Flow Logs disabled, wrong subnet/time window, or sampling | Check logging configuration and time range |
| Firewall Insights marks rule unused | Low traffic, non-representative window/sampling, or DR-only rule | Review with owner, workload schedule, and logs before deleting |
| Network Analyzer shows insight while app runs | Insight flags suboptimal/misconfig risk, not necessarily an outage | Check severity, affected path, and verify with Connectivity Test |
| Network Topology missing an edge | No traffic in window or metrics not yet ready | Widen time range and verify telemetry sources |
| Performance Dashboard normal yet API slow | Bottleneck in JVM, database, or downstream | Inspect application traces, GC, CPU, pools, and query metrics |

## 17. Routine Operations and Cost Management

### 17.1. Daily/Weekly

- Review new Network Analyzer insights and high-severity changes.
- Audit firewall rule changes and overly broad rules.
- Investigate anomalous inter-zone or hybrid-link packet loss/latency.
- Verify VPC Flow Logs remain enabled on target subnets with proper metadata and retention.
- Review saved Connectivity Tests; enforce naming conventions by source/destination/port and ticket.
- Clean up obsolete tests per process to keep the test list uncluttered.

### 17.2. Cost and Data Volume

Connectivity Tests persist as resources until deleted; avoid creating thousands of one-off tests and leaving them orphaned. Flow Logs, Cloud Logging, metrics, dashboards, and Network Intelligence Center modules carry separate pricing/usage terms. Before enabling logging across all subnets:

1. Estimate traffic volume and sampling rate.
2. Select aggregation intervals and metadata tailored to your goal.
3. Set log retention and sink destinations per audit requirements.
4. Use Flow Analyzer for targeted questions rather than keeping full metadata indefinitely if unnecessary.
5. Monitor log ingestion, storage, query, and network egress costs.

### 17.3. Change Governance

Connectivity Tests provide diagnostic evidence, not change approval. Every firewall, route, peering, VPN, PSC, or DNS change requires:

- An accountable owner.
- Specification of allowed source/destination/port.
- Business justification and security review.
- Pre- and post-change test plans.
- A rollback plan.
- Connectivity Tests results and application-level validation.
- Recorded timestamp, project, and change ID.

## 18. Lesson Completion Checklist

- [ ] Can explain Network Intelligence Center and the role of each module.
- [ ] Can distinguish configuration analysis from live data plane analysis.
- [ ] Understand 5-tuple inputs and choose the exact source interface, destination, protocol, and port.
- [ ] Know that live analysis uses TCP/UDP probes and the 95% Reachable threshold.
- [ ] Understand probe limitations with ECMP, multi-backend load balancers, and Google-managed services.
- [ ] Know how to enable `networkmanagement.googleapis.com` and assign least-privilege IAM roles.
- [ ] Can create, describe, rerun, and list Connectivity Tests using `gcloud`.
- [ ] Can read traces and pinpoint dropped firewall/route/peering hops.
- [ ] Know to wait 20–120 seconds for propagation after configuration changes.
- [ ] Can test VM-to-VM, VM-to-Cloud SQL, Internet, and hybrid connectivity.
- [ ] Can separate TCP reachability from DNS, TLS, database auth, and application behavior.
- [ ] Can use Network Analyzer for continuous misconfiguration detection.
- [ ] Can use Network Topology to understand network graphs and traffic.
- [ ] Can use Firewall Insights to review rule usage before making changes.
- [ ] Can use Flow Analyzer with VPC Flow Logs and 5-tuples.
- [ ] Can use Performance Dashboard to compare inter-zone latency/packet loss.
- [ ] Maintain change tickets, rollback plans, and before/after evidence.
- [ ] Manage test resources, Flow Logs retention, and costs appropriately.

## References

- [Network Intelligence Center overview](https://docs.cloud.google.com/network-intelligence-center/docs/overview) — overview of Network Intelligence Center modules.
- [Connectivity Tests overview](https://docs.cloud.google.com/network-intelligence-center/docs/connectivity-tests/concepts/overview) — configuration analysis, live data plane, endpoints, and limitations.
- [Create and run Connectivity Tests](https://docs.cloud.google.com/network-intelligence-center/docs/connectivity-tests/how-to/running-connectivity-tests) — creating tests in Console and gcloud across VM, Cloud SQL, GKE, Cloud Run, and hybrid scenarios.
- [gcloud connectivity-tests create](https://docs.cloud.google.com/sdk/gcloud/reference/network-management/connectivity-tests/create) — syntax and endpoint flags.
- [gcloud connectivity-tests commands](https://docs.cloud.google.com/sdk/gcloud/reference/network-management/connectivity-tests) — list, create, describe, rerun, update, and delete.
- [Connectivity Tests roles and permissions](https://docs.cloud.google.com/network-intelligence-center/docs/connectivity-tests/concepts/access-control) — Network Management Admin, Editor, Viewer, and permissions.
- [Enable the Network Management API](https://docs.cloud.google.com/network-intelligence-center/docs/reference/enable-api) — API enablement and IAM.
- [Network Analyzer overview](https://docs.cloud.google.com/network-intelligence-center/docs/network-analyzer/overview) — automatic insights, root cause, and recommendations.
- [Network Topology overview](https://docs.cloud.google.com/network-intelligence-center/docs/network-topology/overview) — topology, hybrid connections, and traffic metrics.
- [Firewall Insights overview](https://docs.cloud.google.com/network-intelligence-center/docs/firewall-insights/overview) — firewall rule usage and optimization.
- [Flow Analyzer overview](https://docs.cloud.google.com/network-intelligence-center/docs/flow-analyzer/overview) — analyzing VPC Flow Logs by 5-tuple.
- [Performance Dashboard overview](https://docs.cloud.google.com/network-intelligence-center/docs/performance-dashboard/overview) — inter-zone latency and packet loss.
- [VPC Flow Logs](https://docs.cloud.google.com/vpc/docs/flow-logs) — enabling, configuration, sampling, and log volume.
