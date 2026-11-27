# Traffic Control, Network Logging, and Connectivity Troubleshooting

## 1. Why Design Network Controls and Observability Together?

An application deployed successfully to the cloud does not automatically have accurate, secure, and maintainable network paths. A Booking API may run fine in testing yet fail in production because DNS resolves to the wrong private address, a return route is missing, a firewall blocks health checks, NAT runs out of connection capacity, or the backend responds slowly.

**Network traffic control** defines who can connect where, over which protocol, and along which path. **Network logging** captures telemetry from checkpoints along the path for operations, access investigations, and anomaly detection. **Connectivity troubleshooting** correlates those signals layer by layer—from name resolution and routing through TLS and application logic.

These three capabilities belong together. A policy may block dangerous traffic accurately, yet without tests and logs it is hard to tell if legitimate traffic was harmed. Conversely, collecting massive logs without owners, retention policies, and clear investigation questions only drives up costs.

This lesson belongs to the **CLOUD_ARCHITECTURE** module and focuses on designing network paths when moving applications to the cloud while balancing **reliability, security, scalability, performance, cost, and operations** under the Well-Architected mindset.

### Learning Objectives

After this lesson, you will be able to:

1. Distinguish ingress, egress, east-west, and hybrid connectivity flows.
2. Explain the roles of routing, DNS, firewalls, ACLs, security groups, load balancers, WAF, NAT, and IAM.
3. Build a least-privilege traffic matrix based on source, destination, protocol, port, and business need.
4. Read and correlate flow logs, DNS logs, firewall logs, load balancer logs, and application traces without over-interpreting any single source.
5. Diagnose timeouts, connection refused errors, DNS/TLS/HTTP failures, and private/hybrid connectivity incidents.
6. Organize change-control workflows, alerts, and runbooks with verifiable acceptance criteria.

## 2. Map Traffic Flows Before Writing Policies

A diagram showing only VPCs/VNets and subnets is insufficient to evaluate connectivity. You must specify traffic traveling from **which source** to **which destination**, through **which control points**, and how you verify the path is healthy.

Suppose a booking system has external users, a Booking API, a managed database, a queue service, a payment provider, and an on-prem accounting system:

~~~mermaid
flowchart LR
    User["Internet users"] --> Edge["Public DNS / WAF / Load Balancer"]
    Edge --> API["Booking API - private workload"]
    API --> DB[("Private Booking DB")]
    API --> Queue[["Private queue endpoint"]]
    API --> NAT["Controlled egress / NAT"]
    NAT --> Pay["Payment provider"]
    Office["On-prem accounting"] <-->|"VPN / private connectivity"| Gateway["Hybrid gateway"]
    Gateway --> API
~~~

*This is a logical diagram. DNS resolves names rather than directly proxying HTTP requests; placement of WAF, load balancers, NAT, and private endpoints varies by cloud service.*

| Traffic group | Example | Design questions |
|---|---|---|
| **Ingress** | Internet → public endpoint → Booking API | Which entry points are exposed? Where does TLS terminate? Is the backend exposed directly? |
| **East-west** | API → DB, API → queue | Which services genuinely need to talk? Are paths segmented and authorized properly? |
| **Egress** | Booking API → payment provider | Where is the exit path, what is the post-SNAT IP, and who governs targets and cost? |
| **Hybrid** | Cloud ↔ on-prem via VPN/private link | Do CIDRs overlap, are DNS and bidirectional routes right, and is failover tested? |
| **Control plane** | Pipeline → cloud API modifying routes/firewalls | Who may change configs and who receives audits/alerts? |

**Data plane** carries live application traffic. **Control plane** comprises infrastructure configuration APIs and operations. Cloud audit logs recording control-plane changes do not capture individual data-plane packets.

### Template for Documenting a Connectivity Path

| Field | Example: Booking API → Database | Meaning |
|---|---|---|
| Source | Booking workload identity + private subnet | Who calls, and where does it originate? |
| Destination | Private DB hostname/endpoint | Which target may receive traffic? |
| Transport | TCP 5432 | Actual protocol and port |
| Business purpose | Read/write booking transactions | Why must this connection exist? |
| Security | DB authentication, TLS, network policy | Data protection and access control |
| Route | Private network path | Never detours unintentionally over Internet |
| Operational target | Per-journey timeout and error budget | Behavior when DB is unavailable |
| Evidence | Effective routes, flow logs, DB metrics, app traces | How to verify success and diagnose failures |

Any connection lacking an owner or business justification should be reviewed before granting permissive policies.

## 3. Layers Where a Connection Can Fail

**An open port does not guarantee a successful API response.** A request traverses multiple layers:

| Layer | Responsibility | Failure symptoms | Evidence sources |
|---|---|---|---|
| **DNS / service discovery** | Resolves hostname to endpoint | NXDOMAIN, SERVFAIL, wrong IP returned | Resolvers, private zones, DNS query logs |
| **Routing** | Selects next hop and return path | Unreachable target, wrong gateway | Effective routes, BGP, VPN/peering |
| **Network policy** | Allows/denies by IP, port, protocol | Timeouts, denies, resets depending on enforcement point | Effective firewall/ACL rules, flow logs |
| **NAT / proxy** | Translates addresses/ports, forwards, filters | SNAT port exhaustion, wrong source IP, proxy errors | NAT/proxy metrics and connection logs |
| **Load balancer** | Selects healthy backends and handles listeners | Unhealthy targets, 502/503/504 per platform | Listeners, target health, access logs |
| **Transport / TLS** | Establishes TCP/TLS sessions | SYN timeout, RST, SNI/certificate errors | Connection probes, TLS diagnostics |
| **Application / identity** | Handles HTTP, authorization, and dependencies | 401, 403, 404, 429, 5xx, slow requests | App logs, traces, auth logs, DB metrics |

### 3.1. How Does Stateful Differ from Stateless?

**Stateful firewalls/security policies** track connection state. Return packets belonging to an allowed session pass without needing a separate return rule at that same layer. AWS Security Groups and Azure Network Security Groups are common stateful examples.

**Stateless ACLs** evaluate each direction independently; some designs require explicit inbound and outbound rules covering return traffic and matching ephemeral port ranges. AWS Network ACLs are a stateless example.

A path can cross **multiple policy layers**. A stateful security group allowing traffic does not make an ACL or central firewall allow it automatically. Rule precedence, implicit rules, and deny semantics vary across platforms; inspect the **effective policy**, not just one rule labeled ALLOW.

### 3.2. Network Policies Do Not Replace IAM

Firewalls answer “who can connect to which endpoint”. IAM, workload identities, certificates, and app permissions answer “who can perform which action on which resource”. A DB in a private subnet still needs authentication and authorization; a WAF cannot stop an API bug that lets users view another customer's bookings if business authorization is broken.

## 4. Designing Ingress Controls

For public HTTPS apps, a sound pattern exposes a managed entry point while locking down backends:

1. Public DNS points to the public edge/load balancer.
2. Edge enforces TLS, certificates, and HTTP/WAF rules where needed; WAF primarily guards the HTTP(S) application layer and does not replace general TCP firewalls.
3. Load balancer distributes requests across healthy backends and runs health probes on the matching port/path.
4. Booking API accepts traffic strictly from valid ingress sources, avoiding direct public IPs on backends.
5. API authenticates, authorizes, and forwards internally to DB/queues per policy.

| Source | Destination | Protocol/port | Desired policy | Verification |
|---|---|---|---|---|
| Internet | Public load balancer | TCP 443 | Allow with TLS/WAF as required | HTTPS and LB access logs |
| LB and valid health-check sources | Booking API | TCP 8080 | Allow scoped strictly to LB/health | Healthy targets and request traces |
| Direct Internet | Private Booking API | TCP 8080 | No path / deny | Probe from outside scope |
| Direct Internet | Private DB | TCP 5432 | No path / deny | Network paths and effective policies |

The table expresses **design intent**, not universal firewall syntax. Exact health-probe source IPs, proxy modes, and LB–backend paths depend on the product. A new rule blocking health checks can cause the LB to mark every backend unhealthy even while the app is running fine.

**HTTP 403 does not automatically prove a firewall error.** It can come from a WAF, gateway, or the application. Likewise, 502/503/504 from an LB does not automatically mean bad routing: backends, timeouts, health checks, or downstream dependencies can also trigger them.

## 5. Egress Control: NAT, Proxies, and Private Endpoints

### 5.1. Source IP Visible Externally

Private workloads commonly call external partners via a NAT gateway or proxy. Source address translation (SNAT) makes the public IP/port differ from the container's internal IP/port:

~~~text
Before SNAT: 10.20.4.18:53124   -> 198.51.100.40:443
After SNAT:  203.0.113.17:41002 -> 198.51.100.40:443
Reply:       198.51.100.40:443  -> 203.0.113.17:41002
~~~

*198.51.100.0/24 and 203.0.113.0/24 are documentation-reserved IP ranges; port numbers are illustrative.*

Implications:

- Partners using **IP allowlists** need the post-NAT egress IP, not the app's private IP.
- **SNAT port exhaustion** occurs when active connections/ports outstrip capacity; limits and scaling options vary by product.
- Connection pooling, keep-alive, timeouts, retries, and workload sharing behind one NAT all drive active session counts.
- NAT does not automatically restrict every destination type and never replaces app-level partner authentication.
- Routing through NAT, central firewalls, or across zones/regions can incur substantial network charges.

When calling a managed cloud service, a **private endpoint/private connectivity** option may fit well if supported. However, verify endpoints, private DNS, routes, policies, IAM, and network associations together. Provisioning a private endpoint while workloads still resolve the hostname to a public IP is a very common misconfiguration.

### 5.2. East-West and Fault Isolation

Among internal workloads, open only genuinely required flows. Booking API may need the DB and queue; Notification worker does not automatically need production DB access. Enforcement may use security groups/NSGs/firewalls, Kubernetes NetworkPolicies, service mesh policies, and workload identities.

**Private IPs do not mean implicitly trusted.** A compromised internal workload can still call any target permitted by network rules and IAM. When locking down east-west traffic, account for DNS, time sync, health checks, secrets, telemetry, and platform endpoints so you do not break the very workload you are protecting.

## 6. Routing and DNS: Find the Root Cause Before Loosening Firewalls

### 6.1. Verify Outbound and Return Paths

Routing picks the next hop for packets; stateful appliances along the path normally must see both directions of a session. Common issues:

- **Overlapping CIDRs:** On-prem and cloud share colliding IP ranges, making routes ambiguous or preventing intended connections.
- **Missing return route:** Cloud knows how to reach on-prem, yet on-prem lacks a route back to the workload.
- **Asymmetric routing:** Outbound crosses firewall A while replies cross firewall B; sessions go unrecognized and get dropped.
- **False transit assumption:** Peering A–B does not automatically let A transit B to reach C; behavior depends on product and config.
- **Wrong next hop:** Traffic passes through an unintended NAT, firewall, or zone different from the diagram.

In most IP routing contexts, more specific prefixes win (longest-prefix match); tie-breaking among equal-length routes from different sources varies by cloud. Inspect **effective routes** on the exact subnet/interface plus routes advertised across hybrid gateways.

### 6.2. DNS and Private Configurations

- **NXDOMAIN:** The resolver states the name does not exist in the query context; check zones, records, and search suffixes.
- **SERVFAIL:** The resolver failed to complete lookup; check forwarders, upstreams, DNSSEC if applicable, and DNS availability.
- **Returns public IP instead of private:** Check private hosted/managed zones, network associations, resolvers, and split-horizon DNS.
- **Stale IP after change:** Inspect TTLs, resolver/app caches, and cutover timing.
- **DNS right yet TCP fails:** Move on to inspect routes, policies, listeners, and TLS.

**Run tests from the exact failing environment.** An ops laptop, staging VM, and production pod may use different resolvers, networks, and private zones and thus receive different DNS answers.

## 7. Classifying Network Logs and Observability Limits

No single log source explains the entire network path.

| Source | What it answers | Limitations |
|---|---|---|
| **VPC/VNet flow logs** | Source/dest IP, port, protocol, bytes/packets, action, timestamps per service | Usually no payloads; ACCEPT does not prove app success; may sample/aggregate |
| **Firewall logs** | Which rule allowed/denied which traffic, sometimes NAT and threat verdicts | Cannot see application-layer handling |
| **DNS query logs** | Which hostname was queried, from which resolver, and what answer returned | Returning the right IP does not prove TCP/TLS works |
| **Load balancer access/health logs** | Which listener/target handled the request, status, timings, target health | Gateway error codes alone rarely pinpoint root cause |
| **NAT/proxy telemetry** | Translation state, connection counts, port errors, throughput per product | Not every service emits per-session records |
| **VPN/BGP metrics** | Tunnel/peer status, throughput, packet drops, route state | Tunnel UP does not prove apps can connect |
| **Host/container metrics** | Sockets, retransmissions, conntrack, readiness, pod policies | Does not reflect upstream cloud firewalls in front of the host |
| **Cloud audit logs** | Who modified routes, DNS, IAM, LBs, or policies and when | Records control-plane actions, not individual packets |
| **Application logs/traces** | Request IDs, timeouts, dependencies, business errors | Often unaware of which network layer dropped a packet |

Common service names include **AWS VPC Flow Logs**, **Azure Virtual Network flow logs**, and **Google Cloud VPC Flow Logs**. They differ in scope, fields, sampling, aggregation, delivery delay, and enablement. Never assume logs capture every packet or share identical schemas.

### 7.1. Sample Flow Log Record

~~~json
{
  "startTime": "2026-11-18T03:10:00Z",
  "endTime": "2026-11-18T03:11:00Z",
  "srcIp": "10.20.4.18",
  "srcPort": 53124,
  "dstIp": "10.20.8.25",
  "dstPort": 5432,
  "protocol": "TCP",
  "action": "ACCEPT",
  "bytes": 18452,
  "packets": 38,
  "interfaceId": "example-interface"
}
~~~

*This JSON schema is purely for learning analysis; it is not the exact native format of any specific cloud provider.*

Correlate the **5-tuple**: source IP, source port, destination IP, destination port, and protocol. Also ask: was this logged before or after NAT? Is it outbound or return traffic? Which enforcement layer does `action` reflect? How are timestamps and counts aggregated or sampled?

An **ACCEPT** record only proves that logging layer permitted/observed the flow per its semantics. The destination may still not be listening, certificates may mismatch, proxies may reject, or the API may error. A **REJECT** record must match the exact addresses, ports, timestamps, and vantage point before tying it to the incident.

**Missing logs do not prove zero traffic.** Logging might be disabled, filtered, sampled, delayed, captured on a different interface, or unsupported on that path. Confirm pipeline coverage and config before concluding.

### 7.2. Collect Logs with Appropriate Permissions and Retention

Flow logs, hostnames, IPs, request URLs, and timestamps can contain sensitive data. Define retention, encryption, access permissions, storage regions, sensitive-field masking, and deletion workflows per policy. Never dump tokens, passwords, or transaction payloads into logs for debugging. Packet captures can expose sensitive data; enable them only targeted, briefly, and under strict authorization.

## 8. Designing a Network Observability Pipeline

~~~mermaid
flowchart LR
    Flow["Flow / Firewall logs"] --> Collect["Collect + Normalize"]
    DNS["DNS / LB logs"] --> Collect
    Audit["Control-plane audit"] --> Collect
    Collect --> Store[("Log store: IAM + retention")]
    Store --> Search["Search / Investigation"]
    Store --> Detect["Detection rules"]
    Detect --> Alert["Actionable alert + owner"]
    NAT["NAT / VPN / LB metrics"] --> Monitor["Monitoring"]
    Monitor --> Alert
    Trace["Application traces"] --> Search
~~~

A practical pipeline needs:

1. **Clear coverage:** Which networks/subnets/interfaces have logging enabled; which managed services, gateways, NATs, or queues emit no flow logs?
2. **Correlatable timestamps:** UTC or explicit timezones, synced clocks, observation intervals, and ingestion latency.
3. **Correlation fields:** 5-tuple, network/interface, rule ID, request/trace ID, or connection ID where available.
4. **Pipeline self-monitoring:** Dropped logs, parse failures, ingestion lag, quotas, and storage usage.
5. **Actionable alert ownership:** Alerts state impact, recipient, evidence, and runbook links.
6. **Governance and cost:** Filter required sources, set sensible retention, and track log cost attribution.

| Metric | What it supports | Interpretation caveats |
|---|---|---|
| DNS SERVFAIL/NXDOMAIN per resolver | Detects naming failures for critical services | NXDOMAIN may come from clients querying non-existent names; check context |
| Firewall denies by rule/target | Spots bad policies or unwanted traffic | High denies do not always mean user-facing impact |
| LB healthy targets and target errors | Detects unhealthy or slow backends | Broken health checks also mark healthy apps unhealthy |
| NAT port/connection utilization | Predicts outbound connection exhaustion | Metric names and caps differ across providers |
| VPN/BGP tunnel/peer health | Monitors hybrid interconnects | Tunnel UP does not guarantee routes and apps work |
| Egress traffic and log ingestion | Tracks cost and anomalous flows | Correlate against business traffic and real paths |

## 9. Layer-by-Layer Connectivity Troubleshooting Runbook

### Step 0: Capture Symptoms and Blast Radius

Gather source workload/subnet, destination hostname/IP/port, protocol, start time, environment, and user impact. Distinguish **NXDOMAIN, timeout, connection refused, TLS error, and HTTP 4xx/5xx**. Check recent changes to DNS, IAM, routes, security rules, deployments, TLS, and firewalls. Assign an incident owner and align time windows across all log sources.

### Step 1: Check DNS from the Exact Failing Source

Resolve the hostname from the pod/VM or an environment sharing the client's resolver. If the IP is wrong, inspect private zones, forwarding, search suffixes, records, and caches. If DNS is right, move on to routing instead of tweaking DNS further.

### Step 2: Check Outbound and Return Routes

Verify destination IP, effective routes, next hops, peering/transit, BGP/VPN, NAT/proxies, and return paths. Never assume one valid outbound route guarantees TCP completes. With stateful firewalls, verify replies return through the exact stateful checkpoint.

### Step 3: Check Policies at Every Layer

Inspect cloud firewalls/security groups/ACLs, container network policies, and proxies/service meshes if present. Check **post-NAT** source/destination where applicable, direction, protocol/port, priority, default deny, and connection state. Locate matching records in firewall/flow logs.

### Step 4: Check Listener, Transport, and TLS

Confirm the target port is listening, the load balancer sees healthy backends, and TCP handshakes complete. For SYN timeouts, RSTs, or retransmissions, inspect endpoints/networks further; for TLS errors, verify hostname, SNI, certificates, expiration, trust chains, and proxy settings.

**A failed ping does not prove TCP is blocked**, as ICMP may be blocked separately. Traceroute may also hide hops inside cloud networks; treat it only as supporting evidence.

### Step 5: Check HTTP, Auth, and Application Dependencies

When TCP/TLS succeed yet requests still fail, check WAF/gateway statuses, app logs, request IDs, and distributed traces. Timeouts can stem from DB locks, exhausted thread pools, queues, or slow upstreams rather than the network link.

### Step 6: Remediate Safely and Re-Verify

Fix the root cause with minimal scope via approved change processes. Retest **from the originally failing source**, verify both allowed and denied flows, re-measure SLOs/latency, monitor for a stabilization window, and document residual risk.

~~~mermaid
flowchart TD
    Start["Connection failed: source / dest / time"] --> Dns{"DNS returns right IP?"}
    Dns -- "No" --> FixDns["Resolver / zone / forwarding"]
    Dns -- "Yes" --> Route{"Bidirectional routes valid?"}
    Route -- "No" --> FixRoute["Routes / NAT / VPN / transit"]
    Route -- "Yes" --> Policy{"Policies permit traffic?"}
    Policy -- "No" --> FixPolicy["Rules / direction / priority"]
    Policy -- "Yes" --> Transport{"Listener, TCP, TLS healthy?"}
    Transport -- "No" --> FixTransport["Health / port / cert / SNAT / MTU"]
    Transport -- "Yes" --> App{"L7 and application succeed?"}
    App -- "No" --> FixApp["WAF / auth / app trace / dependencies"]
    App -- "Yes" --> Verify["Re-test from source and confirm SLO"]
~~~

This flowchart is a suggested sequence and does not preclude testing multiple hypotheses in parallel when evidence is clear.

## 10. Practical Diagnostic Tools

Examples below use mock hostnames; run in authorized environments and avoid scanning production networks outside incident scope.

### 10.1. Name Resolution

~~~bash
# Run from the exact workload/network experiencing symptoms.
nslookup booking.internal.example
dig booking.internal.example A
dig booking.internal.example AAAA
dig booking.internal.example @10.20.0.2
~~~

Compare the default resolver against a targeted resolver. CLI DNS tools and application name-resolution libraries may use different caches or search domains, so reconcile results with actual runtime behavior.

### 10.2. TCP, TLS, and HTTP

~~~bash
# Check the exact TCP port.
nc -vz booking.internal.example 443

# Measure DNS lookup, TCP connect, TLS handshake, and total request time.
curl -sS -o /dev/null --connect-timeout 3 --max-time 10 \
  -w 'dns=%{time_namelookup} connect=%{time_connect} tls=%{time_appconnect} total=%{time_total} code=%{http_code}\n' \
  https://booking.internal.example/health

# Verify TLS handshake/certificate with SNI hostname.
openssl s_client -connect booking.internal.example:443 \
  -servername booking.internal.example
~~~

Never disable TLS verification flags to “fix” certificate errors in production. When enabling verbose HTTP output or packet captures, avoid exposing tokens, cookies, or personal data.

### 10.3. Windows PowerShell

~~~powershell
Resolve-DnsName booking.internal.example
Test-NetConnection booking.internal.example -Port 443
~~~

Working TCP does not prove the app is authorized or returning valid responses; if failures occur at HTTP, continue checking higher layers.

### 10.4. Packet Capture and Network Mirroring

Packet captures confirm SYN/SYN-ACK/RST, retransmissions, or MTU issues, yet only see traffic at the capture point. With cloud managed services, proxies, and NAT, never assume capturing on one host shows the entire end-to-end path. Payload capture must comply with authorization and data-protection policies.

## 11. Case Study A: 504 After Tightening Firewalls

**Context:** A public load balancer forwards HTTPS to a private Booking API. After a network rule update, users see 504 errors; backend CPU is low.

**Valid hypotheses:**

- Security rule blocked the LB source or health-check probes.
- Return route is wrong, so replies never reach the LB.
- Requests reach the backend, yet Booking stalls waiting on the DB/queue.
- Backend is not listening on the right port or fails health probes.

**Investigation:** Pinpoint where 504 originates from LB logs, target health, and upstream response times; then correlate the 5-tuple across flow/firewall logs and app traces. If targets went unhealthy with matching denies right at change time, inspect the rule change. If targets receive requests yet the app waits 30 seconds on the DB, opening LB ports will not fix the cause.

**Remediation:** Fix the exact rule/route or downstream dependency, verify health checks and booking journeys, and monitor error rates/latency post-change. Add assertions to network policy tests to prevent regressions.

## 12. Case Study B: Private Database Endpoint Failure

**Context:** Staging reaches a managed DB via private endpoint fine, while production reports timeouts. An engineer's laptop can reach the DB hostname.

| Evidence | Hypothesis to test | Remediation path |
|---|---|---|
| Production DNS returns public IP | Private zone not properly linked | Check zone associations, forwarding, and resolvers |
| DNS returns right private IP; TCP times out | Wrong routes or network policies | Check bidirectional routes, DB firewalls, and security rules |
| TCP connects yet DB rejects | Auth/authorization or TLS error | Verify DB identity, certificates, and permissions |
| Only one subnet/pod fails | Differing local network/identity config | Compare effective policies, DNS, and network attachments |
| No flow logs appear | Insufficient data to conclude | Verify logging enablement at the right point and delay/sampling |

A laptop is not the same origin as a production pod: DNS, VPN, source IP, routes, and permissions all differ. **Results from a laptop never substitute for testing from the failing workload itself.**

## 13. Case Study C: Payment Timeouts During Peak Hours

**Context:** Booking API calls a payment provider through NAT. During peak hours, connection errors climb while the DB stays healthy; the payment provider enforces an IP allowlist.

Distinguish among:

1. **SNAT port exhaustion** caused by excessive concurrent sessions or long-lived connections.
2. **Changed egress IP** after failover/rerouting, no longer present in the allowlist.
3. **Retry storm** inflating outbound requests far above true transaction volume.
4. **Partner rate limiting / slow processing**, even after TCP/TLS succeed.
5. **DNS/proxy shift** routing requests to a different endpoint.

Correlate NAT connection metrics/port-allocation errors, egress IPs, client connect times, HTTP statuses, and retry counts. If port exhaustion is confirmed, tune connection pools, keep-alive durations, concurrency, or scale NAT capacity per platform support. If the partner returns 429s, aggressive retries only worsen the outage.

## 14. Case Study D: VPN Reports Healthy Yet Hybrid Service Is Unreachable

**Context:** The VPN tunnel between on-prem and cloud is UP, yet office users cannot reach the private API.

Investigate in order:

1. Does on-prem client DNS return the right private IP? How are forwarders and private zones behaving?
2. Do CIDRs overlap across sides? Is the destination IP within advertised prefixes?
3. Do BGP peers or static routes provide both outbound and return paths for the exact prefix?
4. Do on-prem/cloud firewalls, stateless ACLs, and stateful devices allow the exact flow?
5. Do TLS, endpoints, and the application work when tested from an authorized source?
6. If backup tunnels exist, how are failover and asymmetric routing handled?

A healthy tunnel is only **one prerequisite for connectivity**, not proof the application works.

## 15. Change Control and Incident Runbooks

Network changes often carry wide blast radius. Any route/DNS/firewall change should record **owner, exact source/dest/port, before–after policy, potentially impacted flows, test results, rollback plan, and executor**. Use IaC and policy review wherever supported to curb drift.

Short runbook template:

~~~text
Incident: Booking API cannot connect to private DB
Incident owner: Booking on-call + Cloud Platform on-call
Time (UTC): ...
Source and destination: workload/subnet/IP:port -> hostname/IP:port
Impact: error rate / latency / affected SLO
Symptoms: DNS / refused / timeout / TLS / HTTP / auth

Evidence:
  1. DNS answer from failing source:
  2. Effective outbound/return routes:
  3. Effective network policies + flow/firewall logs:
  4. TCP/TLS probe + LB health + app traces:
  5. Changes near incident onset:

Confirmed hypothesis:
Scoped remediation change:
Retest result from original source:
Post-fix SLI/SLO:
Follow-ups for IaC, alerts, runbooks:
~~~

During recovery, test **both permitted flows and flows that must remain blocked** to avoid fixing an outage by blowing open the network. Postmortems must identify systemic causes, observability gaps, and regression prevention.

## 16. Well-Architected Trade-Offs

| Perspective | Architectural decision | Benefits and trade-offs |
|---|---|---|
| **Security** | Least-privilege network policies, private endpoints, ingress/egress controls | Shrinks attack surface while increasing rule and DNS management |
| **Reliability** | Health checks, redundant routes, timeouts, blast-radius limits | Eliminates single points of failure while demanding failover drills |
| **Performance efficiency** | Avoid extra network hops, tune connection pooling, optimize paths | Cuts latency and SNAT pressure while preserving isolation |
| **Cost optimization** | Tune log retention, NAT/firewall/gateways, and traffic paths | Improves visibility while incurring log ingestion, cross-zone/region, and egress fees |
| **Operational excellence** | IaC, policy tests, runbooks, and owned alerts | Speeds diagnostics while requiring upfront tooling and process investment |
| **Sustainability** | Avoid hairpin traffic and excessive log retention | Cuts waste while still meeting security and recovery goals |

For example: forcing all outbound traffic through one central firewall keeps policies uniform and centralizes visibility. At the same time, it can create bottlenecks, raise latency, inflate cost, and widen blast radius. Decide **which flows truly must cross that checkpoint**, which suit private endpoints or workload-local controls, what redundancy is required, and how outcomes are measured.

## 17. Anti-Patterns and Reasoning Fallacies

| Mistake | Problem | How to improve |
|---|---|---|
| “Ping failed so TCP must be blocked.” | ICMP may be blocked separately | Test the actual protocol/port and check logs |
| “Flow log ACCEPT means the API succeeded.” | Flow logs see one layer, not HTTP/DB status | Check TCP/TLS, LB status, and traces |
| “No flow log means zero packets.” | Could be missing coverage, lag, or sampling | Verify logging config and collection scope |
| “Just open 0.0.0.0/0 to unblock it.” | Creates security risk and won't fix routing/DNS | Pin down the 5-tuple and minimal policy |
| “Private endpoint makes DNS right everywhere.” | Private zones/forwarding may be missing in hybrid | Test resolution from real clients |
| “VPN is up so the app must work.” | Return routes, firewalls, TLS, and IAM can still fail | Inspect every layer |
| “502/504 is always a network bug.” | Backends, gateway timeouts, or dependencies can fail | Inspect LB logs and app traces |
| “Adding infinite retries fixes timeouts.” | Retry storms overload systems and exhaust ports | Bound retries with backoff/jitter and idempotency |
| “Capture full packets forever.” | Inflates cost and data-leak risk | Capture purposefully with tight access and retention |
| “Outbound route works so that's enough.” | Replies may take the wrong path or hit stateful drops | Verify return paths and NAT |

## 18. Production Connectivity Verification Checklist

- [ ] Owner, business reason, source/dest, protocol/port, direction, and grant duration documented.
- [ ] DNS tested from the exact source environment, returning the expected endpoint.
- [ ] Outbound and return routes valid; CIDRs, VPN/peering/transit, and NAT accounted for.
- [ ] All firewall/security group/ACL/pod policy layers checked for effective enforcement.
- [ ] Backends shielded from unintended Internet exposure; listeners and health checks active.
- [ ] TLS, authentication/authorization, and secrets management properly configured.
- [ ] Egress IPs, allowlists, NAT capacity, and quotas sized for projected peak load.
- [ ] Flow/firewall/DNS/LB/NAT/VPN logs or metrics available for investigation.
- [ ] Sampling limits, ingestion delays, and collection boundaries understood per source.
- [ ] Log access permissions, retention, encryption, and cost controlled.
- [ ] DNS outages, slow/unavailable dependencies, and timeout behavior tested.
- [ ] Alerts tied to user-journey impact, with clear owners, runbooks, and rollback steps.
- [ ] Both permitted flows **and** flows that must be blocked tested after changes.

## 19. Practice Exercise

**Scenario:** A company runs a Booking API in the cloud. Public LB → private app; app → DB private endpoint; app → payment provider via NAT. The platform team recently added a central firewall and updated private DNS. After the change, roughly 30% of booking-creation requests time out. From an engineer's laptop, the DB still resolves and connects using the old hostname; NAT metrics show rising connection errors under high load; firewall logs contain both ACCEPT and REJECT entries.

**Tasks:**

1. Diagram ingress, east-west, and egress, marking at least six potential failure points.
2. Propose three distinct hypotheses and state the evidence needed to refute each.
3. Explain why DB test results from an engineer's laptop do not represent a production Booking pod.
4. Lay out an investigation sequence checking DNS, effective routes, firewall/flow logs, NAT, LB, and app traces within the same time window.
5. Propose fixes if production DNS returns the wrong IP, return routes bypass the stateful firewall, or NAT exhausts ports.
6. Define verification tests before closing the incident: bookings, payments, latency under load, blocked flows, logs, and SLOs.
7. Compare two egress approaches: centralizing everything at the shared firewall vs. combining private endpoints with workload-scoped policies; detail trade-offs across cost, observability, and reliability.

**Self-check hints:** Never conclude from a single ACCEPT/REJECT record whose 5-tuple and timestamp do not match. First verify DNS from the exact pod, bidirectional routes, NAT placement, TCP/TLS, and per-request traces. **Multiple simultaneous faults** may exist: part of traffic hits bad DNS while NAT exhausts ports only under peak load. Back every fix with hard measurements.

## 20. Key Takeaways

Traffic control starts with a **map of required flows**, then enforces them across DNS, routing, network policies, NAT, load balancers, TLS, and application permissions. Network logs are **evidence at a specific observation point**, so understand coverage, semantics, and limitations before drawing conclusions.

When incidents strike, capture **source, destination, symptoms, onset time, and blast radius**, test layers systematically by hypothesis, fix the exact root cause, and re-verify the end-to-end user journey. This discipline keeps cloud architectures balanced across security, reliability, scalability, performance, cost, and operations rather than merely trying to “get the port open”.
