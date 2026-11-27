# Google Distributed Cloud and On-Premises Deployment Requirements

## 1. Context and Objectives

In the **Hybrid and Multicloud Infrastructure** chapter of the **CLOUD_PROVIDERS_GCP** module, a common architectural question is: when should an application run in a Google Cloud region, and when must compute be placed in a customer's data center or edge location?

Enterprises may need to keep data in a specific location, process video and industrial signals with very low latency, operate during WAN interruptions, or leverage existing bare-metal/VMware investments. **Google Distributed Cloud (GDC)** is a portfolio of solutions that extends Google Cloud's Kubernetes platform, compute capabilities, and supported services into **on-premises and edge** environments.

This lesson connects with the rest of the GCP track: project organization, IAM, VPC; Compute Engine, GKE, Cloud Run; storage, databases, release automation, reliability monitoring, and cost management. GDC should be viewed through the lens of **workload placement and operational responsibility split**, not simply as an option for installing Kubernetes.

After this lesson, learners can:

1. Identify requirements for data residency, sovereignty, latency, large data volumes, intermittent internet connectivity, and reusing existing infrastructure.
2. Distinguish **GDC connected**, **GDC air-gapped**, **GDC software only for bare metal**, and **GDC software only for VMware**.
3. Map boundaries between the local data plane, management/control plane, and Google Cloud networking.
4. Plan site readiness, networking, capacity, security, backups, availability, and observability.
5. Select a deployment model aligned with compliance requirements and support models.
6. Define a POC, TCO, and practical operations plan before moving to production.

## 2. Why Do Applications Need to Run On-Premises?

### 2.1 Processing loop latency and stability

A factory uses cameras for defect detection that must return results within 50 ms. If all images must travel to a cloud region over a WAN, latency and variable jitter can violate the SLO. Processing near the cameras shortens the data path. Still, you must measure **end-to-end p95/p99 latency**, including sensor capture, LAN networking, preprocessing, inference, and response delivery.

### 2.2 High data volume where only high-value data goes to the cloud

Video, equipment logs, medical imaging, and sensor streams are generated continuously. You can process data on-site and send only metadata, alerts, statistics, and aggregated reports to Google Cloud. Document how long raw data stays on-site, where backup copies reside, and when deletion is permitted.

### 2.3 Data residency and sovereignty

- **Data residency:** the physical region/country where data is stored.
- **Data sovereignty:** control over data under specific policies, contracts, and legal frameworks.
- **Operational sovereignty:** who holds admin privileges, who controls encryption keys, who has support access, and whether external connectivity dependencies exist.

Placing a server locally does not automatically satisfy all requirements. You must also examine logs, telemetry, backups, management metadata, certificates, keys, support access, and data exchange procedures.

### 2.4 WAN connectivity is not always available

Distinguish three distinct requirements:

- Network drops for minutes/hours while local applications continue running.
- WAN can be disconnected for days, followed by syncing accumulated backlog data.
- **Zero internet or Google Cloud connectivity permitted during operation.**

These three levels lead to different choices. A product requiring periodic connectivity cannot be treated as air-gapped.

### 2.5 Leveraging existing platforms

An enterprise with Linux servers, VMware vSphere, SANs, switches, and an on-prem operations team wants to run containerized workloads on standard Kubernetes. GDC software only is worth evaluating, though it does not mean all infrastructure responsibilities shift to Google.

## 3. Four Main Deployment Variants

Google Cloud currently categorizes GDC into three solution tracks: **connected**, **air-gapped**, and **software only**; the software only track includes bare metal and VMware.

| Criterion | Connected | Air-gapped | Software only |
| --- | --- | --- | --- |
| Core | GKE clusters on Google-certified hardware on-site | Integrated infrastructure and services inside an isolated perimeter | On-prem GKE clusters on customer infrastructure |
| Hardware | Purchased through a certified systems integrator | Integrated racks or appliances per product configuration | Existing bare-metal Linux or VMware vSphere |
| Google Cloud connectivity | Required periodically for management | No Google Cloud or public internet required to operate | Fleet/management integration via Google Cloud per config |
| Platform management | Google manages the connected software | Operated inside an isolated environment per contract | Customer manages clusters/infrastructure using Google tools |
| Workloads | Containers, VMs per supported features | VMs, containers, AI/data services per catalog | Kubernetes applications; features vary by release |
| Best fit | Edge sites with WAN needing centralized management | Facilities banning external links, highly classified data | Leveraging existing on-prem hardware and skills |
| Specific risks | WAN dependency and fixed zone capacity | Offline supply chain, updates, and operations | Self-operating hardware, OS, vSphere, and upgrades |

**Never extrapolate features from one GDC variant to another.** APIs, storage, runtimes, GPU availability, software versions, AI capabilities, cluster limits, and support terms differ across variants.

### 3.1 Google Distributed Cloud connected

GDC connected runs Google Kubernetes Engine clusters on **certified servers** at the customer site, plugged directly into the local network. Cloud teams can use the Google Cloud console or Google Cloud CLI to manage zones/clusters/node pools, along with `kubectl` for workloads.

Key characteristics:

- A connected zone is typically deployed in a **three-server** configuration for availability; actual configurations and SKUs must be confirmed per version/hardware.
- Google manages the software and related monitoring operations, while the customer/SI **procures, deploys, maintains, and repairs the hardware** alongside power, cooling, and networking.
- Suits container/VM workloads needing proximity to equipment, low latency, and large local data transfers.
- Can connect to a Google Cloud VPC via **Cloud VPN** in supported architectures.
- Even though the control plane operates locally, **connected must reach Google Cloud periodically** for management, logging, tokens, and keys.

**Disconnection limit to remember:** per current Google Cloud documentation, workloads on GDC connected can continue operating while disconnected from Google Cloud for **up to seven days**. Afterward, connectivity must be restored to refresh authentication tokens, encryption keys, and management/audit sync. Connected must not be used for permanent air-gap requirements. Testing network behavior and disconnected processing capacity is a mandatory part of any POC.

GDC connected servers in a zone have **finite physical capacity**; do not treat them like an infinitely autoscaling Google Cloud region. Per installation guidelines, certified hardware is purchased through a **Google-certified systems integrator** and requires at least **Enhanced Support**. Country availability must be confirmed with Google.

### 3.2 Google Distributed Cloud air-gapped

GDC air-gapped is designed for environments with strict physical and logical isolation requirements, **independent of Google Cloud or internet connectivity** during operation. It is an integrated hardware-and-software solution typically placed in a controlled data center, alongside appliance variants for specialized edge scenarios.

Key points:

- The system includes management, networking, identity, storage, workloads, and a service catalog **within an isolated perimeter**.
- The scope of VMs, containers, AI/ML, and other services must be confirmed against the specific GDC air-gapped release rather than assumed identical to public Google Cloud.
- Updates, images, artifacts, and data entering the isolated zone must pass through **intake, malware scanning, signature/hash verification, and approval workflows**.
- Authorization policies, data classification, media controls, key management, and logging must operate even without internet access.
- A site survey covering racks, power, cooling, physical security, and operational readiness is a formal design step.

Beyond data-center racks, the **GDC air-gapped appliance** targets portable/field scenarios with different HA, capacity, and operational limits. Never assume an appliance can replace a fully redundant data-center cluster.

**Do not confuse:** disconnecting the internet on a GDC connected cluster does not turn it into GDC air-gapped.

### 3.3 GDC software only on bare metal

GDC software only for bare metal provides an on-prem GKE platform running Kubernetes directly on customer Linux machines, avoiding a hypervisor layer when direct hardware access is needed or when a bare-metal operations team already exists.

The model typically uses an **admin cluster** to manage the lifecycle of **user clusters** running applications. Customers design IP addressing, load balancers, storage, networking, OS, hardware, and resilience, connecting **Fleet/Connect Agent** for centralized management features via Google Cloud.

Primary cluster data and workloads stay in the on-prem data center. Documentation notes that Google Cloud receives certain cluster data—such as metadata, health, and usage—for management purposes, rather than automatically uploading all application data to the cloud.

GDC software only was previously named **Google Distributed Cloud Virtual** and earlier **Anthos clusters on bare metal**. Cross-check versions carefully when reading older docs.

### 3.4 GDC software only on VMware

The VMware track runs Kubernetes nodes inside virtual machines on the organization's **vSphere** environment. It uses vSphere datastores (vSAN, VMFS, or NFS as supported) and the **vSphere CSI driver** to provision persistent volumes for stateful applications.

Typical components include admin clusters, user clusters, admin workstation, load balancers/VIPs, storage classes, vCenter configuration, fleet memberships, and tools like `gkectl` and `kubectl`.

Its strength is reusing vCenter expertise, SAN/vSAN infrastructure, and established change management. The trade-off is managing two layers—**vSphere/VMs and Kubernetes**—plus compatibility matrices across GDC versions, vSphere, networking, storage, firmware, and certificates.

**Software only is also not air-gapped by default.** Management/fleet features have their own connectivity requirements; verify against documentation for your exact version.

## 4. Hybrid Reference Architecture

~~~mermaid
flowchart LR
    subgraph SITE["On-premises factory / data center"]
      DEV["Cameras, sensors, machinery"] --> GW["LAN network gateway"]
      GW --> APP["GDC workload: real-time processing"]
      APP --> LOCAL[("Local storage / database")]
      APP --> QUEUE["Durable queue + checkpoint"]
    end
    QUEUE -->|"Authorized data only when WAN is up"| LINK["Secure connection / VPN"]
    LINK --> CLOUD["Google Cloud VPC / target services"]
    CLOUD --> DWH[("Cloud Storage / BigQuery")]
    MGT["Google Cloud management: connected/software only where applicable"] -.-> APP
~~~

The architecture separates two flows:

- **Data plane:** devices send data to the on-site application; results are processed, stored, or shipped outward per policy.
- **Management plane:** Google Cloud can manage/monitor GDC connected or software only per the product and configured connectivity.

In **air-gapped**, the management plane must stay inside the isolated environment. There is no always-on VPN to Google Cloud. Importing/exporting data or updates requires approved offline workflows.

### Data classification and placement

| Data | Example | Decisions required |
| --- | --- | --- |
| Raw | Video, medical images, telemetry | Must it stay local? What retention period? |
| Results | Defect alerts, metadata, aggregates | Which cloud region may receive them? |
| Management | Cluster metadata, health, billing usage | Which channel goes out to Google Cloud? |
| Logs/audit | User activity, admin access | Does it contain PII/secrets and where must it reside? |
| Artifacts | Container images, ML models, SBOMs | Online registry or offline import? |
| Keys and certificates | TLS keys, KMS, secrets | Who manages, backs up, rotates, and recovers them? |

**Running on-prem** does not automatically mean "zero bits ever leave the site" if management telemetry, support access, or logs are still transmitted externally.

## 5. Product Selection Workflow by Requirement

~~~mermaid
flowchart TD
    A["Application requires on-premises deployment"] --> B{"Are Google Cloud/internet links forbidden during operation?"}
    B -- "Yes" --> G["Evaluate GDC air-gapped"]
    B -- "No" --> C{"Want to reuse existing hardware?"}
    C -- "Bare metal" --> BM["GDC software only for bare metal"]
    C -- "VMware" --> VM["GDC software only for VMware"]
    C -- "No" --> D{"Accept periodic Google Cloud management?"}
    D -- "Yes" --> CON["GDC connected"]
    D -- "No" --> RE["Revisit requirements; consider air-gapped"]
    G --> P["POC and evaluate security, TCO, support"]
    BM --> P
    VM --> P
    CON --> P
    RE --> P
~~~

| Problem | First track to evaluate | Critical prerequisites |
| --- | --- | --- |
| Factory camera inference with reasonably stable WAN | Connected | Certified hardware procurement, periodic management link accepted |
| Data requiring total isolation from external networks | Air-gapped | Offline operations readiness, site survey, update pipeline |
| Enterprise with strong VMware infrastructure | Software only VMware | Compatible vSphere version, CSI, load balancer, and storage |
| Linux bare-metal servers across multiple sites | Software only bare metal | OS, firmware, networking, and hardware meet requirements |
| Only need on-prem connectivity to cloud workloads | Cloud VPN/Interconnect and GCP | Do you actually need Kubernetes on-site? |
| Cloud-native apps with no locality requirement | GKE/Cloud Run/Compute Engine in region | Avoid unnecessary on-prem cost and operational overhead |

Do not choose air-gapped merely because WAN is weak; it is an entirely different operational and contractual model. Conversely, connected does not satisfy strict absolute isolation requirements.

## 6. Pre-Deployment Site Readiness

The architecture team needs a **site readiness checklist**:

1. **Space:** rack units, floor load capacity, maintenance clearance, cable pathways.
2. **Power:** UPS, PDUs, wattage, redundant feeds, power-loss procedures.
3. **Cooling:** HVAC, temperature, humidity, environmental monitoring.
4. **Networking:** switches, VLANs, DNS, NTP, MTU, CIDRs, routes, firewalls, uplinks/VPN.
5. **Physical security:** rack access control, audit logs, cameras, asset tracking.
6. **Operations:** NOC, SOC, on-call, spare-part replacement procedures, SI/Google contacts.
7. **End-of-life plan:** data export, drive sanitization, hardware return, contract closure.

For connected, engage Google/partners before purchasing to confirm **certified configurations, country availability, support**, and zone scalability limits. For air-gapped, evaluate supportability in a restricted facility and supply chain workflows. For software only, the internal team must verify hardware, OS or vSphere, and storage/networking themselves.

### Sample network design document

~~~yaml
# Illustrative example for discussing with the network team, NOT a valid GDC manifest.
site_id: factory-01
local_cidr: 10.40.0.0/16
management_subnet: 10.40.10.0/24
workload_subnet: 10.40.20.0/24
storage_subnet: 10.40.30.0/24
dns: dns.factory-01.example
ntp: ntp.factory-01.example
connectivity: controlled-vpn
~~~

Before deployment, add Pod/Service CIDRs, VIPs, load balancers, ingress, routes to OT/VPC, and prevent CIDR overlaps across sites. Cluster configurations must follow the **exact schema of the GDC track and version**, never feeding conceptual examples like this straight into an installer.

## 7. Compute Capacity, HA, and Edge Redundancy

An edge zone has **hard physical limits** on CPU, RAM, GPU, disk, and IOPS. Never mistake Pod autoscaling for instant server provisioning. When sizing, account for:

- Normal daily traffic, p95/p99 peaks, seasonal spikes, and 12–24 month growth.
- Resources reserved for Kubernetes system components, control plane, and monitoring.
- Ability to lose a node while still serving critical load.
- Local storage throughput and capacity for both raw data and sync backlogs.
- Power feeds, switches, racks, LAN, and HVAC as distinct **failure domains**.
- Hardware procurement/replacement lead times, RTO/RPO, and tested backups.

Two Pods running on the same node do not provide real HA. Replicas, topology spread, anti-affinity, local storage, failover, and power-outage behavior must be designed together.

GDC connected deploys zones on certified hardware with fixed limits; do not assume you can arbitrarily add nodes once a zone is live. Capacity headroom must be planned from the design phase.

## 8. Security and Shared Responsibility

### 8.1 Identity and access

In connected/software only, management-plane Google Cloud permissions can be paired with **Kubernetes RBAC**, ServiceAccounts, namespaces, and network policies. In air-gapped, IAM/identity operates inside the perimeter and can integrate with supported on-premises identity systems.

Never grant broad `cluster-admin` to every operator; separate infrastructure, security, application, and emergency recovery accounts.

### 8.2 IT/OT segmentation

Cameras, PLCs, and robots on OT networks must be segmented from cluster management and IT application networks. Open only explicitly designed ports and traffic directions. With connected, configure firewall rules for the Google Cloud management channel and VPN when used; never allow all Pods unrestricted internet access by default.

With air-gapped, removable media, model files, and image registries are entry points for software and data. Enforce **source verification, signatures, hashes, malware scanning, SBOMs, licensing, and audit trails** before ingestion.

### 8.3 Encryption and key management

On-premises data may require storage encryption, service-to-service TLS, secret management, certificate rotation, and backup access controls. GDC connected supports **CMEK on local storage** for applicable configurations, involving Cloud KMS. This can introduce dependencies on key-refresh intervals and network reachability; test disconnection scenarios carefully.

GDC air-gapped uses key management suited to isolated environments; never assume a disconnected system can call public Cloud KMS.

### 8.4 Compliance

Audit elements include data location, cluster metadata, logs, support access, remote access, backups, media sanitization, key storage, and supply chain. Compliance conclusions require evidence from configurations, contracts, and formal assessments; **simply placing hardware inside a country is not sufficient proof**.

## 9. Operational Responsibilities

| Activity | Connected | Air-gapped | Software only |
| --- | --- | --- | --- |
| Racks, power, cooling, LAN | Customer | Customer / site operator | Customer |
| Hardware and repairs | Customer/SI with certified hardware | Per integrated solution contract | Customer |
| Software platform | Remotely managed by Google per product | Operated inside perimeter per service/contract model | Customer manages clusters/versions with Google tools |
| Data backup/restore | Customer | Designed per site requirements | Customer |
| Workload configuration | Application owner/customer | Application owner inside isolated environment | Customer |
| Application IAM and network policies | Customer | Customer | Customer |
| WAN availability | Customer | No Google Cloud WAN needed to run | Customer for management features needing network |

**Warning from connected documentation:** Google or SIs cannot guarantee local data recovery if hardware fails; **the customer is responsible for recoverable backups**. Copies must be tested periodically and exported off-device prior to hardware return or sanitization per contract.

For connected, alert on time elapsed since the last Google Cloud check-in; the seven-day threshold is a documented operational limit, not an application uptime promise. For software only, test the impact of losing internet access on fleet/management for your exact version rather than extrapolating connected limits across all products.

## 10. Deploying Applications to the Cluster: Kubernetes Example

Once a GDC cluster is provisioned and you have a valid kubeconfig, application teams use standard Kubernetes workflows. Simple example creating a defect-detection API in its own namespace:

~~~yaml
apiVersion: v1
kind: Namespace
metadata:
  name: factory-analytics
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: anomaly-api
  namespace: factory-analytics
spec:
  replicas: 2
  selector:
    matchLabels:
      app: anomaly-api
  template:
    metadata:
      labels:
        app: anomaly-api
    spec:
      containers:
        - name: api
          image: registry.factory.example/anomaly-api:v1
          ports:
            - containerPort: 8080
          resources:
            requests:
              cpu: 250m
              memory: 256Mi
            limits:
              cpu: "1"
              memory: 512Mi
          readinessProbe:
            httpGet:
              path: /ready
              port: 8080
            periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: anomaly-api
  namespace: factory-analytics
spec:
  selector:
    app: anomaly-api
  ports:
    - port: 80
      targetPort: 8080
~~~

This is an **application example**, not a GDC cluster creation manifest. `registry.factory.example` must be replaced with an existing registry; the `/ready` endpoint must be served by the app. For air-gapped, images must be imported into the internal registry through vetted verification workflows.

Verify in a test environment:

~~~bash
kubectl config current-context
kubectl get nodes
kubectl apply -f anomaly-api.yaml
kubectl -n factory-analytics get deployments,pods,services
kubectl -n factory-analytics rollout status deployment/anomaly-api
~~~

Always confirm the Kubernetes context to avoid writing to production by mistake. A default Service is cluster-internal only; access from cameras/LAN requires ingress, load balancers, and firewalls matching your product track. Two replicas are only a starting point—add topology spread/anti-affinity and real node redundancy.

## 11. Local-First Design, Data Sync, and Disconnection Handling

A typical design includes:

1. Sensors/cameras send data to the local application.
2. The app writes raw data to local storage per retention rules.
3. Workers generate inference results, alerts, and aggregates.
4. A durable queue holds unsent events.
5. When connectivity is permitted, workers push events to the target cloud, confirm acknowledgment, and advance checkpoints.
6. On failure, apply bounded retries, dead-lettering, or alerting; use event IDs to prevent duplicate writes.

Never assume WAN delivery provides **exactly-once** semantics. Design idempotent consumers, deduplication keys, timestamps, site IDs, and late-arriving event rules.

### Calculating backlog capacity

Suppose filtered events/metadata requiring sync total **15 GB/day**, WAN outage lasts **4 days**, plus a **30% buffer**:

~~~text
Backlog = 15 GB/day × 4 days = 60 GB
Buffer = 60 GB × 30% = 18 GB
Illustrative minimum capacity = 78 GB
~~~

This is a logical calculation before accounting for replicas, filesystem overhead, WALs, retention, and new data arriving while draining the backlog after WAN recovery. Production sizing must measure read/write throughput, IOPS, and worst-case scenarios.

### Backup boundaries

Define RPO/RTO, backup destinations, and scheduled restore drills. For single-site deployments, replicate backups to an independent location if protection against fire, prolonged power loss, or full-rack failure is required. Air-gapped deployments need backup mechanisms that uphold isolation policies and media controls.

## 12. Observability and SRE Operations

| Category | Metrics or logs | Value |
| --- | --- | --- |
| App | p50/p95/p99 latency, error rate, inference quality | Proves local SLO compliance |
| Kubernetes | Node conditions, pod restarts, readiness, rollouts | Detects cluster/workload failures |
| Hardware | Temperature, CPU, RAM, SSD health, power | Prevents outages from physical resources |
| Network | RTT, jitter, packet loss, VPN status, reconnect age | Detects WAN issues and tracks disconnected limits |
| Data | Queue depth, retries, sync lag, dead-letters | Prevents data loss and buildup |
| Security | Login logs, RBAC changes, image provenance | Supports auditing and incident response |
| DR | Backup freshness, restore tests, spare capacity | Verifies real recoverability |

For air-gapped, **local observability and alerting** are mandatory; never rely on dashboards accessible only over the internet. For connected/software only, integrate Google Cloud monitoring per version capabilities, while keeping site-level alerts active when WAN drops.

Never rely solely on averages across all factories; one site with terrible p99 latency can be masked by healthy sites.

## 13. TCO and Procurement Decisions

Total Cost of Ownership (TCO) for GDC spans multiple layers:

- Hardware: servers/racks/SSDs/GPUs, replacement parts, spare units.
- Data center: power, UPS, HVAC, racks, floor space, physical security.
- Networking: LAN, VPN/Interconnect, redundant WAN, data transfer.
- Software/support: GDC, VMware/OS if applicable, support tiers, SI and deployment services.
- Operations: on-site on-call staff, upgrades, SOC, audits, backups, and DR drills.
- Risk costs: downtime, spare-part shortages, weak WAN links, hardware replacement lead times.
- Cloud integration: Cloud Storage, BigQuery, processing, result storage, and network charges per actual usage.

| Option | Strengths | Aspects to evaluate |
| --- | --- | --- |
| Public Google Cloud region | Elasticity, managed infrastructure | WAN latency, data movement, residency rules |
| GDC connected | Local compute, Google management, Kubernetes | Certified hardware, SI, support, and reconnection |
| GDC air-gapped | Operational isolation, sovereign data | Offline cost/complexity, service catalog, and site prep |
| GDC software only | Reuses bare metal/VMware, unified workflow | Internal team manages OS/vSphere, cluster, storage |
| Self-managed Kubernetes | Full stack autonomy | Self-integration and full operational ownership |

Pricing and procurement terms vary by country, scale, configuration, and contracts; air-gapped typically requires contacting Google for quotes. Never treat public cloud VM unit pricing as the total on-prem TCO.

## 14. POC Plan With Acceptance Criteria

### Step 1: Define requirements

Document sites, workloads, sensor counts, data retention, p99 SLOs, WAN bandwidth, maximum offline duration, RTO/RPO, compliance requirements, budget, and accountable owners.

### Step 2: Select a GDC candidate

Verify hardware, country availability, release/version, SKUs, storage, networking, licensing, and support tiers. For air-gapped, verify image/update intake workflows; for connected, verify reconnection procedures.

### Step 3: Build a pilot deployment

Stand up a cluster in an environment without real production data, deploy a representative workload, feed simulated data, and configure metrics, logs, backups, IAM/RBAC, and network policies.

### Step 4: Failure injection

- Controlled WAN outage and recovery, measuring service disruption and backlog drain.
- Loss of a node, loss of an internal network path, or resource constraints.
- Peak load test verifying p99 latency.
- Restore data from clean backups into a test environment.
- For air-gapped, execute an offline image/model version import.
- For connected, test disconnection-duration tracking and token/key refresh.

### Step 5: Go/no-go

Expand only if all defined criteria pass: performance, availability, backups, security, data-movement approvals, cost, hardware availability, and on-call staffing.

## 15. Case Study: Camera System Across 20 Factories

A company operates 20 factories with 40 cameras each. Video feeds are analyzed for product defects; the system must respond in **under 80 ms**. Raw video is retained locally for 14 days; only defect events, defect rates, and statistics are sent to Google Cloud for long-term analytics.

Surveyed approach:

1. **On-site:** ingest video, run inference, log results, and store video per retention rules.
2. **GDC connected** at sites with WAN and certified hardware support; **software only** where suitable bare-metal/VMware clusters and skilled ops teams already exist.
3. **Networking:** segment cameras/OT, workloads, and management; design local ingress and required firewalls.
4. **Cloud:** sync metadata in a controlled manner to Cloud Storage or BigQuery depending on the pipeline, never sending raw video unless contracts permit.
5. **Availability:** node redundancy, independent backups, offline queues, and alerts on time since last connection.
6. **Governance:** measure p99 latency, delayed events, sync errors, disk fullness, and recovery rates.
7. **Sites strictly banned from internet connectivity:** branch the design to evaluate **GDC air-gapped** with a dedicated update supply chain; never take a connected design and permanently sever its WAN.

Mistakes to avoid: treating two Pods on the same node as HA; skipping local backups; not testing WAN outages; assuming every public Google Cloud service exists in GDC air-gapped; and omitting power, SI, support, and hardware replacement costs.

## 16. Pre-Production Checklist

- [ ] Reasons for local placement quantified: latency, sovereignty, data volume, or resilience on weak WANs.
- [ ] Properly distinguished connected, air-gapped, software only bare metal, and VMware.
- [ ] Diagrams cover data plane, management plane, data classification, and data-transfer paths.
- [ ] Site readiness verified: racks, power, UPS, HVAC, switches, DNS, NTP, IP addressing, and physical security.
- [ ] Product, version, hardware, country availability, and contracts confirmed.
- [ ] Capacity includes headroom for node loss without assuming infinite scaling.
- [ ] IAM/RBAC, network segmentation, image provenance, and secret management designed.
- [ ] Application data backups are recoverable and DR drills have been executed.
- [ ] For connected: alerts, reconnection runbooks, and offline-limit policies exist.
- [ ] For air-gapped: offline update, scanning, media sign-off, and audit procedures exist.
- [ ] Monitoring and alerting keep working when internet access is lost.
- [ ] TCO, support responsibilities, and hardware lifecycle plans are in place.

## 17. Key Takeaways

GDC extends Google Cloud infrastructure and services to data centers and edge sites, yet it is **not a single product with one uniform feature set**. **Connected** runs workloads near data sources on certified hardware, managed via Google Cloud with periodic connectivity requirements. **Air-gapped** serves completely isolated environments. **Software only** brings on-prem GKE to customer-managed bare metal/VMware.

The right choice depends on data, networking, latency, operations, HA, security, support, and TCO requirements—not merely the ability to run Kubernetes.

## Official Google Cloud Documentation

1. [Google Distributed Cloud — solution portfolio](https://docs.cloud.google.com/distributed-cloud/docs)
2. [GDC connected — overview](https://docs.cloud.google.com/distributed-cloud/connected/latest/docs/overview)
3. [GDC connected — how it works](https://docs.cloud.google.com/distributed-cloud/connected/latest/docs/how-it-works)
4. [GDC connected — requirements](https://docs.cloud.google.com/distributed-cloud/connected/latest/docs/requirements)
5. [GDC connected — deploy workloads](https://docs.cloud.google.com/distributed-cloud/connected/latest/docs/deploy)
6. [GDC connected — availability and backup](https://docs.cloud.google.com/distributed-cloud/connected/latest/docs/availability)
7. [GDC air-gapped — overview](https://docs.cloud.google.com/distributed-cloud/hosted/docs/latest/gdcag/overview)
8. [GDC air-gapped — infrastructure and network security](https://docs.cloud.google.com/distributed-cloud/hosted/docs/latest/gdcag/security-infrastructure-network)
9. [GDC air-gapped appliance — overview](https://docs.cloud.google.com/distributed-cloud/hosted/docs/latest/appliance/overview)
10. [GDC software only for bare metal — overview](https://docs.cloud.google.com/kubernetes-engine/distributed-cloud/bare-metal/docs/concepts/about-bare-metal)
11. [GDC software only for VMware — overview](https://docs.cloud.google.com/kubernetes-engine/distributed-cloud/vmware/docs/overview)
12. [GDC software only for VMware — installation overview](https://docs.cloud.google.com/kubernetes-engine/distributed-cloud/vmware/docs/how-to/install-overview)
