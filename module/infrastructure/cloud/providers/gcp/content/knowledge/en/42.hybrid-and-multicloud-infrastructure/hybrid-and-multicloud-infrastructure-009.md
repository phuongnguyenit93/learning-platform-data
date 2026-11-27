# Cross-Cloud Data Flows, Latency, and Egress Costs

A **hybrid and multicloud** system may run APIs on Google Cloud, process data on AWS or Azure, and still communicate with systems in an on-premises data center. Every API call, object copy, event emission, database sync, or log export can then cross network boundaries, increasing **latency**, **operational risk**, and **data transfer out (egress) costs**.

This lesson belongs to the **Hybrid and Multicloud Infrastructure** chapter of the **CLOUD_PROVIDERS_GCP** module. Within the module scope, learners explore Google Cloud from project organization, IAM, and VPCs to Compute Engine, GKE, Cloud Run, storage services, and databases. Through deployment scenarios, learners select services, secure resources, automate releases, and track reliability alongside cost. This lesson ties these topics together with a quantitative method: **map where data travels, measure how long it takes, determine who pays, and design to avoid sending useless data**.

After this lesson, you will be able to:

- Catalog data flows between GCP, other clouds, and on-premises, separating direction, volume, and billing ownership.
- Distinguish RTT, latency, throughput, bandwidth, jitter, packet loss, and application latency.
- Spot chatty applications, N+1 calls, sequential cross-cloud processing, and hairpin routing.
- Classify costs across internet egress, inter-zone, inter-region, VPN, Interconnect, NAT, CDN, and storage services.
- Estimate costs by GiB and pricing tiers without mistaking illustrative unit prices for actual rates.
- Use VPC Flow Logs, Cloud Monitoring, Cloud Billing Reports, and BigQuery billing exports to validate designs.
- Choose caching, batching, CDC, compression, async events, or moving compute closer to data to reduce latency and egress.

**Pricing note:** all unit prices in the arithmetic examples below are **pedagogical assumptions only**, not quotes from Google Cloud or any other cloud. Actual costs vary by service, SKU, location, tier, contract, and pricing policies at deployment time.

## 1. Data Flows Differ From Resource Diagrams

A diagram showing two VPCs and a database does not explain what happens when a user clicks "Place Order." The architecture team needs to know **who sends what information, where, how often, over which network path, and whether the data can be replayed**.

Minimum inventory attributes:

| Attribute | What to measure or determine |
|---|---|
| Source | Cloud, project/account, VPC, subnet, region, and emitting service |
| Destination | Cloud, location, endpoint, database, bucket, or receiving network |
| Direction | GCP → AWS/Azure, AWS/Azure → GCP, or to/from on-prem? |
| Payload | JSON, protobuf, images, logs, CSV/Parquet, database rows, or events |
| Volume | GiB/day, requests/second, bytes/request, peak throughput |
| Pattern | Synchronous RPC, async queue, snapshot, CDC, or batch |
| Frequency | Per request, per minute, hourly, or event-driven |
| Freshness | Does data need near real-time or tolerate 5–30 minute lag? |
| Latency | P50/P95/P99, timeouts, and end-to-end SLOs |
| Reliability | Retries, idempotency, checkpoints, ordering, and replay |
| Security | TLS/mTLS, IAM, data classification, encryption, egress allowlists |
| Cost owner | Team/project paying for data transfer, NAT, gateways, and processing |
| Observability | Logs, metrics, tracing, billing SKUs, and on-call owner |

### Three-cloud and data-center example

~~~mermaid
flowchart LR
    U["Browser"] --> WEB["GCP Cloud Run: frontend"]
    WEB --> API["GCP GKE: Orders API"]
    API -->|"Small query"| EXT["Cloud B: pricing service"]
    EXT -->|"Response"| API
    API -->|"Events"| ERP["On-prem ERP"]
    API -->|"CDC / batch"| LAKE["Cloud C: data lake"]
    API -->|"HTTP response"| WEB
~~~

There are **multiple distinct egress directions**:

1. Requests sent from GCP to Cloud B can incur data transfer out on GCP.
2. Responses sent from Cloud B back to GCP can incur data transfer out on Cloud B.
3. CDC/batch sent from GCP to Cloud C is a separate flow with a different pricing path.
4. Events sent from GCP to the data center may traverse Cloud VPN/Interconnect.
5. Frontend responses to the browser represent user-facing internet egress.

Aggregating everything as "GCP ↔ Cloud B: 5 TiB/month" makes invoice reconciliation difficult. Separate directions and identify the exact traffic-generating services.

## 2. Ingress, Egress, and Billing Boundaries

**Ingress** is data entering a metered resource/network boundary. **Egress** is data leaving it. In Google Cloud, standard internet network data transfer into GCP generally carries no transfer-in fee, though services receiving, writing, or processing data may still incur separate charges.

| Path type | Example | Where to check pricing |
|---|---|---|
| Internet out from GCP | VM/API returning results to another cloud or user | Internet data transfer out, product-specific SKUs |
| Network in to GCP | AWS sending responses to GCP | Sending cloud's fees, GCP receiver service fees if any |
| Inter-zone | VM zone A → VM zone B in same region | VPC inter-zone rates, service-specific exceptions |
| Inter-region | GCP region A → region B | GCP inter-region rates or service pricing |
| Cloud Storage → other cloud | Exporting objects from a bucket | Cloud Storage data transfer/operations/retrieval |
| Cloud VPN | Private networks over IPsec | Tunnel, network egress, and peer-side costs |
| Cloud Interconnect | Data center/provider connectivity | Ports, VLAN attachments, transfer out, and partner fees |
| Cross-Cloud Interconnect | GCP to a supported CSP | Google + remote cloud attachments/ports/data transfer |
| Cloud NAT | Private workloads reaching outbound endpoints | NAT processing/gateway and transfer out |
| Cloud CDN/Load Balancing | Caches or proxies serving content | Cache fill, serving, proxy data processed, and egress |

VM-to-VM VPC rates do not represent all of Cloud Run, Cloud Storage, BigQuery, or other managed products. Always verify the **exact product SKU, source/destination locations, and network tier**.

Sources: [VPC network pricing](https://cloud.google.com/vpc/pricing), [Cloud Storage pricing](https://cloud.google.com/storage/pricing).

## 3. Four Data Flow Patterns to Analyze Separately

### 3.1. Cross-cloud synchronous API

~~~mermaid
flowchart LR
    A["Orders API on GCP"] -->|"HTTP/gRPC"| B["Remote pricing API"]
    B -->|"Price response"| A
    A --> R["User response"]
~~~

**Pros:** reuses existing services with relatively straightforward logic.

**Risks:** RTT and remote cloud processing sit directly on the request critical path. A remote outage spikes timeouts, retries, and Orders API latency.

**Usually fits:** small payloads, bounded request rates, with timeouts/circuit breakers and fallback plans in place.

### 3.2. CDC or event streaming

~~~mermaid
flowchart LR
    DB["Cloud SQL GCP"] --> CDC["CDC / outbox"]
    CDC --> Q["Queue / transfer"]
    Q --> LAKE["Other cloud: data lake"]
~~~

Ships only changed records instead of full datasets. Monitor replication lag, schema evolution, ordering, duplicate delivery, replay, and dead-letter queues. Eventual consistency suits analytics or search indexes, not necessarily every payment transaction.

### 3.3. Bulk object/file transfer

~~~mermaid
flowchart LR
    CS["Cloud Storage GCP"] --> W["Transfer worker"]
    W --> L["Internet / Interconnect"]
    L --> OBJ["Object storage in other cloud"]
~~~

For large files, throughput, checksums, resumability, and integrity matter more than single-request API RTT. Parallel streams and checkpoints may be needed to avoid restarting full transfers on job failures.

### 3.4. Hybrid on-premises

~~~mermaid
flowchart LR
    APP["GCP workload"] --> VPC["Google VPC"]
    VPC --> LINK["HA VPN / Interconnect"]
    LINK --> DC["On-premises ERP"]
    DC --> LINK
    LINK --> VPC
~~~

Beyond bandwidth, inspect BGP, routes, CIDR overlaps, bidirectional firewalls, DNS, VPN encapsulation, packet loss, and failover mechanics. A private link **does not automatically turn a chatty API into a fast API**.

## 4. Placing Compute Near Data: Data Gravity

Data gravity describes the cost and friction of continuously moving large volumes of data across infrastructure boundaries. An ML job in another cloud that reads a 20 TiB dataset from GCP every day can cost more in networking than in compute.

Three approaches:

| Strategy | Benefit | Trade-off |
|---|---|---|
| Run processing near source data | Reduces egress and read RTT | Requires operating compute where data lives |
| Move data to existing compute | Leverages existing pipelines | Egress, consistency, storage duplication |
| Transfer subsets/aggregates/caches | Fewer bytes, fast local reads | Staleness, cache invalidation, schema sync |

For example, if a remote cloud only needs a 2% aggregate for dashboards, computing the aggregate at the source and sending 2% is usually wiser than copying the entire warehouse hourly. Still, verify CPU/BigQuery/ETL costs incurred to produce that aggregate.

**Principle:** evaluate volume *over time*. A one-time 10 TiB transfer may be reasonable during migration; transferring 10 TiB daily for months warrants redesign.

## 5. Distinguishing Latency, RTT, Throughput, and Bandwidth

| Concept | Unit | Meaning |
|---|---|---|
| Latency | ms | Total time an operation/request spends traversing the system |
| RTT | ms | Time for data to reach the destination and a response to return |
| Throughput | Mbit/s, GiB/s | Actual achieved transfer rate |
| Bandwidth/capacity | Gbit/s | Nominal link capacity |
| Jitter | ms | Variation in latency across measurements |
| Packet loss | % | Fraction of packets dropped or needing retransmission |
| TTFB | ms | Time to first response byte |
| P95/P99 | ms | Percentiles of request latency |

A 10 Gbit/s link can still deliver slow API responses if RTT is high, the target service is slow, DNS/TLS handshakes happen frequently, or the application makes many sequential RPCs.

### 5.1. Anatomy of an HTTPS request

A request on a fresh connection can go through:

~~~text
DNS resolution
→ TCP connection
→ TLS negotiation
→ Remote application / database processing
→ Response transfer
→ Client-side parsing
~~~

Do not blindly add every `curl` timing milestone together, since timestamps are measured from request start and phases may overlap or be skipped via connection reuse. HTTP/2 or gRPC with persistent connections reduces handshake overhead.

### 5.2. Latency budget

Suppose the Orders API targets a P95 under 400 ms:

| Component | Design budget |
|---|---:|
| Browser → GCP frontend | 50 ms |
| Frontend → Orders API | 40 ms |
| Business logic | 60 ms |
| Cross-cloud Pricing RPC | 150 ms |
| Database | 50 ms |
| Buffer | 50 ms |
| **Total budget** | **400 ms** |

This is a **latency budget** breakdown, not a probabilistic calculation for end-to-end P95: summing component P95s does not automatically equal the overall request P95. Measure distributed traces across services and observe real latency distributions.

## 6. When Multiple Round Trips Slow Requests Down

A checkout flow sequentially calls 4 APIs in another cloud. If the link has an 80 ms RTT and each call requires at least one round trip:

\[
T_{\text{min network}} \approx 4 \times 80 = 320\ \text{ms}
\]

This excludes processing, queuing, TLS handshakes, serialization, and database work. If 4 independent calls run in parallel, the critical path stays closer to the slowest single call than the sum of all four.

### 6.1. Cross-cloud N+1 queries

For instance, the Orders API fetches 100 products and then calls an Inventory API in another cloud 100 times to check stock counts. Waiting one RTT per call accumulates huge latency even if each payload is only a few bytes.

Improvements:

1. Use a bulk endpoint accepting multiple product IDs in one call.
2. Batch and dispatch concurrently with **bounded concurrency**.
3. Keep a local cache/read model near the caller if staleness is acceptable.
4. Sync inventory updates via events/CDC.
5. Avoid holding database transactions open while waiting on a remote cloud.

### 6.2. Retries are not free

When a remote API times out, the application may retry. Each retry generates extra requests/responses, potentially amplifying both egress and latency—especially when multiple service layers retry recursively.

Enforce deadline propagation, exponential backoff with jitter, circuit breakers, retry caps, idempotency keys, and alerts when retry rates spike.

## 7. Bandwidth-Delay Product and Large Data Transfers

For TCP, a high-bandwidth link with high RTT needs enough data **in flight** to utilize available capacity.

\[
BDP_{\text{bits}}=\text{Bandwidth (bit/s)}\times RTT(\text{s})
\]

Example with 1 Gbit/s bandwidth and 80 ms RTT:

\[
BDP=1,000,000,000\times0.08=80,000,000\ \text{bits}
\]

This equals roughly 10 MB of unacknowledged data in flight. If TCP receive windows/sender buffers are too small or packet loss is high, actual throughput can fall far short of 1 Gbit/s.

Factors affecting throughput:

- TCP congestion control, window scaling, and parallel stream count.
- Packet loss, retransmissions, and jitter.
- MTU/MSS over IPsec/VXLAN tunnels.
- Gateway encryption/decryption CPU, disk I/O, and storage request/s limits.
- Actual throughput quotas on attachments, VPN tunnels, or cloud services.
- Source/destination application backpressure.

An ICMP ping measuring RTT **does not prove** file-transfer throughput or HTTP P95 performance. Measure both RTT and representative transfer workloads.

## 8. Choosing Between Internet, VPN, and Interconnect

| Option | Pros | Constraints / costs |
|---|---|---|
| Public Internet + TLS | Fast setup, suits low traffic | Internet egress, endpoint hardening, network variance |
| HA VPN | IPsec connecting private networks | Tunnel-hours, data transfer, packet rate, MTU |
| Dedicated/Partner Cloud Interconnect | Private path from GCP to data center/provider | Ports, VLAN attachments, circuits, transfer out |
| Cross-Cloud Interconnect | Dedicated link between Google and supported CSP | Dual-cloud resources, physical provisioning, egress |
| Partner Cross-Cloud Interconnect | Partner-managed connectivity | Depends on region/provider and fee structure |
| Transit via on-premises | Reuses existing infrastructure | Hairpin adds RTT, double network boundaries and fault domains |
| Managed transfer/pipeline | Retries, checkpoints, built-in monitoring | Service processing/storage/ops + egress |

### 8.1. Cloud VPN

Cloud VPN is a site-to-site IPsec connection, **not** a general client internet gateway for a VPC. Individual tunnels have packet-per-second limits; real throughput depends on RTT, packet size, packet loss, IPsec overhead, and the peer gateway.

Monitor tunnel health, Cloud Router/BGP, transferred bytes, drops, and failover. For large file transfers, benchmark both single-stream and parallel-stream runs.

### 8.2. Cross-Cloud Interconnect

Cross-Cloud Interconnect establishes dedicated connectivity between Google Cloud and a supported CSP. Cost analysis must include:

- Ports/connections and VLAN attachments in Google Cloud.
- Ports/circuits/attachments at the peer provider.
- Data transfer out across the interconnect.
- Inter-region transfer if workloads reside in a different region than the attachment.
- Redundant links and operational/monitoring overhead.

Partner models vary in pricing structure; never apply dedicated connection rates across every partner option.

Sources: [Cross-Cloud Interconnect](https://cloud.google.com/network-connectivity/docs/interconnect/concepts/cci-overview), [Cloud Interconnect pricing](https://cloud.google.com/network-connectivity/interconnect/pricing).

### 8.3. Redundant paths

A single private connection still represents a single point of failure. Production designs may need attachments in distinct edge availability domains, dual Cloud Router/BGP sessions, geographic redundancy per SLA, route filters, and failover testing.

Cloud Router manages **BGP routing**, not a data-plane appliance forwarding individual application packets.

## 9. Network Misconfigurations That Inflate Latency and Egress

### 9.1. Overlapping CIDRs

GCP and another cloud sharing `10.0.0.0/16` causes routing conflicts. Enforce organization-wide IPAM or design explicit NAT/transit layers with unambiguous post-translation sources and destinations.

### 9.2. Wrong DNS and routing paths

Hostnames may resolve to public IPs instead of private endpoints. Creating a private link does not guarantee every application uses it. Verify DNS and routing **in both directions**, from Cloud Run/GKE/VM runtimes and from the peer provider.

### 9.3. MTU and fragmentation

VPN/IPsec encapsulation shrinks payload MTU. If Path MTU Discovery breaks or ICMP is blocked, small requests succeed while large file transfers stall. Monitor MSS, retransmissions, and gateway metrics.

### 9.4. Hairpin and asymmetric routing

Traffic from GCP → AWS might route through on-prem and back to AWS instead of a direct shorter path, while responses return via a different path. This adds RTT, multi-hop fees, and stateful firewall issues.

### 9.5. Security

Even over private links, protect APIs with TLS/mTLS, IAM, short-lived tokens, and least-privilege firewalls. Private networking is not authentication. For sensitive data, meet data residency requirements and never log raw payloads or secrets.

## 10. Complete Classification of Cost Components

Mental model:

\[
C_{\text{network}} \approx
\sum_i(\text{GiB}_i\times\text{rate}_i)
+\text{fixed link fees}
+\text{processing}
\]

Cost breakdown table:

| Item | Factors to include |
|---|---|
| GCP Internet data transfer out | Source product/region, destination, and usage tier |
| Peer cloud data transfer out | Return responses or reverse sync flows |
| Inter-region / inter-zone | Internal GCP hops, service-specific SKUs |
| Cloud VPN | Tunnel-hours and data transfer, plus peer-side charges |
| Interconnect | Ports, connections, VLAN attachments, egress, provider circuits |
| Cloud NAT | Uptime/data processed and internet egress |
| Load Balancer / CDN | Proxy processing, requests, cache fill, serving egress |
| Cloud Storage | Operations, retrieval, transfer out, and data storage |
| Network telemetry | Flow Logs, firewall logging, Cloud NAT logs, and retention |
| Pipeline compute | CPU/memory/worker hours for transforms/compression |
| Retries | Extra generated bytes and requests |

**One flow can generate multiple line items** across two providers. Billing may also apply tiered rates. Never multiply total traffic by a single flat rate/GiB if the pricing table uses volume tiers.

Cloud Interconnect carries dedicated data transfer rates and hourly port/attachment charges. If an attachment sits in a different region from the traffic-emitting workload, cross-region charges may accrue before traffic exits the attachment.

Sources: [VPC pricing](https://cloud.google.com/vpc/pricing), [Interconnect pricing](https://cloud.google.com/network-connectivity/interconnect/pricing).

## 11. Worked Example: Syncing Data Between Two Clouds

Suppose a GCP pipeline exports **1.5 TiB/day** to a data lake in another cloud over 30 days. We use an **illustrative unit price** of 0.08 USD/GiB, omitting real tiered discounts, peer-cloud charges, and other service fees.

### 11.1. Unoptimized

\[
V_{\text{month}}=1.5\times30=45\ \text{TiB}
\]

\[
45\ \text{TiB}\times1024=46,080\ \text{GiB}
\]

\[
C_{\text{illustrative}}=46,080\times0.08
=3,686.40\ \text{USD/month}
\]

### 11.2. Filtering 70% of data inside GCP

If downstream only needs 30% of rows/columns after aggregation:

\[
V_{\text{new}}=46,080\times0.30=13,824\ \text{GiB}
\]

\[
C_{\text{new}}=13,824\times0.08=1,105.92\ \text{USD}
\]

Difference:

\[
3,686.40-1,105.92=2,580.48\ \text{USD/month}
\]

| Option | GiB/month | Illustrative rate | Egress estimate |
|---|---:|---:|---:|
| Daily full copy | 46,080 | 0.08 USD/GiB | 3,686.40 USD |
| Send only 30% | 13,824 | 0.08 USD/GiB | 1,105.92 USD |
| **Savings** | **32,256** | — | **2,580.48 USD** |

Additional costs may include filtering compute, data pipelines, Cloud Storage operations, NAT, VPN/Interconnect, and destination-cloud charges. This is an **educational calculation model**, not a production invoice forecast.

## 12. Internet vs. Private Interconnect: TCO Comparison

Select connectivity based on **total cost of ownership (TCO)**, reliability, security, and latency SLOs—not simply price per GiB transferred.

~~~text
Internet_TCO =
  GCP_Internet_egress
+ Counterpart_cloud_egress_on_reverse_flows
+ NAT_LB_Storage_Processing
+ Network_operations

Private_TCO =
  GCP_connection_and_attachment_hours
+ Other_cloud_ports_and_circuits
+ Interconnect_transfer_out
+ Cross_region_data_transfer_if_applicable
+ Other_cloud_egress_and_transfer_fees
+ Network_processing_and_operations
+ Redundant_links
~~~

| Criterion | Internet + TLS | Private Interconnect |
|---|---|---|
| Upfront setup | Generally simpler | May require circuit/provisioning |
| Fixed link fees | Low or none | Ports/attachments/partner fees |
| Data transfer out | Internet SKU | Interconnect/partner SKU |
| Peer cloud fees | Possible | Possible plus attachment fees |
| Redundancy | Relies on endpoint/internet architecture | Must provision multiple links for HA |
| Jitter/latency | Depends on public internet | Can be more predictable depending on topology |
| Lead time | Shorter in most cases | Can be long for dedicated physical circuits |

Compare both options using identical traffic, directions, regions, SLAs, and security requirements. Never compare a single-link private circuit against multi-path internet connectivity and draw skewed reliability conclusions.

## 13. Reducing Egress Without Sacrificing Data Correctness

Group optimizations by **byte volume**, **call count**, and **transfer direction**, rather than blindly caching everything.

### 13.1. Reduce total bytes

- Use CDC/delta updates instead of full snapshots.
- Project only the columns and rows downstream genuinely needs.
- Aggregate near the source and ship only summary results.
- Use Parquet or columnar formats suited to analytics.
- Compress JSON/binary payloads when byte savings outweigh CPU/latency overhead.
- Track checksums or content digests to skip re-copying existing objects.
- Avoid exporting duplicate traces/logs to multiple providers unnecessarily.

Compressing already-compressed media like JPEG or MP4 yields little gain. Benchmark with real data. If filtering consumes heavy compute, include transform cost in TCO.

### 13.2. Reduce cross-cloud boundary crossings

- Batch multiple records into one RPC instead of N+1 calls.
- Use bulk APIs and sensible pagination.
- Place caches/materialized read models near request handlers.
- Use event-driven asynchronous transfers to decouple availability across clouds.
- Separate OLTP transactions from data exports and analytics.
- For ML, consider hosting inference models near the app while running heavy training in the other cloud.

### 13.3. Reduce coupling during peer-cloud outages

- Propagate deadlines from frontend to downstream calls.
- Retry with exponential backoff + jitter and total-duration caps.
- Use circuit breakers, bounded queues, and backpressure.
- Attach idempotency keys to events with side effects.
- Enforce concurrency limits to avoid saturating links or remote APIs.
- Alert when queue lag or retry rates climb.

**Never casually cache pricing, inventory, payment, or sensitive data.** Align on TTLs, invalidation mechanisms, encryption, access controls, and staleness limits with business owners.

## 14. Synchronous vs. Asynchronous: Choosing by Consistency

| Attribute | Synchronous RPC/HTTP | Asynchronous CDC/event/batch |
|---|---|---|
| Freshness | Can reflect state at call time | Lags behind by replication delay |
| User latency | Depends on remote RTT and service | Local reads are typically faster |
| Data transfer | Per request/response | Per delta or batch |
| Peer cloud outage | Can cascade failures into requests | Queues allow deferred retries |
| Consistency | Simpler for certain reads | Requires ordering, dedupe, and reconciliation |
| Complexity | Easy to start, risky if chatty | Requires operating pipelines and schema versions |

For checkout requiring payment confirmation, a safely bounded synchronous flow may remain necessary. For hourly revenue reports, a few minutes of lag is completely acceptable and suits CDC/batching.

Both models require defining the **source of truth**. Letting both GCP and another cloud write to independent primary databases without a designed multi-writer consistency protocol invites data divergence or split-brain.

## 15. SLOs and Latency Budgets for Cross-Cloud Dependencies

When a dependency incurs high RTT, API/SRE/Network teams must agree on:

1. End-to-end SLO, e.g., P95 checkout under 400 ms.
2. Time allocated per call and overall deadline.
3. Maximum remote service timeout.
4. Whether fallback/degraded modes exist.
5. Which data can be cached and maximum acceptable staleness.
6. Maximum retry attempts to prevent unbounded egress growth.
7. Targets for connection reuse, error rates, and packet loss.
8. Alert thresholds when SLOs are threatened.

Illustrative budget table:

| Flow | P95 budget | Separate error budget | Owner |
|---|---:|---|---|
| Browser → Cloud Run | 80 ms | Per frontend SLO | Web team |
| Cloud Run → GKE API | 40 ms | Per API SLO | App team |
| GKE → remote pricing | 150 ms | Has fallback/cache | Integration team |
| GKE → local Cloud SQL | 50 ms | Zero lost transactions | Data team |
| Business processing/buffer | 80 ms | Per business rules | App/SRE |
| **Design total** | **400 ms** | — | Product/SRE |

These figures are **component budgets**, not a guarantee that the overall P95 equals the sum of component P95s. Measure end-to-end traces.

## 16. Measuring Latency at the Right Layer

### 16.1. Distributed tracing

~~~text
checkout request
  ├─ auth
  ├─ local Cloud SQL query
  ├─ cross-cloud pricing request
  │   ├─ connection / TLS (if new)
  │   ├─ remote service processing
  │   └─ response transfer
  └─ order commit
~~~

Tag spans with service, cloud, region, dependency name, and retry count. Never record tokens or sensitive payloads. When P95 rises, pinpoint whether time was spent in networking, remote compute, databases, or queues.

### 16.2. curl timing

Example measuring an authorized HTTP endpoint:

~~~bash
curl --silent --show-error --output /dev/null \
  --write-out 'dns=%{time_namelookup} connect=%{time_connect} tls_until=%{time_appconnect} ttfb=%{time_starttransfer} total=%{time_total}\n' \
  https://api.example.com/health
~~~

All values are cumulative timestamps **from request start**, not independent durations to sum together. On a fresh TLS handshake, TLS time alone can be approximated as `time_appconnect - time_connect`; with connection reuse, results differ.

### 16.3. Throughput benchmarking

Across **two endpoints authorized by your organization for testing**, measure:

- Single stream and multiple parallel TCP streams.
- Peak and off-peak throughput.
- RTT, jitter, packet loss, retransmissions, and CPU.
- MTU/MSS and VPN encryption overhead.
- Data checksums, retry counts, and total transfer elapsed time.
- Actual application throughput rather than raw link line rate.

Never run heavy load tests against production environments or unapproved partner endpoints. Benchmarking tools belong to capacity-testing runbooks, not replacements for production metrics.

## 17. VPC Flow Logs and Network Monitoring

**VPC Flow Logs** sample network traffic and aggregate by 5-tuple (source/destination IP, port, protocol). Where supported, they can observe VM/GKE traffic, Cloud Run with Direct VPC egress, and traffic traversing Cloud VPN or Cloud Interconnect VLAN attachments.

Questions Flow Logs help answer:

- Which flows send the most bytes outside GCP?
- Is unexpected traffic crossing regions or public internet paths?
- After a new deployment, did outbound connections to another cloud spike?
- Is a source VPC/subnet communicating with an unapproved endpoint?
- Are there signs of network hairpinning or failed connections to investigate?

**Critical limitation:** Flow Logs use sampling and aggregation. They are not a complete meter for **reconstructing exact invoices**. Discrepancies against billed bytes also stem from protocol overhead, SKUs, and resource scopes. Use Flow Logs to diagnose causes; use Billing exports for financial reconciliation.

### 17.1. Metrics to track

| Metric | Source | Meaning |
|---|---|---|
| Request latency P50/P95/P99 | Cloud Monitoring/Trace | Impact on SLOs |
| Error rate/retries | App metrics | Traffic-amplifying incidents |
| Bytes sent/received | Network/service metrics | Volume trends |
| VPN status, throughput | Cloud VPN metrics | Capacity/tunnel health |
| Interconnect attachment throughput | Interconnect metrics | Utilization |
| Loss/retransmissions | Host/network telemetry | Throughput degradation |
| Queue depth/CDC lag | Data pipeline metrics | Freshness and backlogs |
| Cache hit ratio | CDN/application cache | Egress-reduction effectiveness |
| Cost per SKU | Cloud Billing Reports/BigQuery | Actual financial cost |

### 17.2. Cost of observability

Network telemetry logs can incur vended-log, storage, export, and BigQuery fees; sampling and retention require deliberate guardrails. Never enable maximum-verbosity logging org-wide without evaluating cost and sensitive-data exposure.

Sources: [VPC Flow Logs](https://cloud.google.com/vpc/docs/flow-logs), [VPC Pricing](https://cloud.google.com/vpc/pricing).

## 18. Cloud Billing Reports: Finding Egress Charges

In the Google Cloud Console, open **Cloud Billing → Reports**. Teams should:

1. Filter by billing account, project, service, and time range.
2. **Group by SKU** to surface data-transfer line items.
3. Inspect each product: Networking/Compute Engine, Cloud Run, Storage, Load Balancing, and others.
4. Compare week-over-week before and after deploying architectural changes.
5. Correlate rising SKUs with flow IDs, byte volumes, and traces.
6. Set budget alerts per project or service group.
7. Check pre-credit and post-credit totals matching the organization's financial reporting standards.

Never filter by a single service name and assume it captures all egress: transfer charges can appear under SKUs across multiple products.

Source: [Billing Reports](https://cloud.google.com/billing/docs/how-to/reports).

## 19. Exporting Billing to BigQuery to Measure by SKU

Cloud Billing standard/detailed usage exports provide service, SKU, project, location, cost, usage, credits, currency, and related metadata. For granular analysis, enable billing export in advance; backfill availability depends on dataset location and export type.

The illustrative SQL below aggregates by day, project, and SKU. The table name is a **placeholder**; replace it with your real export table (if the project ID contains hyphens, wrap the table name in backticks per BigQuery syntax):

~~~sql
SELECT
  DATE(usage_start_time) AS usage_day,
  project.id AS project_id,
  service.description AS service_name,
  sku.description AS sku_name,
  currency,
  ROUND(SUM(cost), 2) AS cost_before_credits,
  ROUND(
    SUM(
      cost + IFNULL(
        (SELECT SUM(c.amount) FROM UNNEST(credits) AS c),
        0
      )
    ), 2
  ) AS cost_after_row_credits
FROM
  BILLING_PROJECT.BILLING_DATASET.gcp_billing_export_v1_XXXXXX
WHERE
  usage_start_time >= TIMESTAMP('2026-11-01')
  AND usage_start_time < TIMESTAMP('2026-12-01')
  AND (
    REGEXP_CONTAINS(
      LOWER(sku.description),
      r'egress|data transfer|network|interconnect|vpn|nat'
    )
    OR REGEXP_CONTAINS(LOWER(service.description), r'networking')
  )
GROUP BY
  usage_day, project_id, service_name, sku_name, currency
ORDER BY
  usage_day DESC, cost_before_credits DESC;
~~~

Notes:

- The regex is an **exploratory** filter, not guaranteed to match every egress SKU. Switch to an explicit **SKU ID allowlist** after inspecting real invoices.
- Cost after line-item credits may not equal the final invoice total (due to taxes, adjustments, or invoice-level items).
- Never sum amounts across different currencies.
- Billing export datasets have latency and are not suited as real-time network meters.
- For team chargeback, apply consistent labels to resources or pipelines for grouping.

Source: [Export Cloud Billing data to BigQuery](https://cloud.google.com/billing/docs/how-to/export-data-bigquery).

## 20. Lab: Optimizing Orders API and ML in Another Cloud

Suppose a company operates:

- Orders API on Cloud Run, with its transactional database on Cloud SQL in the same region.
- ML training in another cloud.
- An ERP in an on-premises data center receiving orders via events.
- Analytics requiring summaries every 5 minutes.

### 20.1. Option A: requests dependent on the other cloud

~~~mermaid
flowchart TD
    USER["Users"] --> ORD["GCP Orders API"]
    ORD --> SQL["Cloud SQL"]
    ORD --> ML["Remote ML API"]
    ML --> DB2["Remote feature store"]
    ORD --> ERP["On-prem ERP"]
~~~

Risks:

- Checkout waits on the remote ML API/feature store.
- ML responses may be large, generating transfer-out charges in the other cloud.
- When remote ML times out, retries inflate latency and bytes.
- When the ERP slows down, synchronous calls hold transaction resources open too long.

### 20.2. Option B: decoupling inference and data transfer

~~~mermaid
flowchart TD
    SQL["Cloud SQL GCP"] --> CDC["CDC/delta export"]
    CDC --> AGG["Filter/aggregate"]
    AGG --> TRAIN["ML training in other cloud"]
    TRAIN -->|"Model artifact/version"| MODEL["Inference near GCP Orders API"]
    MODEL --> ORD["Orders API"]
    ORD --> Q["Durable event queue"]
    Q --> ERP["On-prem ERP"]
~~~

This shifts the workload from many **small synchronous RPCs** to controlled periodic data/model synchronization. Hosting model inference near the Orders API cuts checkout RTT and removes a remote synchronous dependency. Still, verify freshness, data residency, compute/model-serving cost, and prediction accuracy.

### 20.3. Complete the flow register

| Flow ID | Source → Destination | Pattern | Data/SLO to measure |
|---|---|---|---|
| F1 | Orders API → Cloud SQL | Synchronous local | Query P95, connections |
| F2 | GCP → ML training cloud | Batch/CDC | GiB/day, retries, freshness |
| F3 | ML cloud → GCP model artifact | Versioned transfer | Artifact size, checksums, provenance |
| F4 | Orders API → ERP | Async event | Queue lag, idempotency, throughput |
| F5 | Orders API → browser | HTTP | Response P95, bytes, CDN |

Learners should calculate bidirectional volumes, verify matching pricing SKUs, measure SLOs, and propose at least one high-impact optimization.

## 21. Experimentation Plan for Changes

1. **Baseline:** measure 7–14 days of bytes, P95/P99 latency, retry counts, cache hit rates, and billing.
2. **Hypothesis:** e.g., "switching from full copies to CDC will cut outbound GiB by ≥60% while keeping data freshness within 10 minutes."
3. **Controlled change:** test in staging or a small canary.
4. **Measure:** raw bytes/responses, data transfer by route, errors, cloud billing, lag, and consistency.
5. **Security review:** IAM, encryption, network paths, data residency, and log redaction.
6. **Compare:** before/after TCO and SLOs over equivalent traffic periods.
7. **Decision:** keep or roll back, recording owners and remaining follow-ups.

Never extrapolate a 5-minute off-peak measurement to 12 months. Month-end batches, backups, error/retry storms, and seasonal peaks alter volume dramatically.

### Illustrative acceptance criteria

| Metric | Before | After optimization | Measured via |
|---|---|---|---|
| GCP outbound data transfer | 1.5 TiB/day | ≤0.6 TiB/day | Billing + network/app metrics |
| Checkout P95 | 600 ms | ≤400 ms | Distributed traces |
| Data freshness | Direct query | ≤10 minutes | CDC lag |
| Duplicate event side effects | Uncontrolled | 0 in idempotency tests | Business tests |
| Monthly network cost | Actual baseline | ≥30% reduction | Billing SKU report |
| Link availability | Unknown | Meets approved SLO | VPN/Interconnect metrics |

These numbers are exercise targets, not default GCP thresholds.

## 22. Common Mistakes

| Symptom | Common cause | How to inspect |
|---|---|---|
| Egress bill rises while requests stay flat | Large responses, log exports, retries, backups, cross-region fetches | Billing SKUs, flow logs, release timeline |
| P95 slow only on one cloud | RTT, DNS/TLS, remote APIs, packet loss | Distributed tracing and RTT/packet metrics |
| VPN packet loss or low throughput | MTU/MSS, encryption CPU, peer capacity, retransmits | Tunnel metrics and controlled benchmarks |
| 10 Gbit/s link yet slow file copies | Single stream/window/RTT or storage IOPS | BDP, parallel transfers, source/destination I/O |
| Flow Logs bytes do not match bill | Sampling/aggregation and billing product scope | Flow Logs for diagnostics, Billing export for finance |
| Traffic uses internet despite private link | Public DNS, wrong routes/BGP advertisements | Check routes/DNS on both sides |
| Unit confusion | Mixing up GB/GiB, Gbit/s/GB/s | Standardize units and chart labels |
| Cache lowers bill yet serves stale data | TTL/invalidation misaligned with business rules | Freshness contract tests |
| CDC lag grows | Backlogs, under-provisioned workers, retry loops | Queue metrics, replication lag, DLQs |
| Interconnect bill spikes | Attachment in different region from source or unneeded ports | Pricing by location and resource |
| Both clouds charge data transfer | Bidirectional traffic; each provider has separate SKUs | Separate source/destination per flow |
| Unexpected NAT cost | Gateway processing and generated traffic | NAT SKUs, routes, egress volume |

## 23. Multi-Cloud Architecture Checklist

- [ ] Data flow diagram lists sources, destinations, regions, and transfer directions.
- [ ] Measured GiB/day, peak MiB/s, requests/s, and response sizes.
- [ ] Distinguished ingress, internet egress, inter-zone, inter-region, and interconnect charges.
- [ ] Verified pricing tables by exact product/SKU, destination, and usage tiers.
- [ ] Accounted for peer-cloud fees, NAT, VPN, Interconnect, LBs, storage, logs, and compute.
- [ ] Measured RTT, P95/P99, throughput, jitter, loss, and retries on real workloads.
- [ ] Identified synchronous fanout/N+1 calls and timeout budgets.
- [ ] Selected Internet/VPN/Interconnect based on SLOs, security, TCO, and volume.
- [ ] Checked CIDRs, routes/BGP, DNS, firewalls, and MTU.
- [ ] Never assumed a private link makes egress free.
- [ ] Applied batching/CDC/caching/filtering/compression where data semantics permit.
- [ ] Enforced idempotency, replay, bounded retries, and error handling.
- [ ] VPC Flow Logs and billing exports have retention/filter/cost guardrails.
- [ ] Budgets, budget alerts, and owners assigned per data flow.
- [ ] Verified encryption, IAM, data residency, and zero sensitive data leaked in logs.
- [ ] Canaries and failover tests executed before production.
- [ ] Periodic architecture reviews scheduled as data volume or pricing changes.

## 24. Self-Check Questions

**1. Why separate GCP → Cloud B and Cloud B → GCP traffic?**

Each direction has a different source and volume. Small requests from GCP can trigger large responses from Cloud B, generating most data transfer out on Cloud B.

**2. Does free GCP ingress mean receiving data never costs money?**

No. Standard network transfer-in may be free, yet services receiving/writing/processing data, load balancing, and storage operations can still incur separate fees.

**3. Why is high bandwidth insufficient for low API latency?**

RTT, DNS/TLS handshakes, remote processing, request fanout, queuing, and packet loss all impact response time; bandwidth reflects only link capacity.

**4. Roughly how large is the BDP for 1 Gbit/s at 80 ms RTT?**

80 Mbit, or roughly 10 MB of data in flight. TCP window sizes, parallelism, and packet loss dictate actual achieved throughput.

**5. Can VPC Flow Logs reconstruct an exact egress invoice?**

No. Flow Logs are sampled and aggregated and do not cover every product/SKU. Use Billing exports for financial accounting and Flow Logs to pinpoint cost-driving flows.

**6. How does CDC reduce egress?**

It transmits only new changes instead of re-sending entire datasets. You must still manage lag, schemas, ordering, deduplication, and reconciliation.

**7. Is Cross-Cloud Interconnect always cheaper than the internet?**

No. Include ports/attachments, peer-provider fees, data transfer, redundant links, monitoring, and cross-region transit where applicable.

**8. In the 1.5 TiB/day example, how much does 70% filtering save illustratively?**

Over 30 days at a simulated 0.08 USD/GiB, the estimate drops from 3,686.40 USD to 1,105.92 USD—a difference of 2,580.48 USD/month, excluding compute/connection fees and actual tiered pricing.

## 25. References

- [Google Cloud: VPC network pricing](https://cloud.google.com/vpc/pricing)
- [Google Cloud: Cloud Storage pricing](https://cloud.google.com/storage/pricing)
- [Google Cloud: Cloud Run pricing](https://cloud.google.com/run/pricing)
- [Google Cloud: Cloud NAT pricing](https://cloud.google.com/nat/pricing)
- [Google Cloud: Cloud Interconnect pricing](https://cloud.google.com/network-connectivity/interconnect/pricing)
- [Google Cloud: Cloud Interconnect overview](https://cloud.google.com/network-connectivity/docs/interconnect/concepts/overview)
- [Google Cloud: Cross-Cloud Interconnect overview](https://cloud.google.com/network-connectivity/docs/interconnect/concepts/cci-overview)
- [Google Cloud: Cloud VPN overview](https://cloud.google.com/network-connectivity/docs/vpn/concepts/overview)
- [Google Cloud: VPC Flow Logs](https://cloud.google.com/vpc/docs/flow-logs)
- [Google Cloud: Cloud Billing Reports](https://cloud.google.com/billing/docs/how-to/reports)
- [Google Cloud: Export Cloud Billing data to BigQuery](https://cloud.google.com/billing/docs/how-to/export-data-bigquery)
- [Google Cloud: Set up Billing export](https://cloud.google.com/billing/docs/how-to/export-data-bigquery-setup)
- [Google Cloud: Networking products](https://cloud.google.com/products/networking)
