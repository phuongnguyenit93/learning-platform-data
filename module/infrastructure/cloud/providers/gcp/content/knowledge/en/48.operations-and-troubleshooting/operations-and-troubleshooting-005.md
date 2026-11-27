# Finding the Root Cause of Firewall, NAT, and Google API Access Errors

An application running on Compute Engine, GKE, or Cloud Run can call external services cleanly in a test environment yet time out in production. The blame is frequently placed immediately on firewalls, even though the real cause may be DNS returning the wrong address, a missing outbound route, Cloud NAT not covering the subnet, Private Google Access being disabled, a misconfigured proxy, or the application identity lacking permissions to call the Google API.

Effective troubleshooting does not mean opening all egress or granting Owner to a service account. Operators must determine **where the request originates, which endpoint it targets, how it is routed, and at which layer it fails**. This lesson presents a repeatable investigation workflow on Google Cloud, observability tools, read-only command examples, and common failure scenarios. The goal is to find the exact fault with evidence, apply the smallest necessary configuration change, and verify both recovery and security boundaries.

## 1. Identifying the Exact Failing Layer

An HTTP call to a Google API traverses multiple layers. Failures at different layers can produce nearly identical messages in application logs.

| Layer | Question to Answer | Common Symptoms |
| --- | --- | --- |
| Request source | Which VM, Pod, or Cloud Run revision is throwing errors? | Only one environment or instance group fails |
| DNS | Does the API hostname resolve to the expected IP? | Resolution failure, NXDOMAIN, or wrong endpoint |
| Route | Does the VPC/subnet have a valid route to the destination IP? | Timeout despite DNS returning an IP |
| Firewall / network policy | Is traffic from source to destination on the required port allowed? | Blocked or timed out depending on path |
| NAT / private access | Does a source without an external IP have a corresponding outbound path? | Loss of internet access or only certain APIs failing |
| TLS / proxy | Does TLS handshake succeed with the right hostname and CA? | Certificate, proxy, or handshake errors |
| IAM / API control | Does the principal have permission to access the API/resource? | HTTP 401/403, permission denied |
| Quota / service state | Is the API rejecting requests due to limits or service outages? | HTTP 429, `RESOURCE_EXHAUSTED`, 5xx |

**An HTTP 403 error is not automatically a firewall error.** If the client receives a complete HTTP response from a Google API, network and TLS connectivity to an endpoint usually succeeded. Next, check IAM, OAuth scopes, API enablement, VPC Service Controls, organization policies, or service access rules. Conversely, a TCP connection timeout can come from firewalls, routes, NAT, DNS, proxies, or an unresponsive endpoint; a single log line cannot diagnose it.

## 2. Outside-In Investigation Workflow

Use a consistent test request to inspect each stage:

~~~mermaid
flowchart TD
  A["App call to Google API fails"] --> B{"Does DNS resolve properly?"}
  B -->|"No"| D["Check resolver, private zone, forwarding, proxy"]
  B -->|"Yes"| C{"Does TCP/TLS to endpoint work?"}
  C -->|"No"| E["Check routes, firewall, NAT, PGA, egress path"]
  C -->|"Yes"| F{"HTTP/gRPC status received?"}
  F -->|"401/403"| G["Check identity, IAM, scopes, VPC SC, API enabled"]
  F -->|"429/5xx"| H["Check quotas, retries, API health"]
  F -->|"Other 2xx/3xx/4xx"| I["Check API semantics and payload"]
  D --> J["Fix one component and retry"]
  E --> J
  G --> J
  H --> J
  I --> J
  J --> K["Verify functionality and telemetry after change"]
~~~

Never change DNS, routes, firewalls, and IAM all at once. Changing multiple layers simultaneously makes it impossible to tell which fix worked and easily leaves behind an overly permissive rule.

## 3. Recording Scope and Evidence Before Taking Action

Every incident should have a minimum record:

- **Source:** project, VPC, subnet, region/zone, VM or cluster/Pod/service, network interface, source IP.
- **Destination:** FQDN, DNS-resolved IP, port, protocol, Google API/resource, and call method.
- **Timing:** first failure timestamp, recurrence, affected region, and recent changes.
- **Symptoms:** DNS failure, timeout, TCP reset, TLS error, HTTP status, or gRPC status.
- **Egress path:** external IP, Cloud NAT, Private Google Access, Private Service Connect, VPC connector, or Direct VPC egress.
- **Identity:** service account, scopes (where applicable), IAM roles, VPC Service Controls, and organization policies.
- **Telemetry:** request ID, app logs, VPC Flow Logs, Firewall Rules Logging, Cloud NAT logs, and API audit logs where available.

With Shared VPC in particular, a workload in a **service project** can use subnets, firewalls, and NAT in a **host project**. Inspecting firewalls only in the application project misses the actual network configuration.

Never print access tokens, service account keys, or secrets into incident logs. Record principal emails and resource paths where appropriate, never credentials.

## 4. Understanding Network Paths: VMs, Pods, and Serverless

Before inspecting firewalls, determine which IP actually appears on the wire.

| Workload | Network Path to Understand | Commonly Overlooked Detail |
| --- | --- | --- |
| Compute Engine with external IPv4 | VM communicates via VPC, egressing via external IP | Does not use Cloud NAT by default for that VM |
| Compute Engine without external IPv4 | May use Cloud NAT for Internet, Private Google Access for Google APIs | NAT missing subnet/region coverage; PGA disabled |
| GKE Standard / VPC-native | Pod IP, node IP, and SNAT depend on CNI, `ip-masq` config, network policy | NAT missing actual source range or Pod egress blocked |
| GKE Autopilot | Network path governed by GKE and cluster config | Do not assume Standard node behavior without checking |
| Cloud Run | Uses platform egress or configured VPC egress | Mixing up `private-ranges-only` with `all-traffic` |
| On-premises workloads | VPN/Interconnect, DNS forwarding, and matching routes/endpoints | Return path, resolver policy, and prefix advertisement |

**Cloud NAT is not an inline proxy visible as a separate hop in traceroute.** It performs address translation under supported conditions; the absence of a NAT hop in traceroute does not prove NAT is broken.

## 5. DNS: Check Hostnames Before IPs

An application calling `storage.googleapis.com` or another API typically starts with DNS. Depending on architecture, resolution can return standard public addresses, dedicated ranges for Google API access, or internal Private Service Connect addresses.

Steps:

1. Query the FQDN from **the exact failing environment**, not just your laptop.
2. Record the active resolver and all returned CNAME/A/AAAA records.
3. Check private Cloud DNS zones, forwarding/peering zones, and DNS policies if present.
4. Confirm the resolved endpoint matches the intended egress architecture.
5. Check whether proxies or custom DNS inside containers alter the target.

Examples on a Linux worker:

~~~bash
getent ahostsv4 storage.googleapis.com
dig storage.googleapis.com A
dig +short storage.googleapis.com A
cat /etc/resolv.conf
~~~

If `dig` is unavailable, use `nslookup` or an equivalent DNS tool. On Kubernetes, `/etc/resolv.conf` usually points to the cluster resolver or configured DNS mechanism; examine CoreDNS/Cloud DNS or NodeLocal DNSCache according to the actual architecture.

**Never blame a firewall when `dig` returns NXDOMAIN or resolves the wrong name.** Find the DNS root cause first. Conversely, successful resolution only confirms an IP exists—it does not prove TCP/TLS to that IP works.

## 6. Routes: Inspect Both Destination and Next Hop

After DNS, the system needs a route to the destination IP. For VMs without external IPs accessing Google APIs via Private Google Access, architectures normally rely on a route to Google API addresses via the VPC **default internet gateway**, even though traffic to dedicated VIPs stays within Google's network per product behavior.

Questions to verify:

- Is there a default route `0.0.0.0/0` or a specific route covering the destination IP range?
- Does the next hop match design, or is traffic detoured through a VPN, appliance, or other endpoint?
- Are dynamic routes or network policy routes overriding the default path?
- For Shared VPC subnets, are you inspecting the right VPC/host project?
- For hybrid networks, does a return route exist back to the request source?

Read-only command:

~~~bash
gcloud compute routes list \
  --project=HOST_PROJECT_ID \
  --filter="network:VPC_NAME" \
  --format="table(name,destRange,priority,nextHopGateway,nextHopInstance)"
~~~

`gcloud compute routes list` output does not display all special routing semantics or exact route selection order across every next-hop type. When needed, use **Connectivity Tests** and Google Cloud's effective routes inspection tools appropriate for the resource and version. Never add `0.0.0.0/0` indiscriminately just to test, especially in networks with centralized egress or VPC Service Controls.

## 7. VPC Firewalls: Stateful, Yet Not Everything Is Permitted

VPC firewall rules and network firewall policies govern allowed/denied traffic by direction, priority, target, source/destination, protocol, and port. In a VPC without overriding rules or policies, Google Cloud applies implied rules including **deny ingress** and **allow egress** per platform behavior. The default VPC also comes with pre-created rules that should not be confused with implied rules.

Checks to run:

- Does an egress rule actually permit TCP 443 from the exact source to the target IP/API?
- Is ingress needed? For allowed connections initiated by a VM, VPC firewalls track session state; do not create broad ingress rules just for return responses.
- Does the rule apply network-wide or only to VMs with specific network tags or service accounts?
- Does a higher-priority deny rule or organization/folder/network policy block traffic first?
- Does the workload also enforce Kubernetes NetworkPolicy, host firewalls, or service mesh policies?
- Is logging enabled on the matching rule, and does it capture the expected events?

Within VPC firewall rules, lower priority numbers take precedence inside the same evaluation tier. However, **do not infer the full effective precedence purely from VPC firewall rule lists** when hierarchical firewall policies and network firewall policies are in use. Inspect effective firewall policies along the active path.

## 8. Inspecting Firewalls with CLI and Connectivity Tests

Some **read-only** commands:

~~~bash
gcloud compute firewall-rules list \
  --project=HOST_PROJECT_ID \
  --filter="network:VPC_NAME"

gcloud compute instances describe VM_NAME \
  --project=SERVICE_PROJECT_ID \
  --zone=ZONE \
  --format="yaml(networkInterfaces,tags,serviceAccounts)"
~~~

Network tags and service accounts on the VM determine which rules apply. If a rule targets a service account or secure tag, check the exact selector rather than looking only at source IPs.

**Network Intelligence Center – Connectivity Tests** can analyze network configuration for a source/destination pair and report predicted drop reasons such as missing routes or firewall denies within its supported scope. It is invaluable for narrowing down suspects, yet does not replace a live call: it may not observe full application state, TLS, permissions, dynamic DNS, or devices outside Google Cloud.

Firewall Rules Logging only captures data when enabled on the relevant rule/scope, and logs may not capture every packet. VPC Flow Logs likewise depend on logging enablement, sampling, aggregation, and supported resources. **Absence of logs does not prove traffic never existed.**

## 9. What Problem Does Cloud NAT Solve?

Cloud NAT lets eligible workloads without external IPv4 addresses initiate outbound connections via address translation. Public NAT is configured per **region** and attached to a Cloud Router as a control-plane configuration component; the Cloud Router here does not become a data-plane router forwarding every NAT packet.

Key checkpoints:

| Checkpoint | Meaning |
| --- | --- |
| Region | NAT must match the region of the source workloads |
| VPC/subnet | Must cover the source subnet and IP range type |
| NAT IP allocation | Valid external NAT IPs with sufficient capacity |
| Port allocation | Sufficient translated ports for active connection concurrency |
| Egress route | Valid next-hop path so traffic reaches NAT translation |
| Logging | Appropriate logging enabled to observe translations/errors when needed |
| Source identity | Do not confuse node IPs, Pod IPs, and serverless egress IPs |

Cloud NAT does not allow external Internet clients to initiate new TCP connections into a private VM. It does not replace an external load balancer, proxy, or ingress design. A VM that already has an external IP typically does not use Cloud NAT for that external IPv4 egress flow.

**Public NAT and Private NAT are distinct mechanisms** in the Cloud NAT ecosystem. When investigating Google API or Internet access via public addresses, confirm which NAT type is active and whether the source and destination fall within its supported scope.

## 10. Troubleshooting Cloud NAT in Order

A private VM has an Internet route yet cannot reach a public website. Before adding firewall rules, check:

1. Does the VM have an external IP? If yes, trace the actual egress path rather than assuming NAT.
2. Which region and subnet is the VM in? Does the NAT belong to that VPC and region?
3. Does NAT cover all primary subnet IP ranges or only a specific list of subnets/ranges?
4. On GKE, is Pod traffic SNATed to node IPs or keeping Pod secondary IPs?
5. Does NAT use automatic or manual IP allocation? Are IP or port allocations exhausted?
6. Is any route or policy unexpectedly steering the next hop to an appliance or VPN?
7. Do Cloud NAT logs/metrics show port exhaustion, packet drops, or mapping errors?

Command to inspect a named NAT configuration:

~~~bash
gcloud compute routers nats describe NAT_NAME \
  --project=HOST_PROJECT_ID \
  --router=ROUTER_NAME \
  --region=REGION
~~~

Do not tweak **min ports per VM**, dynamic port allocation, or add NAT IPs before knowing which limit is being hit. NAT port exhaustion exhibits different symptoms from broken DNS or missing routes. When connection rates surge or many connections hit the same endpoint, check NAT logs/metrics, endpoint counts, and traffic patterns (TCP/UDP, connection duration) to pick the right fix.

## 11. Private Google Access Is Not Cloud NAT

**Private Google Access (PGA)** allows eligible sources without external IPs in a subnet to access supported Google APIs and services over Google Cloud paths when DNS and routes are properly configured. Calling Google APIs over PGA **does not require Cloud NAT** just because a VM lacks a public IPv4 address.

Key differences:

| Requirement | Typical Component Involved |
| --- | --- |
| Private VM accesses a public Internet website outside Google APIs | Public Cloud NAT or equivalent egress mechanism |
| Private VM calls supported Google APIs | Private Google Access with matching DNS and routes |
| Enforce VPC Service Controls on Google API access | `restricted.googleapis.com` and perimeter where applicable |
| Access Google APIs via a private IP endpoint inside the VPC | Private Service Connect endpoint for Google APIs if supported |
| On-prem calls Google APIs over hybrid links | Supported connectivity, routing/DNS, and private access path |

Never conclude from "Cloud NAT is working" that PGA, VPC SC, or IAM must also be correct. They are independent layers.

Inspect subnet configuration:

~~~bash
gcloud compute networks subnets describe SUBNET_NAME \
  --project=HOST_PROJECT_ID \
  --region=REGION \
  --format="yaml(name,network,ipCidrRange,privateIpGoogleAccess)"
~~~

If `privateIpGoogleAccess` is false, compare against the design: does the workload have its own external IP/egress or was it expected to use PGA? Only change it after confirming it is the root cause and assessing subnet-wide impact.

## 12. `private.googleapis.com` and `restricted.googleapis.com`

Google Cloud provides special domains for private access architectures:

- **`private.googleapis.com`** uses IPv4 VIPs **199.36.153.8/30** and provides private access to most supported Google APIs and services.
- **`restricted.googleapis.com`** uses IPv4 VIPs **199.36.153.4/30** and targets the subset of APIs supporting VPC Service Controls under restricted access.

These are **reserved public IP addresses dedicated to Google API access**, not RFC 1918 ranges. Access behavior and routing on Google's network cannot be judged simply by checking whether an IP falls in `10.0.0.0/8`.

An architecture may use a private Cloud DNS zone to direct Google API hostnames to one of these VIPs. Example DNS records to verify:

~~~text
private.googleapis.com.       A      199.36.153.8
private.googleapis.com.       A      199.36.153.9
private.googleapis.com.       A      199.36.153.10
private.googleapis.com.       A      199.36.153.11
*.googleapis.com.             CNAME  private.googleapis.com.
~~~

This is an illustrative record layout for `private.googleapis.com`, **not a recipe for bulk-modifying production DNS**. Verify which domains use `googleapis.com`, how other domains are handled, zone visibility scope, and which endpoints/capabilities are supported. The restricted option uses a different endpoint and VIP range; never switch all workloads to `restricted` without verifying every required API supports VPC Service Controls.

When using these VIPs, you still need DNS, routes to the target range via a supported next hop, egress firewalls, and Private Google Access aligned with the actual source/workload. A valid CNAME without matching routes or permissions will still fail.

## 13. Misconfigured DNS Overrides: Easily Mistaken for NAT

Suppose an application suddenly fails to reach `storage.googleapis.com` right after the network team adds a private DNS zone for `googleapis.com`. Common causes:

- Wildcard CNAME points to a non-existent target or omits a trailing FQDN dot.
- The private zone is attached to a different VPC than the one issuing queries.
- A forwarding zone or peering zone takes precedence for that namespace.
- Pod or host resolvers point to a custom DNS server lacking that zone.
- DNS TTL has not expired, clients hold stale connections, or negative caching persists.
- Using `restricted.googleapis.com` for an unsupported API or one blocked by VPC SC.

Never disable a firewall to "test DNS." Query from the exact failing Pod/VM, compare responses against zone configuration, and check routes to the returned IP. When applications use a custom HTTP proxy, the proxy may resolve DNS on behalf of clients; test **where resolution actually happens**.

Read-only commands to inspect private zones:

~~~bash
gcloud dns managed-zones list --project=DNS_PROJECT_ID

gcloud dns record-sets list \
  --project=DNS_PROJECT_ID \
  --zone=GOOGLEAPIS_PRIVATE_ZONE
~~~

A zone's name does not indicate which VPCs are authorized to query it; inspect zone visibility and attached networks as needed.

## 14. Private Service Connect, Private Services Access, and Google API Endpoints

Three frequently confused mechanisms:

| Mechanism | Problem Solved | Do Not Misunderstand |
| --- | --- | --- |
| Private Google Access | Eligible sources without external IPs access Google APIs over supported paths | Not a general NAT for all Internet websites |
| Private Service Connect (PSC) | Creates service endpoints/attachments by service type, including Google APIs in supported setups | Does not grant API IAM and does not replace DNS |
| Private Services Access (PSA) | Private connectivity to supported producer services via service networking | Does not operate identically to PSC endpoints |

With PSC for Google APIs, DNS overrides may be needed to point API FQDNs to the internal endpoint IP. Verify **endpoint address, status, global/regional scope per product, DNS, routes/firewalls, and API bundle**. An existing PSC endpoint does not guarantee every API is supported or that IAM allows the call.

Never try to fix a PSC issue by enabling Cloud NAT when traffic is meant to stay on an internal VPC endpoint. First prove requests are hitting the configured endpoint IP.

## 15. Google API Access Also Depends on IAM, Scopes, and VPC SC

Even after an HTTPS connection succeeds, a Google API can reject the request. Common causes:

1. **API is not enabled** in the appropriate project per API and consumption model.
2. **Service account lacks roles/permissions** on the target project, bucket, dataset, secret, or resource.
3. **OAuth access scopes** on certain VM/credential paths remain restrictive despite IAM roles.
4. **VPC Service Controls** block access due to perimeters, ingress/egress rules, or API support.
5. **Organization policies** or service-level policies block the action.
6. **Quota/billing** issues or malformed API requests.

For instance, a VM using PGA can complete TLS to Cloud Storage yet receive HTTP 403 when reading a private bucket. Adding Cloud NAT or opening firewalls will not grant bucket read access. Inspect the principal, bucket/project IAM roles, and API error details.

Status codes must also be interpreted alongside response bodies and service context:

| Outcome | Initial Interpretation |
| --- | --- |
| DNS NXDOMAIN / name not resolved | Check DNS first |
| TCP connection timeout | Check routes, firewalls, NAT, proxies, and endpoint |
| TLS certificate error | Check hostname, trust store, TLS inspection, and system clock |
| HTTP 401 | Missing/expired/invalid credentials or wrong auth mechanism |
| HTTP 403 | IAM, VPC SC, disabled API, or service policy depending on error details |
| HTTP 429 | Rate limit/quota or overload protection |
| HTTP 5xx | Service issue, intermediate network, or server fault; capture correlation ID |

Do not treat this table as an absolute rule; examine gRPC codes, error details, audit logs, and specific methods to confirm root cause.

## 16. Testing TCP and TLS with Non-Destructive Probes

Test directly from the failing source:

~~~bash
curl -sv \
  --connect-timeout 5 \
  --max-time 15 \
  https://storage.googleapis.com/ \
  -o /dev/null

openssl s_client \
  -connect storage.googleapis.com:443 \
  -servername storage.googleapis.com \
  -brief
~~~

An HTTP 400/403/404 response from a test endpoint can still prove DNS/TCP/TLS completed, though it **does not prove application API permissions**. With `curl`, record the response code, timestamp, remote IP, TLS errors, and proxy settings; never log access tokens.

Never disable TLS certificate validation as a production fix. When TLS fails, diagnose the exact certificate chain, hostname mismatch, CA trust, proxy interception, or clock skew.

For gRPC, use protocol-appropriate tools against the endpoint. Once the network path is verified, shift investigation to status codes and permissions rather than continuing to guess at firewalls.

## 17. Compute Engine: Example of a Private VM Failing to Call an API

**Scenario:** A VM without an external IPv4 address in `asia-southeast1` tries to read Cloud Storage; `curl` times out.

Procedure:

1. Inspect VM `networkInterfaces` to confirm VPC/subnet, external IP, and network tags.
2. Check DNS resolution for `storage.googleapis.com` directly on the VM.
3. Verify the target IP: private/restricted VIP, PSC IP, or default endpoint.
4. Check whether the subnet has PGA enabled if PGA is the intended design.
5. Inspect routes to the destination and egress firewalls/policies.
6. If traffic truly traverses the public Internet, check whether Public Cloud NAT is needed and covers the subnet.
7. Run unauthenticated `curl`/`openssl` to confirm TLS; then call the API using the VM identity via a secure auth method.
8. If only the bucket read operation fails, check IAM/scopes and VPC Service Controls.

Never attach an external IP or grant Editor to the VM as a "quick fix." Those changes widen the attack surface and mask the underlying issue.

## 18. GKE: Pod IPs, Node IPs, and NetworkPolicy

In VPC-native GKE clusters, Pod IPs typically come from a secondary range while node IPs come from the primary range. Pod egress may be SNATed to the node IP or preserve the source Pod IP depending on IP masquerade config, CNI, and cluster settings. Cloud NAT must cover **the actual source addresses** used by outbound traffic—not necessarily only the primary range in every setup.

Typical symptoms:

- Nodes reach the API while Pods fail: check in-Pod DNS, NetworkPolicy, service mesh, proxies, and egress SNAT.
- One namespace fails while another succeeds: compare NetworkPolicies and workload identities.
- Pods only fail when scaling up: inspect Cloud NAT port allocation, connection rates, quotas, and new Pod/node counts.
- Pods receive HTTP 403 calling an API: check Workload Identity Federation for GKE, service account roles, VPC SC, and resource scopes.

Read-only commands:

~~~bash
kubectl get pods -n APP_NAMESPACE -o wide
kubectl get networkpolicy -n APP_NAMESPACE
kubectl get serviceaccounts -n APP_NAMESPACE
kubectl describe pod POD_NAME -n APP_NAMESPACE
~~~

Do not deploy privileged Pods or privileged DaemonSets across all nodes without authorization. If a diagnostic Pod is needed, run it in an approved test namespace and delete it afterward.

On GKE Autopilot, node-level privileges differ from Standard; rely on platform-supported observability tools.

## 19. Cloud Run: Easily Misunderstood Egress Paths

Cloud Run supports VPC connectivity options such as **Direct VPC egress** and **Serverless VPC Access connectors** depending on supported features and regions. Based on configuration, traffic can route through the VPC only for private ranges (**private-ranges-only**) or for all destinations (**all-traffic**).

| Egress Configuration | What to Check |
| --- | --- |
| No VPC egress configured | Do not apply private-VM Cloud NAT diagrams to default platform egress |
| `private-ranges-only` | Publicly addressed Google API VIPs or Internet endpoints may bypass the VPC despite assumptions |
| `all-traffic` | Inspect subnet/connector, routes, firewalls, NAT, or PGA/PSC for the actual destination |

For example, a Cloud Run revision previously called an API cleanly, then timed out after switching to `all-traffic`. Do not assume the Google API is down: egress may now route through a subnet lacking PGA, routes, or firewalls; for external websites, Public Cloud NAT may not cover that subnet.

Read-only service inspection command:

~~~bash
gcloud run services describe SERVICE_NAME \
  --project=PROJECT_ID \
  --region=REGION \
  --format=yaml
~~~

Compare the traffic-serving revision with the failing revision; differences in network, egress settings, env vars, and IAM often explain the incident. Cloud Run revisions lack VM-style host networking tools; rely on application logs and approved in-container probes.

## 20. Hybrid/On-Premises: Do Not Assume GCP VM Behavior

Servers in a data center or another cloud calling Google APIs over VPN/Interconnect face extra requirements around DNS, private VIP routing, source addresses, and supported private access mechanisms. Enabling Private Google Access on a Compute Engine subnet **does not automatically enable access** for all on-premises systems.

Dedicated checklist:

- Does on-prem DNS resolve to private/restricted VIPs or PSC endpoints where appropriate?
- Are on-prem routes to destination ranges advertised/directed over the right tunnel/interconnect?
- Are return routes, stateful firewalls/NAT, and source IPs permitted?
- Is the system using standard Internet egress or a specific private access path?
- Do IAM and VPC Service Controls allow requests originating outside Google Cloud VPCs?

Never advertise a blanket default route over VPN just because one API fails. Prefer specific endpoint routes and egress policies aligned with supported architectures, and test from an actual host.

## 21. Observability Tools: Strengths and Limitations

| Tool | What It Verifies | Limitations |
| --- | --- | --- |
| Connectivity Tests | Route/firewall config analysis and reachability within supported scope | Does not verify API auth outcomes or external non-GCP devices |
| Firewall Rules Logging | Whether allow/deny rules match configured traffic | Must be enabled; not a full packet capture |
| VPC Flow Logs | Observed flows, IPs, ports, byte counts, and supported metadata | Subject to sampling/aggregation; requires source IP interpretation |
| Cloud NAT logs/metrics | Translations, port allocations, NAT errors, and traffic | Reflects only sources actually traversing NAT |
| Cloud DNS logs | Queries, answers, or resolver state per supported config | Does not prove TCP to the IP works |
| Cloud Audit Logs | Config changes and API access errors where recorded | Data Access logs may require explicit enablement and viewing permissions |
| Application logs/traces | Request paths, methods, statuses, deadlines, proxy/TLS errors | Require correlation IDs; avoid leaking secrets |

No single log explains the entire path. For instance, empty NAT logs may occur because traffic used PGA/PSC, NAT logging is off, flows were not sampled, or packets never reached NAT.

When configuring monitoring, avoid ultra-high-cardinality metric labels like request IDs. Keep request IDs in logs/traces; aggregate metrics by service, region, endpoint class, and error category.

## 22. Cloud Logging Query Suggestions

The examples below are **suggested filter templates** for Logs Explorer; adjust resource types and log names to match your product, project, and logging setup. They do not enable logging by themselves.

Find Cloud NAT logs where supported:

~~~text
resource.type="nat_gateway"
severity>=WARNING
~~~

Find VPC Flow Logs for a subnet:

~~~text
resource.type="gce_subnetwork"
logName:"vpc_flows"
~~~

Find firewall/route changes or permission errors via audit logs:

~~~text
logName:"cloudaudit.googleapis.com"
protoPayload.serviceName="compute.googleapis.com"
~~~

During investigations, narrow the time window, project/host project, and target resources to reduce noise. Correlate failing request timestamps with `gcloud`/Terraform changes and telemetry; never blame a NAT warning if it does not match the failing source/destination.

## 23. Scenario 1: Private API Works Yet Public Website Times Out

**Context:** A VM without an external IP can read metadata from a Google API via PGA, yet calls to an external public website time out.

Plausible hypotheses:

1. PGA and routes to Google APIs are working.
2. The VM lacks Public Cloud NAT or an egress proxy to reach the public Internet.
3. NAT exists but does not cover that subnet/region, lacks IPs, or exhausted ports.
4. Egress firewalls block destinations or TCP 443 outside allowed API ranges.

Verification sequence:

- Confirm the IPs of both the API and website; separate Google API endpoints from the public Internet.
- Inspect external IPs, routes, and NAT coverage.
- Inspect egress firewalls and Cloud NAT logs/metrics.
- Use `curl` against an approved test endpoint to verify DNS/TCP/TLS.
- After fixing, test both the private API and public website to check for regressions.

**Takeaway:** Private Google Access is not general Internet access; adding a bucket IAM role will never fix a public website timeout.

## 24. Scenario 2: GKE Fails as Pod Count Scales Up

**Context:** An app runs cleanly with 5 Pods yet suffers timeouts or connection resets when scaling to 200 Pods, especially when calling external services.

Limit-focused checks:

- Which nodes or subnets host the failing Pods? Is the issue zonal/regional?
- Are NAT ports and allocated NAT IPs sufficient for peak concurrent connections?
- Is Pod traffic SNATed to node IPs or keeping secondary Pod IPs?
- Are there limits on endpoints, DNS caches, TCP connection pools, or external API quotas?
- Does HPA scaling Pods without scaling the database or external endpoint trigger a retry storm?

Do not blindly raise NAT ports if the real failure is HTTP 429 from the API. Likewise, do not open all firewalls when a single pool is exhausting connections. Measure active connections, HTTP status codes, and packet-level telemetry using approved tools.

**Takeaway:** load-dependent failures typically stem from capacity, connection lifecycles, or quotas—distinguish them from absolute configuration denies.

## 25. Scenario 3: Cloud Run Fails After Switching to `all-traffic`

**Context:** The team configures Direct VPC egress or a VPC connector with `all-traffic` to centralize egress control. After deployment, requests to Google APIs or public websites time out.

Steps:

1. Diff the previous and new revisions, focusing on network and egress settings.
2. Identify the region, subnet or connector, and source IP/range used.
3. Verify routes, effective firewall policies, and NAT coverage for public websites.
4. For Google APIs, check PGA, private/restricted/PSC DNS, and matching routes.
5. Check proxies, certificate stores, and IAM if TLS succeeds yet the API returns 403.
6. Use a canary revision or approved rollback if production is impacted; never open network-wide egress as a panic fix.

**Takeaway:** changing egress routing is a network architecture change, not just a single Cloud Run flag.

## 26. Scenario 4: `restricted.googleapis.com` Returns Permission Denied

**Context:** The workload resolves the API to the restricted VIP and completes TLS, yet operations return HTTP 403.

Checks:

- Is that specific Google API supported by `restricted.googleapis.com`?
- Is VPC Service Controls blocking the request due to perimeter membership, identity, ingress/egress rules, or project?
- Does the service account hold IAM roles on the target resource, and is the API enabled?
- Do the endpoint hostname and API method match?
- Do error details distinguish VPC SC from IAM?

Once the Google API returns 403, adding Cloud NAT or tweaking firewalls will rarely solve the root cause. Never switch to `private.googleapis.com` to "bypass" VPC Service Controls if it is a mandatory organizational security control.

**Takeaway:** investigate service-layer denials using policy and identity evidence rather than stripping network controls.

## 27. Step-by-Step Investigation Runbook

**Step 1 – Classify impact.** Record project/region, source, destination FQDN/IP:port, timestamp, error message, and frequency. Select a safe, repeatable test request.

**Step 2 – Verify endpoint resolution.** From the failing VM/Pod/service, check DNS and proxies. If DNS is wrong, fix resolver settings or DNS zones within scope first.

**Step 3 – Inspect the path.** Identify the actual VPC/subnet and source; verify routes, next hops, Shared VPC host projects, and firewall policies. Run Connectivity Tests where applicable.

**Step 4 – Confirm egress mechanism.** Is there an external IP? Is Public NAT or PGA needed? Does the Google API endpoint use private/restricted VIPs or PSC? Does configuration cover the source subnet/range?

**Step 5 – Test live behavior.** Use `curl`, TLS probes, and logs from the same time window. If connectivity fails, keep investigating networking; if an HTTP/gRPC response arrives, pivot to IAM, VPC SC, quotas, or API semantics.

**Step 6 – Apply the minimal fix.** Change exactly one component: DNS record, route, firewall policy, NAT coverage, PGA flag, service account permission, or API setting. Review permissions and blast radius before applying.

**Step 7 – Verify.** Repeat the originally failing request, validate the business response, and cross-check firewall/NAT/API logs. Test a related journey to catch regressions.

**Step 8 – Close the incident.** Document root cause, evidence, remediation timestamp, approver, regression tests, and IaC updates. Revoke any temporary rules or permissions; never leave permanent exceptions.

## 28. Mistakes to Avoid

| Mistake | Why Dangerous | Right Approach |
| --- | --- | --- |
| Granting Editor/Owner because an API returns 403 | Over-privileges principals and does not fix VPC SC | Find the denied permission and principal |
| Opening `0.0.0.0/0` egress on all ports to test | Increases data exfiltration risk | Use minimal, approved, time-bound rules |
| Adding NAT for every Google API failure | Ignores Private Google Access and DNS | Verify the actual endpoint and egress path |
| Using `ping` to prove HTTPS works | ICMP may be blocked separately and never tests TLS | Test TCP 443 and actual responses |
| Treating absence of logs as absolute proof | Logging may be disabled or sampled | Correlate multiple telemetry sources |
| Confusing Cloud Run `private-ranges-only` and `all-traffic` | Investigates the wrong VPC/NAT path | Inspect revision and network egress settings |
| Forgetting the Shared VPC host project | Inspects the wrong firewalls, subnets, and NAT | Start from network interface and subnet owner |
| Checking only node IPs while ignoring Pod SNAT | Misconfigures NAT source ranges | Verify post-NAT/masquerade source addresses |
| Disabling VPC SC to debug 403 | Breaks security boundaries | Use audit/error details and approved policy updates |
| Changing multiple layers at once | Obscures root cause and complicates rollback | One hypothesis – one change – one measurement |

## 29. Hands-On Exercise: Three Failure Modes on One API

**Context:** A Java/Spring application calls Cloud Storage from three environments: a private VM, a GKE Pod, and a Cloud Run revision. The team aims to eliminate timeouts and permission errors without granting broad access.

Set up the exercise in a properly authorized sandbox project. Never break production configurations or create public rules to simulate failures.

1. Identify the project, VPC, subnet, workload identity, and Cloud Storage endpoint for each source.
2. Record DNS resolution, routes, effective firewalls/policies, and egress mechanisms.
3. Using an approved test configuration, simulate a DNS misconfiguration or wrong endpoint; prove DNS is the root cause and fix it.
4. On the VM without an external IP, compare accessing Google APIs via PGA against accessing a public website via Public NAT.
5. On GKE, identify the source Pod/node IP and the impact of a NetworkPolicy in a test namespace.
6. On Cloud Run, compare `private-ranges-only` versus `all-traffic` within authorized deployment permissions.
7. Execute an unauthorized API call against a dummy resource, capture HTTP 403 and error details; do not alter firewalls to fix it.
8. Capture logs/metrics proving the request reached the failing layer.
9. Propose the minimal fix, re-test the exact endpoint, and verify no out-of-scope permissions were opened.
10. Compile the runbook and persist the final configuration in IaC.

**Deliverables:** a source/destination/route/DNS/egress summary table, four categories of evidence (DNS, network, TLS, API), root cause conclusion, required change, post-fix verification, and a rollback checklist. Never fabricate numbers or service states as if live measurements were executed.

## 30. Pre-Closure Incident Checklist

- Confirmed exact source, project, VPC/subnet, and Shared VPC owner (if applicable).
- Recorded FQDN, IP, protocol, port, and error message for the same test request.
- Verified DNS directly from the failing VM/Pod/container or resolving proxy.
- Checked routes to the destination IP and the actual egress path.
- Checked effective firewalls/policies, rule selectors, and workload NetworkPolicies.
- Distinguished VMs with external IPs, Public NAT, PGA, PSC, PSA, and serverless egress.
- Verified NAT region, subnet/source range coverage, and IP/port capacity under load.
- Confirmed private/restricted Google API VIPs and private DNS are used properly without bypassing VPC SC.
- Verified TLS without disabling certificate validation.
- Classified HTTP/gRPC status codes; avoided confusing 401/403/429 with network timeouts.
- Verified IAM, scopes, API enablement, organization policies, and VPC Service Controls where applicable.
- Correlated firewall, VPC flow, NAT, DNS, and API audit logs within the same timeframe, accounting for sampling limits.
- Applied least-privilege fixes with rollback plans and regression tests.
- Confirmed no unapproved temporary rules, tokens, or egress paths remain.
- Documented evidence-backed RCA and updated IaC/runbooks to prevent recurrence.

Troubleshooting firewall, NAT, and Google API access failures on GCP must begin by tracing **the actual request path**, rather than opening firewalls or adding NAT by guesswork. DNS determines the destination, routing and policies govern transmission, Cloud NAT or Private Google Access provides the right egress path, and IAM plus VPC Service Controls decide whether the API accepts the operation. By separating layers and pinpointing where failures occur, operations teams can restore service faster while keeping security boundaries, auditability, and costs under control.
