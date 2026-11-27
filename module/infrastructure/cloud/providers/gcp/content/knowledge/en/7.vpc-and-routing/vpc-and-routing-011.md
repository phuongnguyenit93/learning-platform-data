# Cloud NAT and Outbound Connectivity for Private Resources

In Google Cloud, a Compute Engine VM with only an internal IP address may still need to download OS packages, call a payment provider's API, or send data to external services. Similarly, private GKE nodes or Cloud Run applications may need **outbound connectivity (egress)** without exposing a dedicated public IP address for each workload. **Cloud NAT** provides an address translation mechanism to support such connections without turning the VM into a public entry point from the Internet.

This lesson belongs to the **VPC and Routing** chapter of the `CLOUD_PROVIDERS_GCP` module. These concepts connect project organization, IAM, and VPCs with deploying Compute Engine, GKE, Cloud Run, storage, and databases; while helping learners select the right networking solution, protect resources, automate releases, and monitor reliability as well as cost.

The content focuses on **Public NAT for privately addressed resources to reach the Internet**; the end of the lesson introduces **Private NAT** so you do not confuse the two NAT types provided by Google Cloud.

## Learning Objectives

After this lesson, you will be able to:

1. Explain why VMs without external IPs still need egress and what problem Public NAT solves.
2. Describe **SNAT** flows for outbound packets and **DNAT** for return packets, and explain why Cloud NAT does not allow unsolicited inbound connections from outside.
3. Distinguish Cloud NAT, Cloud Router, VPC routes, firewalls, DNS, Private Google Access, and Private Service Connect.
4. Design NAT scope by **VPC, region, subnet, and primary/secondary IP ranges**.
5. Practice configuring Public NAT for Compute Engine via Console or `gcloud`.
6. Apply the right model with GKE and Cloud Run, especially static egress IP requirements when third parties require allowlisting.
7. Troubleshoot routing errors, missing egress permissions, NAT port exhaustion, and monitor operational costs.

## 1. Starting Scenario: A Private VM Needs to Download Updates

The Commerce team places an order-processing VM in a private subnet of project `atlas-commerce-dev`:

- VM internal address: `10.20.0.10`.
- VM **has no external IPv4 address**.
- VM needs to call a public HTTPS service to retrieve update information.
- The team does not want to assign an external IP directly to the VM because the VM does not serve inbound Internet requests.

Merely creating a subnet and VM does not guarantee the VM can reach the Internet. Traffic must be **routed** to the appropriate destination, **egress firewalls** must permit it, and the VM's private source address must be **translated to a public address** for IPv4 Internet traffic. Public NAT handles source address translation.

~~~mermaid
flowchart LR
    VM["Private VM<br/>10.20.0.10<br/>No external IP"]
    SUB["Subnet 10.20.0.0/24"]
    NAT["Public NAT<br/>Shared external IP"]
    WEB["External API<br/>HTTPS :443"]
    VM --> SUB
    SUB -->|"Route + egress firewall allow"| NAT
    NAT -->|"SNAT: public IP/port"| WEB
    WEB -. "Reply for established connection" .-> NAT
    NAT -. "DNAT back to internal IP" .-> VM
~~~

This diagram shows the **logical flow**. In reality, Cloud NAT is a distributed service implemented in Google Cloud's virtual network fabric; **packets do not pass through a NAT gateway VM or Cloud Router as a forwarding hop**.

### 1.1. Why Not Attach an External IP to Every VM?

You can attach an external IP to a VM if a workload truly needs it, but that model differs significantly:

| Option | Outbound connection source | Considerations |
| --- | --- | --- |
| VM with external IP | VM uses Google Cloud's one-to-one NAT for its primary internal IP when route conditions are met | Has its own public address; must control ingress/egress firewalls |
| VM with internal IP only + Public NAT | Uses Public NAT's external IP/port pool | Reduces external IP usage per VM; disallows unsolicited inbound connections via NAT |
| VM with internal IP only + Private Google Access | Reaches supported Google APIs/services when the network is properly configured | Not a way to reach arbitrary Internet websites or APIs |
| VM with internal IP only, no NAT and no matching egress path | No standard IPv4 Internet path from the VM | Can still access private resources/other VPCs if routes and links exist |

**A private IP does not mean a VM is completely secure.** The VM still needs IAM, OS patching, proper firewalls, internal access rules, and monitoring.

## 2. What Is Cloud NAT? Public NAT and Private NAT

**Cloud NAT (Network Address Translation)** is a Google Cloud-managed service that translates network addresses for outbound flows from supported resources. Google Cloud provides two main types:

| Type | Target use | Translated address | Example |
| --- | --- | --- | --- |
| **Public NAT** | Outbound traffic to the Internet or public IPv4 targets per supported conditions | External IP of the NAT gateway | Private VM downloading packages from a public repo; Cloud Run calling a partner API via static IP |
| **Private NAT** | Traffic from one private network to another private network over supported connections | IP from a configured Private NAT range | Inter-VPC or hybrid connections requiring IP range translation |

Each NAT gateway is configured for **one NAT type**. Two separate gateways can serve Public NAT and Private NAT purposes on appropriate subnets. Never treat Private NAT as a variant of Public NAT for reaching the Internet: targets, IP ranges, and routing differ.

Cloud NAT supports multiple translation modes, with **NAT44** (IPv4 → IPv4) being the primary focus of this lesson. Some configurations support **NAT64** (IPv6 → IPv4), though support scope varies by workload and NAT type; consult official documentation when deploying IPv6.

### 2.1. Is Cloud Router a Router Forwarding NAT Packets?

**No.** When creating Public NAT, you attach the NAT configuration to a **Cloud Router** in the same VPC and region. Cloud Router provides the **control plane** for NAT; it does not become a data-plane appliance processing every Internet packet, and Public NAT **does not require BGP** to operate.

Distinguish clearly:

- **Cloud Router** can use BGP to exchange dynamic routes in hybrid setups like Cloud VPN/Interconnect; when serving NAT, Cloud Router's role is storing/managing configuration.
- **VPC routes** determine the next hop for packets.
- **Cloud NAT** translates addresses/ports for traffic matching the route and NAT scope.
- **Firewall rules** decide whether connections are allowed or blocked.

Therefore, creating a Cloud Router and NAT **does not automatically create a default route** and does not open egress firewalls.

## 3. How Is an Outbound Connection NATted?

Suppose a VM opens a TCP connection:

~~~text
Source before NAT:
  10.20.0.10:51520  ->  198.51.100.20:443

Example after Public NAT translation:
  <NAT_EXTERNAL_IP>:30011  ->  198.51.100.20:443

Return packet:
  198.51.100.20:443  ->  <NAT_EXTERNAL_IP>:30011

After reverse translation for the established connection:
  198.51.100.20:443  ->  10.20.0.10:51520
~~~

`198.51.100.20` belongs to a documentation-reserved address range; `<NAT_EXTERNAL_IP>` denotes the actual public IP allocated or used by Cloud NAT. Port 30011 is illustrative only. Cloud NAT manages source and port mappings so connections remain distinguishable.

### 3.1. SNAT, DNAT, and Connection Tracking

1. The VM sends a packet to a public address.
2. The VPC selects a route with an appropriate next hop; egress firewalls are evaluated on the source side.
3. Public NAT replaces the internal **source IP** with the gateway's external IP and uses an allocated source port as needed (**SNAT**).
4. The external Internet server sends a reply back to the observed external IP/port.
5. NAT recognizes the reply as belonging to a valid connection and rewrites the destination address/port back to the VM (**DNAT**).

If an external client initiates a brand-new request to Cloud NAT's external IP **without an existing connection mapping**, Public NAT does not act as a mechanism to open inbound service ports. It only translates replies for connections initiated from inside.

> **Key point:** Public NAT does not replace an external Application Load Balancer, inbound proxies, VPNs, or VM admin access methods like IAP TCP forwarding. NAT handles only configured egress translation.

### 3.2. Why Do Ports Matter?

Many VMs, nodes, or containers may share a single pool of NAT external IPs. Cloud NAT allocates **source ports** to differentiate concurrent flows. If concurrent connections, connection creation rates, or traffic patterns exceed allocated ports, applications can suffer outbound connection failures.

Cloud NAT lets you configure parameters such as **minimum ports per VM**, **maximum ports per VM** when using dynamic port allocation, NAT IP counts, and timeouts. Do not raise values blindly; inspect metrics/logs to pinpoint bottlenecks, consider **connection pooling/reuse**, allocate additional IPs, or optimize workloads.

## 4. Prerequisites for Public NAT to Enable Egress

A VM without an external IP can reach the Internet through Public NAT when all relevant conditions hold:

| Condition | Valid example | What happens if wrong? |
| --- | --- | --- |
| **VPC/subnet/region** | VM resides in a regional subnet served by the gateway | NAT does not apply to the VM |
| **Source IP scope** | Primary internal IP or alias/secondary IP range enabled in NAT per supported cases | That specific traffic type is not translated |
| **Route** | Matching route to destination has **default internet gateway** as next hop | Packets do not follow the path served by Public NAT |
| **Egress firewall** | VPC/VM rules allow TCP 443 traffic to the destination | Packets are dropped before NAT |
| **DNS** | Public domain name resolves properly | Hostname-based connections fail even though NAT is healthy |
| **NAT IP/port capacity** | Enough external IPs and source ports available | New connections may be dropped or fail |
| **Service policy** | Partner API accepts the client and egress IP | May get HTTP 403/401 from the application despite working networking |

For **Public NAT**, the routes NAT uses must have **default internet gateway** as their next hop. A `0.0.0.0/0` route is normally pre-created in VPCs and satisfies this requirement. But if that route is deleted, replaced, or shadowed by a higher-priority route sending traffic to an appliance/VPN, Cloud NAT may not be invoked.

### 4.1. NAT Does Not Bypass Firewalls

In a VPC with an egress rule blocking all Internet traffic, creating a NAT gateway does not override that block. Google Cloud evaluates egress firewalls at the source NIC before NAT. Having a default route and NAT IP **does not mean every destination is reachable**.

Design guidelines for applications calling partner APIs:

- Allow only genuinely needed protocols/ports and destinations (e.g., HTTPS TCP 443) per rule/policy capabilities.
- Restrict sources using network tags, service accounts, or appropriate firewall mechanisms.
- For granular domain/HTTP inspection, consider a **proxy or egress filtering solution**; NAT does not inspect or approve application URLs.
- Use separate IAM controls for Google Cloud APIs; NAT does not determine request IAM.

### 4.2. NAT Does Not Provide DNS Itself

If `curl https://api.example.com` reports failing to resolve the domain name, inspect **Cloud DNS/resolvers, DNS forwarding, and DNS policies** first. NAT can only process IP flows once the client resolves a destination IP and has an appropriate route.

## 5. VPCs Are Global, Yet Cloud NAT Is Configured per Region

A VPC network is a **global** resource, whereas subnets live in a **region**. Each Public NAT gateway is tied to **one VPC, one region, and one Cloud Router**.

~~~mermaid
flowchart TD
    VPC["VPC: commerce-vpc (global)"]
    A["Subnet: commerce-private-a<br/>asia-southeast1"]
    B["Subnet: commerce-private-b<br/>asia-southeast1"]
    C["Subnet: commerce-private-us<br/>us-central1"]
    NA["Public NAT: nat-asia<br/>asia-southeast1"]
    NU["Public NAT: nat-us<br/>us-central1"]
    VPC --> A
    VPC --> B
    VPC --> C
    NA -. "Serves selected subnet" .-> A
    NA -. "Can serve" .-> B
    NU -. "Serves if configured" .-> C
~~~

You cannot use a gateway in `asia-southeast1` to directly serve a subnet in `us-central1`. When operating across multiple regions, design corresponding NAT gateways in each region needing egress.

### 5.1. Selecting Which IP Ranges Receive NAT

When creating Public NAT, you can choose:

| Selection | Meaning | When to use |
| --- | --- | --- |
| **All primary and secondary ranges** | NAT serves primary/secondary IP ranges of all subnets in the VPC region | Small labs or designs permitting all workloads in the region outbound |
| **Primary ranges of all subnets** | Only primary IP ranges of all subnets in the region | When alias/secondary ranges do not need NAT |
| **Custom subnet IP ranges** | Only specified subnets and primary/secondary ranges | Production needing explicit control over permitted subnets |
| **A custom subnet by name only** | Only the **primary range** of that subnet | VMs using primary internal IPs |
| **Custom subnet with `:ALL`** | Both primary and secondary ranges of the subnet | When GKE/alias IPs require secondary range support |

**Do not blindly select all subnets** in an enterprise project if only one workload needs egress. NAT scope expands outbound surface area and can affect cost governance.

### 5.2. Do Compute Engine VMs with External IPs Go Through Public NAT?

For packets from the **primary internal IP** of a NIC that already has an external IP, Google Cloud normally performs the NIC's own one-to-one NAT; Public NAT **does not replace** that egress source. Certain flows from **alias IP ranges** may still fall under NAT depending on configuration. When testing, verify the exact source IP of packets and resource type to avoid falsely concluding NAT is handling the traffic.

## 6. How Public NAT Differs from Other Connectivity Mechanisms

| Mechanism | Goal | Key difference |
| --- | --- | --- |
| **Public NAT** | Translates addresses for egress from private resources to public IPv4 targets | Does not open unsolicited inbound access |
| **Private NAT** | Translates addresses for private-to-private connections over supported routes/links | Not intended for general Internet egress |
| **Private Google Access** | Lets internal-IP-only VMs reach supported Google APIs/services | Not for reaching arbitrary Internet websites |
| **Private Service Connect** | Accesses published services via private endpoints/backends in a VPC | Not a general NAT gateway for all Internet traffic |
| **Cloud VPN/Interconnect** | Connects a VPC to external/on-premises networks via hybrid mechanisms | Does not replace Public NAT |
| **Cloud Load Balancing** | Receives and distributes traffic to backends (per LB type) | Handles inbound/forwarding per config, distinct from NAT egress |
| **IAP TCP forwarding** | Provides controlled administrative access to VMs without public IPs | Not Internet egress for applications running on VMs |
| **External proxy/egress firewall** | Enforces application, URL, or advanced policy controls | Can complement NAT if deep traffic inspection is required |

### 6.1. Do Private VMs Need Cloud NAT to Call Google Cloud APIs?

**Not necessarily.** For Compute Engine VMs without external IPs, **Private Google Access** can provide access to supported Google APIs/services. Depending on the service and design, Private Service Connect is also an option.

For example, a private VM only needs to download objects from Cloud Storage. Before deploying Public NAT, evaluate **Private Google Access** and appropriate IAM/service accounts. If the VM also needs to download packages from an external software repository outside Google, Public NAT may still be needed for that Internet path.

This prevents deploying Cloud NAT everywhere simply because a destination has a Google domain name. **DNS, routes, IP ranges, and service mechanisms** must still be verified for the chosen connectivity option.

## 7. Hands-On: Creating a VPC and Public NAT for a Private VM

This lab uses a VM in region `asia-southeast1` (Singapore) with an internal IP, a private subnet, Cloud Router, and Public NAT. **Commands creating VMs, NAT gateways, and external IPs can incur charges**; perform only in an authorized lab project with a budget and cleanup procedure. Names/addresses are illustrative and must be checked for availability in your project.

### 7.1. Verify Project and Permissions

~~~bash
gcloud auth list
gcloud config set project PROJECT_ID
gcloud config get-value project
gcloud services enable compute.googleapis.com --project=PROJECT_ID
~~~

Required permissions may include creating networks, subnets, VMs, routers/NAT, and managing IP addresses; use appropriately scoped roles instead of granting Owner unnecessarily. The CLI must be authenticated with an authorized account, and the project linked to billing when required by services.

### 7.2. Create Custom Mode VPC and Subnet

~~~bash
# Create a new VPC to isolate lab scope
gcloud compute networks create nat-lab-vpc \
  --subnet-mode=custom \
  --project=PROJECT_ID

# Create a subnet in the target region
gcloud compute networks subnets create nat-lab-private \
  --network=nat-lab-vpc \
  --region=asia-southeast1 \
  --range=10.20.0.0/24 \
  --project=PROJECT_ID
~~~

When creating a custom subnet, ensure the CIDR does not overlap any range already used in the VPC. If you want to reach Google APIs from private VMs without relying on NAT, consider enabling Private Google Access per architectural requirements.

### 7.3. Create a VM Without an External IP

~~~bash
gcloud compute instances create nat-lab-vm \
  --zone=asia-southeast1-b \
  --machine-type=e2-micro \
  --network-interface=subnet=nat-lab-private,no-address \
  --project=PROJECT_ID
~~~

Depending on the chosen image and firewall/SSH setup, you may need administrative permissions and access mechanisms such as **IAP TCP forwarding**. A VM without an external IP cannot be reached directly via SSH over the Internet using a VM external IP.

Inspect the address:

~~~bash
gcloud compute instances describe nat-lab-vm \
  --zone=asia-southeast1-b \
  --format="yaml(networkInterfaces)" \
  --project=PROJECT_ID
~~~

The goal is a NIC with an internal IP inside `10.20.0.0/24` and **no external IPv4 `accessConfigs`** on the source NIC. If the VM already has an external IP, Public NAT test results may not reflect the intended design.

### 7.4. Create Cloud Router for NAT

~~~bash
gcloud compute routers create nat-lab-router \
  --network=nat-lab-vpc \
  --region=asia-southeast1 \
  --project=PROJECT_ID
~~~

No BGP peer configuration is needed for Public NAT to operate in this example.

### 7.5. Create Public NAT with Auto-Allocated External IPs

~~~bash
gcloud compute routers nats create nat-lab-public \
  --router=nat-lab-router \
  --region=asia-southeast1 \
  --auto-allocate-nat-external-ips \
  --nat-custom-subnet-ip-ranges=nat-lab-private \
  --project=PROJECT_ID
~~~

Meaning of key flags:

- `--router`: Cloud Router holding the NAT configuration.
- `--region`: region of the Cloud Router, gateway, and served subnets.
- `--auto-allocate-nat-external-ips`: lets Google Cloud automatically allocate external IPs for Public NAT.
- `--nat-custom-subnet-ip-ranges=nat-lab-private`: only the primary IP range of this subnet is configured for NAT; other subnets are not automatically included.
- `--project`: project containing the lab configuration.

If both primary **and** secondary ranges of that subnet must be served, the matching custom range syntax is `--nat-custom-subnet-ip-ranges=nat-lab-private:ALL`. To enable NAT for all primary and secondary ranges of all subnets in the region, use `--nat-all-subnet-ip-ranges`; the two scope flags are **mutually exclusive** in a single command.

### 7.6. Inspect the Newly Created NAT

~~~bash
gcloud compute routers nats list \
  --router=nat-lab-router \
  --region=asia-southeast1 \
  --project=PROJECT_ID

gcloud compute routers nats describe nat-lab-public \
  --router=nat-lab-router \
  --region=asia-southeast1 \
  --project=PROJECT_ID

gcloud compute routes list \
  --filter="network:nat-lab-vpc" \
  --project=PROJECT_ID
~~~

Read the output and verify subnet scope, IP allocation type, region, and the default route with default internet gateway next hop. Do not conclude "NAT is working" solely because the create command succeeded.

### 7.7. Test Live Egress

Connect to the VM via an approved method; for example, IAP TCP forwarding if permissions and firewalls are configured:

~~~bash
gcloud compute ssh nat-lab-vm \
  --zone=asia-southeast1-b \
  --tunnel-through-iap \
  --project=PROJECT_ID
~~~

`--tunnel-through-iap` requires appropriate IAP configuration, including IAM permissions and an ingress firewall rule for IAP TCP forwarding. **IAP is not automatically configured by Cloud NAT.** If IAP is not set up, use another organization-approved administrative access method.

Inside the VM, try calling an HTTP(S) endpoint **outside Google Cloud**:

~~~bash
curl -I --connect-timeout 10 https://example.com

# Use only if checking egress IP from an external service and
# organization policy allows accessing third-party endpoints.
curl -4 --connect-timeout 10 https://ifconfig.me/ip
~~~

If you get a response, the VM can reach the tested destination outbound. If the IP-checking service returns an IP belonging to the gateway's NAT pool, that provides further evidence of the egress path. Still, **verify the actual external IP allocated to NAT**, routes, firewalls, and traffic sources before concluding all workloads traverse NAT. Third-party IP-check services have their own terms, reliability, and limits.

To definitively test NAT for a private VM, do not test solely against Cloud Storage or Google APIs: **Private Google Access** can allow Google APIs to succeed even when Public NAT is not configured.

## 8. Static Egress IPs When Third Parties Require Allowlisting

Certain payment APIs, partner services, or external databases accept requests only from a **list of permitted public IPs (IP allowlist)**. If using NAT with **auto-allocated** external IPs, the IP set can change when the gateway is modified or scaled. For allowlist requirements, use **regional static external IPs** attached to Public NAT via **manual allocation**.

### 8.1. Create and Attach Static External IPs

~~~bash
# Reserve a public IPv4 address in the same region
gcloud compute addresses create nat-lab-egress-ip \
  --region=asia-southeast1 \
  --project=PROJECT_ID

# View the actual address to provide to the partner allowlist
gcloud compute addresses describe nat-lab-egress-ip \
  --region=asia-southeast1 \
  --project=PROJECT_ID
~~~

If creating a **new** NAT gateway with manual IPs, for example:

~~~bash
gcloud compute routers nats create nat-partner-egress \
  --router=nat-lab-router \
  --region=asia-southeast1 \
  --nat-external-ip-pool=nat-lab-egress-ip \
  --nat-custom-subnet-ip-ranges=nat-lab-private \
  --project=PROJECT_ID
~~~

**Do not run the new gateway creation command alongside an existing NAT gateway already serving an overlapping primary range in the lab.** Pick **one** valid NAT configuration: use manual IPs **in place of** auto-allocation, or deploy in a separately designed environment/configuration. Cloud NAT enforces rules forbidding overlapping source ranges between gateways of the same type and scope.

The illustrative command above shows **creating from scratch** when choosing manual allocation upfront. In a live environment with a running gateway, plan updates using `gcloud compute routers nats update` per Google Cloud guidelines, as changing external IPs can disrupt active connections.

### 8.2. Is One Static IP Enough?

Not always. If a workload opens many concurrent connections to the same destination, usable source ports on a single IP can become a bottleneck. With Cloud Run or GKE autoscaling, port demand can spike rapidly. In that case:

- Use **connection pooling/keep-alive** instead of opening a new connection per request.
- Measure concurrent connections and NAT error/dropped packet metrics.
- Consider multiple static IPs, port allocation sizing, and scale design.
- Align with partners on **all** valid egress IPs; avoid adding IPs without updating the allowlist.
- Evaluate external IP and data-processing costs when increasing capacity.

## 9. Cloud NAT with GKE Private Nodes

In GKE, Pods can run on node VMs without external IPs. Pods still need to download packages, call partner APIs, or send telemetry outside Google Cloud. **Public NAT** can support egress for node/pod traffic matching the configuration.

### 9.1. Primary and Secondary Ranges

Many GKE clusters use **VPC-native** networking with **alias IPs**:

- Nodes use primary internal IPs from the subnet's primary range.
- Pod IPs and Service IPs may reside in appropriately created/managed **secondary ranges**.
- Depending on node-level IP masquerading/SNAT behavior, pod traffic may leave the node with the node's IP or the pod's IP as source.

Thus NAT must be configured for the **actual outbound source ranges**, rather than assuming every pod connection uses the node's primary IP.

~~~mermaid
flowchart LR
    POD["GKE Pod<br/>Pod IP from secondary range"]
    NODE["Node VM<br/>Primary IP"]
    MASQ["GKE IP masquerade / SNAT configuration"]
    NAT["Public NAT<br/>Matching primary/secondary ranges"]
    API["Internet target"]
    POD --> MASQ
    NODE --> MASQ
    MASQ --> NAT
    NAT --> API
~~~

To control egress and avoid unnecessary double NAT, inspect the **GKE IP masquerade policy**, secondary range design, and official networking docs for your cluster mode. In some GKE architectures, preserving pod source IPs instead of SNATting at the node so Cloud NAT handles translation is recommended, though the choice depends on destination (Internet vs. hybrid) and cluster config.

### 9.2. NAT Does Not Replace GKE Controls

- **NetworkPolicy** restricts permitted pod connections.
- **Firewalls** and VPC routes govern network paths.
- **Workload Identity Federation for GKE** handles identity/IAM when pods call Google APIs.
- **Private Google Access** can satisfy some Google API needs without Public NAT.
- **Cloud NAT** handles address translation for matching flows.

A GKE pod reaching the Internet does not mean the pod has permission to read Cloud Storage or Pub/Sub; that still depends on workload identity and IAM.

## 10. Cloud Run and Static Egress IP Requirements

Cloud Run has a default egress mechanism and can reach the Internet **without using a Cloud NAT you configure**. For Cloud Run to use a **static egress IP** through NAT, actively route traffic through a VPC and apply a gateway in the matching region/subnet.

A common pattern:

1. Create or select a VPC/subnet matching the Cloud Run service.
2. Configure **Direct VPC egress** (preferred where supported) or a **Serverless VPC Access connector**.
3. Select **all-traffic egress** so Internet traffic from the service traverses the VPC.
4. Create a Public NAT gateway serving the corresponding subnet/traffic source using **manual static external IPs**.
5. Verify firewalls, routing, NAT port counts, and the observed egress IP on the partner side.

~~~mermaid
flowchart LR
    CR["Cloud Run service"]
    V["Direct VPC egress<br/>all-traffic"]
    SUB["VPC subnet in same region"]
    NAT["Public NAT<br/>Static external IP"]
    PARTNER["Partner API<br/>IP Allowlist"]
    CR --> V
    V --> SUB
    SUB --> NAT
    NAT --> PARTNER
~~~

Reference command when **deploying or updating** a Cloud Run service with an existing image and configured VPC/subnet:

~~~bash
gcloud run deploy orders-api \
  --image=IMAGE_URL \
  --network=nat-lab-vpc \
  --subnet=nat-lab-private \
  --region=asia-southeast1 \
  --vpc-egress=all-traffic \
  --project=PROJECT_ID
~~~

This command modifies the workload, so run it only with a valid image and appropriate deploy permissions. NAT must be configured to serve Cloud Run traffic in that subnet, with static public IPs if the partner uses an allowlist.

**Common pitfall:** if Cloud Run configures VPC egress only for **private ranges** instead of **all traffic**, public Internet requests may still take the default egress path, so third parties will not see the intended static NAT address.

### 10.1. NAT Does Not Configure Cloud Run Inbound

Cloud Run has its own inbound request handling (URLs, ingress controls, authentication, load balancing when used). Creating Public NAT affects only eligible egress; it does not turn the NAT external IP into an HTTP endpoint receiving requests for Cloud Run.

## 11. Private NAT: When the Destination Is Another Private Network

Public NAT handles **private-to-public**. **Private NAT** applies to **private-to-private** across network connectivity scenarios supported by Google Cloud, such as inter-VPC or hybrid connectivity models.

For example, two environments use private IP ranges and require NAT due to governance policies or overlapping address risks. Private NAT can translate sources into a **configured Private NAT IP range**; traffic follows the appropriate private connection route rather than the external Internet gateway.

| Aspect | Public NAT | Private NAT |
| --- | --- | --- |
| Typical destination | Public IPv4 on the Internet | Target private network |
| Translated IP | Regional external IP | IP from Private NAT subnet/range |
| Route used | Matching route with default internet gateway next hop | Routes belonging to supported private connection types |
| Scenario | Private VM downloading updates, Cloud Run calling partner API | Private connectivity requiring NAT between networks |
| Accepts arbitrary unsolicited inbound? | No | No; only replies belonging to established connections |

Private NAT **does not create VPC Peering, Cloud VPN, Cloud Interconnect, or Network Connectivity Center links itself**. Design routes, IP range scopes, connection types, and firewalls before applying. Detailed Private NAT setup is an advanced deployment topic; avoid applying Public NAT external-IP flags to Private NAT without checking docs.

## 12. Observability: How Do You Know NAT Is Working?

Cloud NAT provides **Cloud Logging**, **Cloud Monitoring metrics**, and network diagnostics to monitor gateways.

### 12.1. NAT Logs

Depending on configuration, NAT logging can record:

- **Translation logs** when a connection flow is created and translated.
- **Error logs** when packets are dropped for NAT-logged reasons, such as exhausted allocated ports.
- Details on source, destination, NAT IP, port, and timestamp per logging capabilities.

Example enabling logging on an existing gateway:

~~~bash
gcloud compute routers nats update nat-lab-public \
  --router=nat-lab-router \
  --region=asia-southeast1 \
  --enable-logging \
  --log-filter=ERRORS_ONLY \
  --project=PROJECT_ID
~~~

`ERRORS_ONLY` helps monitor supported NAT error events. When analyzing translation flows to verify traffic, switch the logging policy to collect the appropriate log types. **Do not leave full translation logging enabled long-term without evaluating Cloud Logging volume and cost.**

NAT logs **do not record every packet evaluated by firewalls and are not the sole tool to verify all network traffic**. For instance, if an egress firewall drops a request before NAT, NAT cannot emit a translation log for that request; combine with Firewall Rules Logging/Connectivity Tests.

### 12.2. Metrics to Monitor

| Metric group | Operational meaning | When to act |
| --- | --- | --- |
| NAT port allocation/usage | Port consumption per source | Approaching limits or frequent port exhaustion |
| Dropped packets / NAT errors | Flows failing due to NAT errors | Sudden spike accompanied by timeouts |
| Open connections / connection creation | Connection demand over time | Spikes tied to deployments or scaling |
| Egress bytes / traffic | Data volume processed by NAT | Sharp increase affecting cost/egress |
| NAT IP usage | NAT IP count and utilization | Need more IPs or allowlist stabilization |

Exact metric names, dimensions, and availability depend on service and configuration. Pull exact metric names directly from **Cloud Monitoring metrics explorer** and Cloud NAT docs rather than hardcoding unverified names in dashboards.

### 12.3. NAT Is a Distributed Managed Service

There is no user-created "NAT gateway VM" to SSH into and inspect `iptables`. The Cloud Router/NAT control plane manages configuration; Google Cloud's network infrastructure executes address translation. Observability must rely on **logs, metrics, VPC Flow Logs**, configuration status, and application telemetry rather than checking a hypothetical gateway VM.

## 13. Common Errors and Inspection Workflow

| Symptom | Likely causes | Priority checks |
| --- | --- | --- |
| VM cannot reach Internet | NAT does not serve subnet/region, missing route, egress firewall deny, DNS failure | NIC external IP, NAT region/subnet, routes, firewalls, DNS |
| VM reaches Internet without NAT configured | VM has an external IP or another egress path exists | `accessConfigs`, routes, proxy/NAT appliance, VPN |
| GKE nodes reach out, Pods do not | NAT excludes secondary range or IP masquerade/SNAT mismatch | Actual Pod source IP, secondary ranges, GKE policy |
| Cloud Run reaches Internet, yet IP is not NAT IP | Direct VPC egress/all-traffic not set or NAT on wrong subnet | Cloud Run egress config and NAT |
| Google APIs work, partner API fails | Private Google Access works; Public NAT/route misconfigured | Test non-Google Internet endpoint, check egress path |
| Same destination succeeds intermittently, times out sometimes | Exhausted NAT source ports, connection bursts, retries, or upstream limits | NAT metrics, logs, connection reuse, capacity |
| No NAT logs | Logging disabled, wrong filter, or traffic blocked by firewall before NAT | NAT log config, filters, firewall logs |
| External API returns `403` | Wrong IP allowlist or invalid application token/authorization | Actual egress IP and HTTP/API response |
| Works by IP, fails by hostname | DNS resolver not working properly | DNS policy, Cloud DNS, resolution results |
| Traffic between two private VPCs does not use Public NAT | Public NAT is not private connectivity NAT | Routes/peering/VPN and evaluate Private NAT |

### 13.1. Repeatable Debugging Sequence

~~~mermaid
flowchart TD
    A["Cannot reach external target"] --> B{"Workload has its own external IP?"}
    B -->|Yes| C["Re-verify egress source and routing; Public NAT may not apply"]
    B -->|No| D{"NAT in same VPC/region and serving source range?"}
    D -->|No| E["Fix NAT scope/subnet"]
    D -->|Yes| F{"Route to Internet gateway and firewall allow?"}
    F -->|No| G["Review routes, egress firewalls"]
    F -->|Yes| H{"DNS resolution and TCP/TLS handshake succeed?"}
    H -->|No| I["Distinguish DNS, port exhaustion, upstream timeout"]
    H -->|Yes| J["Check app response, IAM/token, and allowlist"]
~~~

**Practical sequence:**

1. Verify network interface, source IP, region, subnet, primary/secondary ranges, and whether the VM has an external IP.
2. Read NAT gateway configuration, Cloud Router, public NAT IP mode, and source ranges.
3. Verify effective route to destination: Public NAT requires the default internet gateway next hop.
4. Check egress firewalls; use firewall logs/Connectivity Tests when needed.
5. Test DNS queries and HTTP(S) against an endpoint suited to the problem.
6. Check NAT logs/metrics for port exhaustion or dropped packets.
7. If networking succeeds yet the app fails, inspect HTTP status, TLS, tokens, IAM, remote allowlists, and target quotas.

**Never log private keys, access tokens, or customer data during debugging.**

## 14. Security: NAT Is One Layer in Egress Architecture

Cloud NAT helps reduce the need for external IPs on individual VMs, but **it is not a firewall controlling every destination and not a complete data exfiltration prevention solution**. Complementary controls and policies must include:

- **Egress firewalls:** permit only intended protocols, ports, and destinations per design.
- **IAM/service accounts:** restrict permissions to call Google Cloud APIs and modify VPC/NAT.
- **Routing:** govern default routes, policy-based routing, and proxy paths if any.
- **Private Google Access/PSC:** prefer private paths to Google APIs when suitable, reducing reliance on general Internet paths.
- **DNS/security services:** govern domain names, DNS forwarding, and service access policies.
- **Logs/metrics:** monitor NAT errors, connection spikes, and utilization.
- **Budgets:** track NAT, IP, egress, and VM/GKE/Cloud Run costs.

### 14.1. Where Does NAT Sit When Using Shared VPC?

When using **Shared VPC**, subnets and networks belong to the **host project**. The network team manages NAT/Cloud Router configurations in the host network with appropriate permissions; VMs or workloads in **service projects** can use the Shared VPC network/subnets when properly configured and authorized.

Never create NAT in a service project expecting it to automatically apply to a host project subnet. Identify the **VPC-owning project**, active region/subnet, and network admin roles before creating a gateway.

### 14.2. NAT Does Not Replace Service Authentication

A VM with NAT egress calling `storage.googleapis.com` still needs an appropriate identity and IAM to read a private bucket. Conversely, a service account with `roles/storage.objectViewer` will still fail if DNS/routes/networking block requests. **Authentication/authorization and network connectivity are two independent layers that must both be right.**

## 15. Cloud NAT Costs and How to Forecast Them

Public NAT can incur multiple charges, typically including:

1. **Gateway usage charges over time** and the applicable pricing model.
2. **Data processing charges by NAT** based on volume.
3. **External IP charges** used by the gateway.
4. **Data transfer out charges** corresponding to traffic leaving the network.
5. **Cloud Logging/Monitoring or supporting resource charges** depending on configuration and usage.

Thus a small VM using little CPU does not guarantee low lab costs if large data transfers occur or the NAT gateway/IPs are left running.

### 15.1. Estimating the Cost Structure

Illustrative formula:

~~~text
Estimated NAT and egress cost
  = gateway time/unit charge
  + (GiB processed by NAT × processing rate/GiB)
  + (number of external IPs × usage duration × IP rate)
  + data transfer out charges
  + logging/other charges if applicable
~~~

Do not treat this formula as an official quote; tiers, conditions, and special traffic types apply. **Pull unit rates from the Cloud NAT pricing page at deployment time**, as prices and features may change over time, by region, or by agreement.

### 15.2. Mistakes That Cause Unexpected Costs

- Creating NAT gateways in multiple regions for testing and forgetting to delete them.
- Keeping regional static external IPs after a lab finishes.
- Enabling high-volume translation logging, driving up stored log volume.
- Running unbounded data download jobs between the Internet and VMs/GKE.
- Adding NAT IPs without reviewing actual port needs.
- Deploying Cloud Run with all-traffic egress through NAT even when the workload only needs Google APIs with another private access option.

Set up a **Cloud Billing budget** for the lab project, attach an owner and end date, and audit costs under **Networking/Cloud NAT SKUs**. Budgets only alert; they do not automatically shut down resources.

## 16. Lab Cleanup After Practice

When demo resources are no longer needed, clean up in **dependency order and after confirming the exact project**. The checks below lead to **real deletion** operations that can disrupt systems if names are mistyped. Perform only in a lab project with no data to preserve.

1. Verify project, VMs, network, and NAT gateway genuinely belong to the lab.
2. Delete test VMs and unneeded auxiliary disks.
3. Delete the lab NAT gateway and Cloud Router once no other consumers remain.
4. Inspect and release separately reserved static external IPs.
5. Delete lab subnets/VPC once certain no dependent resources remain.
6. Check Cloud Billing after reporting delay to spot lingering charges.

**Read-only** inventory example before cleanup:

~~~bash
gcloud compute instances list --project=PROJECT_ID

gcloud compute routers list \
  --regions=asia-southeast1 \
  --project=PROJECT_ID

gcloud compute routers nats list \
  --router=nat-lab-router \
  --region=asia-southeast1 \
  --project=PROJECT_ID

gcloud compute addresses list \
  --filter="region:(asia-southeast1)" \
  --project=PROJECT_ID
~~~

If static IPs were used in partner allowlists, coordinate with partners to update allowlists after decommissioning; avoid leaving released IPs inside external trusted lists.

## 17. Design Scenario: Three Workloads Sharing One Project

A company deploys:

- **Private batch VM** in subnet `batch-private` in `asia-southeast1`, needing to download dependencies from the Internet.
- **GKE private node pool** with pod IPs from a secondary range, needing to call partner APIs.
- **Cloud Run orders-api** needing to call a payment gateway that permits only specific fixed external IPs.

Proposed approach:

| Component | Network design | What to verify |
| --- | --- | --- |
| Batch VM | No external IP; subnet served by Public NAT | Default internet gateway route, egress firewall, NAT primary range |
| GKE private nodes/pods | Primary/secondary ranges served by NAT matching actual source IPs | IP masquerade policy, secondary ranges, port capacity |
| Cloud Run | Direct VPC egress + `all-traffic`, Public NAT manual IPs | Region/subnet, actual egress IPs, partner allowlist |
| Google APIs access | Private Google Access/PSC as needed | DNS, API IAM, paths, and service support |
| Governance | Firewalls, IAM, Cloud Monitoring, Cloud Billing | Logs, dropped packets, NAT/IP/egress costs |

### 17.1. Why Must Layers Be Designed Separately?

If the VM reaches the Internet yet Cloud Run shows a different IP from NAT, the fault may lie in **Cloud Run egress mode** rather than NAT. If GKE pods fail while nodes connect fine, inspect **source ranges and IP masquerade**. If all three reach outside yet Cloud Storage returns `403`, the cause is likely **IAM**. If all flows slow down and drop after autoscaling, evaluate **port allocation**.

~~~mermaid
flowchart TD
    A["Identify egress need"] --> B{"Target is a supported Google API?"}
    B -->|Yes| C["Evaluate Private Google Access / PSC"]
    B -->|No| D{"Public Internet target?"}
    D -->|Yes| E["Public NAT + routes/firewalls"]
    D -->|No| F["Evaluate private connectivity / Private NAT"]
    E --> G{"Partner requires fixed IP?"}
    G -->|Yes| H["Manual regional static NAT IP + allowlist"]
    G -->|No| I["Auto-allocated NAT IP may fit"]
    C --> J["Check IAM, DNS, metrics, and cost"]
    F --> J
    H --> J
    I --> J
~~~

This design helps pick the right service rather than forcing one NAT gateway onto every connectivity problem.

## 18. Self-Check Exercises

**Q1.** A VM without an external IPv4 sits in a NAT-served subnet. Can the VM receive inbound SSH connections from a laptop via the NAT's external IP by default?

*Hint:* No. Public NAT does not permit unsolicited inbound connections. Use an administrative access method such as IAP TCP forwarding or an approved VPN/bastion.

**Q2.** Why might a VM still fail to reach HTTPS on the Internet after creating Cloud Router and Public NAT?

*Hint:* It may lack a route with default internet gateway next hop, be blocked by an egress firewall, sit in a subnet/region outside NAT scope, have DNS errors, or lack port capacity. Cloud Router/NAT do not automatically fix those prerequisites.

**Q3.** A VPC has subnets in Singapore and Iowa. Can a single NAT gateway in Singapore serve both subnets?

*Hint:* No. A NAT gateway is bound to one region; create a corresponding gateway in the other region if needed.

**Q4.** A Cloud Run service can call the Internet, yet the partner reports the source IP does not match the NAT allowlist. What do you check first?

*Hint:* Direct VPC egress or connector, `--vpc-egress=all-traffic`, subnet/region, and Public NAT manual external IP configuration.

**Q5.** A private GKE node reaches the Internet fine, yet a pod with an alias IP from the secondary range times out. What is the right investigation approach?

*Hint:* Inspect the source IP after IP masquerading/SNAT, secondary ranges in NAT configuration, egress firewalls, and NAT port usage.

**Q6.** A private VM successfully calls Cloud Storage using Private Google Access. Does that prove Public NAT is working?

*Hint:* No. Private Google Access can provide a path to supported Google APIs without using Public NAT for the public Internet. Test an appropriate non-Google endpoint and inspect configurations/metrics.

**Q7.** Under high load, the system gets errors on new connections to the same partner API while already-open connections continue working. Name one cause at the NAT layer.

*Hint:* Source port exhaustion due to high concurrent connections or connection creation rate. Inspect logs/metrics, connection pooling, and NAT IP/port allocation.

**Q8.** Does using a static external IP for NAT guarantee the application is safe from all malicious connections?

*Hint:* No. NAT does not replace egress firewalls, IAM, API authentication, DNS/security controls, and monitoring.

**Q9.** Do Cloud NAT and Cloud Router force HTTP packets through a gateway VM adding an extra hop?

*Hint:* No. They provide configuration/control plane, while the NAT data plane is distributed by Google Cloud inside the network fabric.

**Q10.** After finishing the lab, you deleted the VM yet still see network charges. Which items should you check?

*Hint:* NAT gateway, reserved external IPs, logging, previously generated egress data, and any other active resources; remember billing data has reporting delay.

## 19. Key Takeaways

- **Public NAT is an egress mechanism** for privately addressed resources reaching public IPv4 targets—not an inbound gateway from the Internet.
- **VPC routes, firewalls, and DNS must align**; NAT does not create default routes or permit all connections.
- **Cloud NAT is bound to one VPC, region, and Cloud Router**; a single gateway cannot serve all regions.
- **Primary/secondary IP range scope** matters greatly, especially when GKE uses pod alias IPs.
- **Cloud Run needs VPC egress + all-traffic** to send Internet traffic through a static-IP NAT gateway in this pattern.
- **Private Google Access/PSC** may be better suited for Google APIs; **Private NAT** serves supported private-to-private translation needs.
- **NAT ports, logs, monitoring, and costs** must be managed as part of cloud reliability and budgeting.

When designing solutions with Compute Engine, GKE, Cloud Run, and databases, ask: **"What is the workload's actual source IP? Is the destination on the Internet or a private network? Do routes and firewalls allow it? Are there fixed egress IP, port capacity, or cost limits?"** Answering these questions accurately produces controlled, diagnosable, and reliably operated private connectivity.

## Official Reference Documentation

- [Cloud NAT overview — Google Cloud](https://cloud.google.com/nat/docs/overview)
- [Public NAT specifications](https://cloud.google.com/nat/docs/public-nat)
- [Private NAT overview](https://cloud.google.com/nat/docs/private-nat)
- [Set up Public NAT](https://cloud.google.com/nat/docs/set-up-manage-network-address-translation)
- [Cloud NAT and routing/firewall interactions](https://cloud.google.com/nat/docs/nat-product-interactions)
- [NAT IP addresses and source ports](https://cloud.google.com/nat/docs/ports-and-addresses)
- [Cloud NAT troubleshooting](https://cloud.google.com/nat/docs/troubleshooting)
- [Cloud NAT logs and metrics](https://cloud.google.com/nat/docs/monitoring)
- [Cloud NAT pricing](https://cloud.google.com/nat/pricing)
- [Private Google Access](https://cloud.google.com/vpc/docs/private-google-access)
- [Cloud Run static outbound IP](https://cloud.google.com/run/docs/configuring/static-outbound-ip)
- [gcloud compute routers nats create](https://cloud.google.com/sdk/gcloud/reference/compute/routers/nats/create)
