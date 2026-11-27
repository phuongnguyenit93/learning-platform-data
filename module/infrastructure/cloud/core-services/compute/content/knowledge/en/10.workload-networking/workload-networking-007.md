# Network Throughput, Connection Limits, and Performance by Machine Size

## 1. Why Does Network Performance Depend on Compute Configuration?

An application may have spare CPU and memory yet still respond slowly because its virtual machine cannot send or receive data fast enough. An API can achieve low throughput when numerous small requests drive up the packet rate; a worker can underutilize CPU while waiting on network data; a server can reject new connections even before bandwidth is saturated because it exhausts file descriptors, ephemeral source ports, or connection tracking tables.

In the cloud, network performance depends on instance family and size, vCPU count, virtual NIC type, packet-processing capacity, network queues, resource-sharing policies, and limits of intermediate services. Two instances with the same vCPU count from different machine families can differ in bandwidth, packets per second (PPS), network queue count, or flow limits. Even within the same family, larger sizes may increase bandwidth in steps, fixed tiers, or via baseline/burst mechanisms depending on the provider.

To select compute accurately, you must distinguish **bandwidth**, **throughput**, **goodput**, **latency**, **PPS**, and **connection capacity**. These metrics describe different bottlenecks. Increasing nominal bandwidth does not solve connection-tracking exhaustion; opening more connections does not let a single TCP flow exceed a link's throughput limit; adding vCPUs does not automatically boost performance if the NIC or target service is already saturated.

After this lesson, learners will be able to:

- Distinguish throughput, bandwidth, goodput, latency, and packet rate.
- Identify connection limits across the OS, NIC, NAT, load balancers, and destination services.
- Explain how instance size and family affect bandwidth, PPS, and connection capacity.
- Estimate required bandwidth and concurrent connections from workload characteristics.
- Measure network performance, locate bottlenecks, and tune both applications and compute configurations.
- Choose network configurations meeting performance, availability, security, and cost requirements.

## 2. Metrics to Distinguish

### 2.1. Bandwidth — Nominal Capacity

Bandwidth is the maximum advertised or configured data transmission rate of a link or network resource. Units are typically bits per second: Mbps, Gbps. For example, a 10 Gbps link has a theoretical ceiling of 10 billion bits per second before protocol overhead.

Bandwidth does not equal the speed an application actually receives. An instance with a nominal 10 Gbps NIC can still achieve less due to limits at the host, virtual switch, routes, NAT, load balancer, peer, storage service, or Internet gateway. Bandwidth may also be shared across multiple flows, NICs, or workloads according to platform policy.

### 2.2. Throughput — Data Rate Actually Transferred

Throughput is the actual rate of data passing a measurement point over a given interval. It can be measured in inbound (ingress) and outbound (egress) directions, per NIC, per instance, per flow, or across the whole application.

When comparing throughput, specify the measurement point and direction. Throughput measured at the sender can differ from throughput measured at the receiver when retransmissions, packet loss, or misaligned measurement windows occur. Aggregate throughput across many flows also says nothing about single-flow performance.

### 2.3. Goodput — Useful Application Data Rate

Goodput is the useful application payload received per second after subtracting overhead such as Ethernet/IP/TCP/UDP headers, TLS framing, retransmissions, and application protocol framing. A link showing high throughput with heavy retransmissions or protocol overhead can yield low goodput.

For instance, sending many tiny packets raises the ratio of header bytes to useful data. Retransmitting dropped packets also consumes bandwidth without increasing useful application data delivered. When evaluating a service, monitor both network-layer throughput and application-layer work completion rate.

### 2.4. Latency — Network Delay

Latency is the time for data or a request to travel from sender to receiver, or the time a network operation takes to complete as defined by the measurement. Latency is typically expressed in milliseconds (ms), or occasionally microseconds (µs) in high-performance internal networks.

Distinguish RTT (round-trip time) from one-way latency. RTT measures sending and receiving a reply; one-way latency measures a single direction and requires clock synchronization between both ends if measured via timestamps. Request/response applications are directly impacted by RTT and the number of round trips.

Do not monitor average latency alone. p95, p99, and p99.9 reveal slow tail requests. A system with low average RTT but high p99 can suffer timeouts, retries, and surging concurrent connections during peak hours.

### 2.5. Packet Rate — Packets per Second

PPS (Packets Per Second) indicates how many packets are processed per second. Two workloads with identical throughput but different packet sizes can produce vastly different PPS. Small packets trigger more header processing, interrupts, lookups, and policy checks per unit of data.

Consequently, workloads with many small messages, short RPCs, DNS queries, or telemetry packets can become bottlenecked by PPS or network-processing CPU long before reaching maximum bandwidth. When choosing instances, examine both bandwidth and packet-rate capabilities when published by the provider.

### 2.6. Connection Capacity — Ability to Sustain Connections

Connection capacity is the ability to open and sustain concurrent connections. It is not a single number. Connections can be constrained by file descriptors, socket memory, ephemeral ports, TCP backlogs, connection tracking, NAT/SNAT, load balancers, firewalls, or destination service limits.

You must distinguish:

- **Concurrent connections:** number of connections open at the same point in time.
- **Connection establishment rate:** number of new connections created per second.
- **Request rate:** number of application requests processed per second.
- **Active flows:** number of network flows currently tracked by an appliance or service.

One application can serve tens of thousands of requests per second over a pool of a few hundred keep-alive connections. Another application opens a new connection per request and rapidly exhausts connection rate or source port limits. Never infer connection counts from requests/s without knowing connection lifetimes and reuse patterns.

## 3. Traffic Path in the Cloud

### 3.1. From Process to Virtual NIC

Application traffic typically passes through the socket API, TCP or UDP stack, routing table, firewall, and virtual network interface. On the cloud host, the virtual NIC maps down to the provider's network fabric. Some platforms use enhanced networking, SR-IOV, or accelerated I/O paths to reduce virtual switch and host CPU overhead.

```text
Application
   |
   v
Socket / TCP / UDP
   |
   v
Kernel networking + firewall + routing
   |
   v
Virtual NIC / network queues
   |
   v
Virtual switch / cloud fabric
   |
   +---- Load balancer / NAT / gateway
   |
   v
Peer NIC and network stack
   |
   v
Target application
```

Each layer can enforce limits or add latency. A valid route does not guarantee high throughput if NIC queues are congested. A high-bandwidth NIC does not ensure an application receives more requests if its worker pool, TLS handshakes, or downstream database are already saturated.

### 3.2. Ingress and Egress

Ingress is traffic entering a resource; egress is traffic leaving it. Some platforms enforce limits per direction, on the bidirectional sum, or by path type. Verify how your provider accounts for traffic on the specific instance type.

Egress to the Internet may traverse a NAT gateway, firewall, proxy, or Internet gateway. Paths to internal services may traverse private endpoints, load balancers, or peered networks. Different paths can carry different bandwidth limits, flow limits, costs, and security policies.

### 3.3. End-to-End Limits

The throughput of a request is bounded by the slowest component along its path. A high-level screening model is:

\[
Throughput_{effective} \leq \min(B_1, B_2, \ldots, B_n)
\]

Where each \(B_i\) is the effective limit of a layer: instance NIC, host, route, NAT, load balancer, network fabric, peer, or target service. This formula is a screening model; actual limits also depend on flow count, packet size, congestion, and how components share resources.

For example, an instance may be capable of sending 10 Gbps while a NAT gateway only has 4 Gbps of usable capacity for the workload at that moment. Application egress throughput will be capped at the NAT or another component on the path, whichever is lower.

## 4. How Instance Size Affects Network Performance

### 4.1. Bandwidth by Machine Family and Size

Cloud providers typically publish network performance tiers by machine family and instance size. Smaller instances may receive lower bandwidth; larger instances generally receive higher network capacity, though increases may occur in steps or with conditions. Do not assume doubling vCPUs doubles network bandwidth.

When reading spec sheets, check:

- Maximum bandwidth and baseline bandwidth.
- Whether performance bursts and conditions for burst usage.
- Limits on ingress, egress, or bidirectional total.
- Maximum PPS or packet-size guidance.
- NIC count, queue count, and multi-queue support.
- Supported flow or connection limits if published by the provider.
- Enhanced networking, SR-IOV, or accelerated networking support.
- Specific limits by region, host, placement group, or instance type.

Labels such as `up to`, `maximum`, `baseline`, or `network optimized` carry different meanings across providers. Check documentation for the exact instance type and validate with measurements in the target deployment region.

### 4.2. vCPU and Packet Processing

CPUs handle the network stack, interrupts, encryption, checksums, packet filtering, connection tracking, and application logic. When PPS is high or many short-lived connections occur, CPU can become the bottleneck before the NIC reaches its bandwidth limit.

An instance with few vCPUs and a high-speed NIC may fail to keep up with the packet rate of a small-packet workload. Conversely, an instance with many vCPUs and a low-capped NIC still cannot reach desired throughput. Selecting compute therefore requires matching CPU capacity and network capacity to the traffic pattern.

### 4.3. Network Queues, RSS, and Multi-Queue

A NIC can use multiple receive/transmit queues to spread packets across multiple CPU cores. Receive Side Scaling (RSS) typically hashes flows to steer packets to appropriate queues. Multi-queue increases parallel processing capacity, though effectiveness depends on queue count, CPU affinity, drivers, and how the application generates flows.

If there is only one large TCP flow, hashing can pin that entire flow to a single queue/CPU; aggregate multi-queue capacity cannot necessarily be exploited by one flow alone. Multiple independent flows distribute much better. Inspect queue configuration and per-core CPU usage when throughput is low despite low overall CPU utilization.

### 4.4. Enhanced Networking and Accelerated I/O Paths

Some platforms provide accelerated virtual NICs or near-SR-IOV mechanisms to cut virtual switch overhead and raise throughput/PPS. These features may require specific instance types, drivers, machine images, kernels, or configurations.

Do not assume every instance supports the same acceleration path. Across VMs, containers, or bare metal, verify how NICs are exposed, driver compatibility, and hypervisor limits. In container environments, NIC/queue access and CNI configuration also affect performance.

### 4.5. Burst vs. Baseline Network Performance

Some instances have a baseline network rate and can burst higher for limited durations or while credits remain. Short benchmarks can show impressive numbers while sustained loads drop back to baseline. Other platforms publish a single maximum or dedicated bandwidth guarantee.

For long-running workloads, benchmark long enough to observe post-burst behavior. Monitor credit or network allowance metrics if exposed by the service. Never design SLOs around peak rates achievable only during short bursts.

## 5. Understanding Connection Limits Layer by Layer

### 5.1. OS Socket and File Descriptor Limits

On Linux, each open socket typically consumes one file descriptor in the process. If a process hits `ulimit -n` or system-wide limits, opening new sockets fails even when ample network bandwidth remains.

Limits to inspect:

- Per-process and system-wide file descriptor limits.
- Open socket counts and TCP state distribution.
- Kernel memory allocated to socket send/receive buffers.
- TCP listen backlog and SYN/accept queue limits.
- Application worker threads and connection pool limits.

Raising file descriptor limits may be necessary for high-concurrency servers, but it does not replace managing socket lifecycles and memory budgets. Every connection consumes resources on both client and server.

### 5.2. Ephemeral Ports and Outbound Connections

When a host opens an outbound TCP connection, the OS typically chooses an ephemeral source port. A connection is identified by a tuple of source IP, source port, destination IP, destination port, and protocol. For a given source IP and destination endpoint, the pool of available source ports can cap concurrent connections to that endpoint.

This frequently affects clients opening large numbers of outbound connections to the same database, API, or proxy. Expanding the ephemeral port range can help in some cases, though tuples, NAT, conntrack, and destination resources still constrain scaling. Do not treat the 16-bit port range as a single global system connection cap; multiple source IPs or distinct endpoints change the number of usable tuples.

Connections in `TIME_WAIT` also hold tuples for a period after closing. Continuously opening new connections instead of reusing a connection pool increases pressure on source ports, CPU, TLS handshakes, and destination services.

### 5.3. TCP Backlog and Connection Establishment

A TCP server maintains queues for connections mid-handshake and completed handshakes awaiting application `accept()`. If the application accepts slowly, the backlog fills and clients encounter timeouts or resets. This limit is distinct from the number of active connections already being served by the application.

When diagnosing, check listen backlog, accept rate, worker counts, CPU, and TCP states. Raising backlog alone will not fix the problem if the application cannot keep up or a downstream service is overloaded.

### 5.4. Connection Tracking and Firewalls

Stateful firewalls, NAT, and certain network layers track flow state in a connection tracking table. Each flow consumes an entry. When the table fills or reaches quota, new connections can be dropped even with spare bandwidth.

Limits can exist in:

- Conntrack tables in the host OS or node.
- Stateful firewalls or security appliances.
- NAT gateways and allocated source ports.
- Cloud load balancers or proxies by connection/flow count.
- Instance or NIC flow-tracking limits.

Raising conntrack maximums must be paired with checking RAM, timeouts, and actual flow rates. Overly long timeouts retain stale entries needlessly; overly short timeouts can disrupt valid idle connections or UDP flows. Tune according to protocol and platform guidance.

### 5.5. NAT and SNAT Port Limits

When multiple outbound workloads share a single NAT IP address, the NAT device must allocate source ports for connections. If new connections to the same endpoint surge, SNAT ports can exhaust or hit allocation limits. Symptoms include sporadic connection failures, timeouts, or errors appearing only during scale-out.

Mitigations include connection reuse, connection pooling, allocating additional NAT IPs/capacity if supported, using private endpoints for internal services, or reducing concurrent outbound connections. Check official NAT service limits and how the provider allocates ports per destination.

### 5.6. Load Balancers and Destination Services

Load balancers can limit concurrent connections, connection setup rates, backends, listeners, targets, or throughput. Some maintain client connections separately from backend connections; others act as proxies or use connection multiplexing. Different architectures alter connection capacity calculations.

Destination services have their own limits: database connection limits, worker pools, thread pools, API quotas, or session limits. Scaling out client instances can push total connections past database capacity. Calculate both per-instance connections and total connections after autoscaling.

## 6. Estimating Bandwidth and Connection Counts

### 6.1. Converting Bandwidth to Data Rate

For bits/s units, theoretical bytes/s is computed by dividing by 8:

\[
10\text{ Gbit/s} \div 8 = 1.25\text{ GB/s}
\]

This is a theoretical ceiling before Ethernet/IP/TCP overhead, TLS, retransmissions, and other layer limits. Application goodput will be lower. Also distinguish decimal GB from binary GiB when comparing dashboards.

### 6.2. Bandwidth-Delay Product

The Bandwidth-Delay Product (BDP) estimates how much data can be "in flight" during one RTT:

\[
BDP = Bandwidth \times RTT
\]

With bandwidth in bits/s and RTT in seconds, divide by 8 to convert to bytes. For example, a 10 Gbit/s path with a 10 ms RTT has a BDP of:

\[
10^{10} \times 0.01 \div 8 = 12.5\text{ MB}
\]

For a single TCP flow to saturate bandwidth under ideal conditions, the outstanding data window must be large enough relative to BDP, and congestion windows, receive windows, and OS settings must allow it. A TCP flow with a window much smaller than BDP may fall far short of link throughput.

### 6.3. Estimating Concurrent Connections

For a steady-state request/response workload, Little's Law gives an approximation:

\[
Concurrent\ requests \approx Request\ rate \times Average\ response\ time
\]

For example, an API handling 2,000 requests/s with an average response time of 150 ms has roughly:

\[
2{,}000 \times 0.15 = 300
\]

concurrently active requests in steady state. This represents average in-flight requests, not necessarily TCP connections. One keep-alive connection can serve multiple sequential requests; HTTP/2 multiplexes multiple streams over one connection; HTTP/1.1 pipelining and proxies behave differently.

To size connection pools, know connection lifetimes, requests per connection, per-connection concurrency, idle ratio, and client instance counts. Add headroom for bursts and failures, without sizing pools so large that databases or downstream services become overloaded.

### 6.4. Estimating Packet Rate

PPS depends on throughput and on-the-wire packet size. For the same throughput, smaller packets produce higher PPS. Ethernet/IP/TCP overhead and framing complicate exact calculations; use approximations for initial screening, then measure with tools and platform metrics.

If a workload involves many small RPCs, DNS, or telemetry, check per-core CPU, NIC queues, and packet drops rather than looking only at Gbps. Increasing payload size or batching can lower PPS, weighed against latency and interactivity requirements.

## 7. Choosing Instance Sizes by Network Load Pattern

### 7.1. High-Throughput Workloads

Examples: streaming, large file transfers, backups, replication, or APIs returning large payloads. Prioritize instances with high network bandwidth, capable NICs, and sustained throughput guarantees. Check ingress/egress caps, NIC counts, placement, and peer limits.

For a single large TCP flow, inspect RTT, BDP, TCP windows, and whether one flow can span queues. For multiple flows, check aggregate throughput and fairness. Ensure storage or data-processing CPU does not become the next bottleneck after upgrading the network.

### 7.2. High-PPS Workloads

Examples: proxies, firewalls, service meshes, DNS, small-request APIs, or telemetry. Prioritize instances with high PPS capability, sufficient vCPUs, and accelerated network stacks. Inspect `softirq`, interrupt distribution, RSS, queue counts, packet drops, and per-core CPU.

A high-PPS workload can require more cores than a bulk-transfer workload at the same bandwidth. Optimize batching, eliminate unnecessary packets, use connection reuse, and avoid CPU-heavy header inspection when unneeded.

### 7.3. High-Concurrency Workloads

Examples: reverse proxies, WebSockets, application gateways, API servers, or services holding many long-lived client connections. Prioritize instances with ample memory for socket buffers, file descriptors, CPU for TLS, and connection tracking. Check load balancer, NAT, and backend limits.

With long-lived connections, concurrent connection counts can be high even at low request rates. Monitor sockets by state, socket memory, connection churn, and idle connections. Use keep-alive, pooling, and sensible timeouts to avoid constant connection teardown and setup.

### 7.4. Latency-Sensitive Workloads

Examples: trading, gaming, internal RPCs, or interactive applications. Prioritize low RTT, stable paths, tight placement, minimal hops, and instances with consistent network performance. Measure p95/p99 across zones and between components.

The largest instance does not always yield the lowest latency. Check data locality, network paths, congestion, CPU scheduling, and load balancer queuing. Placing compute close to dependencies usually lowers RTT, while still respecting data residency and HA requirements.

### 7.5. Quick Selection Matrix

| Load pattern | Priority metrics | Instance traits to inspect | Application optimizations |
|---|---|---|---|
| Large data transfers | Throughput, retransmissions, RTT | NIC bandwidth, baseline/burst, placement | TCP windows, batching, parallel streams where suitable |
| Many small packets | PPS, per-core CPU, packet drops | PPS capability, vCPU, RSS/multi-queue | Reduce packet overhead, batching, tune workers |
| Many long-lived connections | Concurrent connections, memory, FDs | RAM, socket capacity, conntrack and flow limits | Keep-alive, pools, timeouts, connection caps |
| Many short-lived connections | Connection rate, TIME_WAIT, SNAT | CPU, ephemeral ports, NAT/LB limits | Connection reuse, HTTP keep-alive, reduce handshakes |
| Latency-sensitive RPCs | RTT p95/p99, jitter, loss | Network path, placement, stable baseline | Fewer round trips, sensible timeouts and retries |
| Heavy egress | Egress throughput, NAT capacity, cost | NIC, NAT/gateway path, quotas | Private endpoints, caching, compression, data locality |

## 8. Application-Layer Connection Optimization

### 8.1. Connection Pooling and Keep-Alive

Connection pooling reuses open connections instead of establishing a new one per request. This reduces TCP handshakes, TLS handshakes, CPU, and pressure on ephemeral ports/NAT. Pools need size caps, idle timeouts, maximum lifetimes, and broken-connection validation.

A pool that is too small forces requests to wait for connections; a pool that is too large can exhaust backend connections or memory. System-wide pool size equals per-instance pool size multiplied by instance count. When autoscaling adds instances, recalculate total connections hitting databases or target APIs.

Keep-alive preserves connections for reuse. Timeout settings across clients, load balancers, proxies, and servers must align. If one layer closes a connection earlier than another, applications encounter errors on connections they believed were still valid.

### 8.2. HTTP/2, Multiplexing, and HTTP/3

HTTP/2 lets multiple streams share one TCP connection, reducing connection counts and handshake overhead for certain workloads. However, streams still share a single TCP connection; packet loss can stall multiple streams due to TCP delivery semantics.

HTTP/3 runs over QUIC/UDP with independent streams, mitigating TCP stream-level head-of-line blocking. Yet performance depends on clients/servers, load balancers, firewalls, NATs, and UDP path support. Do not switch protocols assuming HTTP/3 is always faster; benchmark across real networks and clients.

### 8.3. Timeouts, Retries, and Backoff

Timeouts must be set across connect, request, and downstream calls. Overly long timeouts tie up connections and workers; overly short timeouts trigger false failures under normal jitter.

Retries should apply only to safe-to-retry operations or requests with idempotency keys. Immediate synchronized retries without backoff cause retry storms, spiking connection rates and pushing target services into overload. Use exponential backoff, jitter, retry budgets, and circuit breakers where appropriate.

### 8.4. Reducing Round Trips and Payloads

Batching small operations into one request, caching data, compressing payloads when beneficial, and avoiding sequential API chains reduce cumulative RTT. However, oversized payloads raise memory pressure and end-to-end latency. Measure serialization, compression, transfer, decompression, and processing together.

### 8.5. TLS and Encryption

TLS protects data in transit while consuming CPU and adding handshake overhead. Connection reuse, session resumption, and tuned TLS libraries reduce overhead. Never disable TLS to chase production benchmark numbers; instead, measure CPU and handshake rates and configure ciphers/protocols per security policy.

## 9. Observability and Diagnostics

### 9.1. Cloud-Level Metrics

Monitor at minimum:

- Ingress and egress bytes/s and packets/s per instance/NIC.
- Network bandwidth allowance, baseline/burst, or credits if exposed.
- Packet drops, errors, retransmissions, and connection resets.
- Flow/connection counts and NAT, load balancer, and firewall metrics.
- Inter-zone and client-to-backend latency at p50/p95/p99.
- Per-core CPU utilization, `softirq`, memory, and network queues.
- Quotas, throttling, and destination service limits.

Metric names vary by provider. Some metrics are sampled per minute and can miss short bursts. Combine cloud metrics with OS and application telemetry.

### 9.2. Linux Tools

Useful commands:

```bash
# View interface addresses, state, and error counters
ip -s link

# View TCP/UDP sockets and connection states
ss -s
ss -tan state established
ss -tan state time-wait

# View shell/process file descriptor limits
ulimit -n
cat /proc/sys/fs/file-nr

# View TCP/IP statistics and retransmissions
nstat -az

# View interface rates over time (if sysstat is installed)
sar -n DEV,TCP,ETCP 1
```

Depending on privileges and OS, you can also use `ethtool -S <interface>` for NIC counters, `ethtool -l <interface>` for channels/queues, and `conntrack -S` for connection-tracking statistics if installed. Some drivers or cloud NICs do not expose all counters.

Never draw conclusions from a single isolated metric. For example, rising retransmissions can stem from packet loss, congestion, slow receivers, or link errors; high `TIME_WAIT` counts reflect connection churn without automatically proving ephemeral ports are exhausted.

### 9.3. Testing Bandwidth with iperf3

`iperf3` measures throughput between two endpoints. Run the server on the target machine:

```bash
iperf3 -s
```

Run the client on the source machine:

```bash
iperf3 -c <server-private-ip> -t 60
```

Measure the reverse direction with reverse mode:

```bash
iperf3 -c <server-private-ip> -t 60 -R
```

You can test parallel streams with `-P`, starting from one stream and scaling up to understand per-flow vs. aggregate limits. Never run bandwidth benchmarks on production networks without approval; test load can disrupt other services, incur egress fees, or congest shared paths. Ensure firewalls allow the test port only within the necessary scope.

### 9.4. Checking Connections and Ports

When failing to open new connections, check in order:

1. Does the application still have file descriptors and worker capacity?
2. Is the listen socket bound to the right address/port, and is its backlog full?
3. Are ephemeral ports or outbound tuples exhausted?
4. Have conntrack, firewalls, or NAT hit limits?
5. Do load balancers have remaining connection/flow capacity and healthy backends?
6. Has the destination service reached connection, quota, or thread-pool limits?
7. Are there packet drops, retransmissions, DNS delays, or abnormal routes?

## 10. Workflow for Choosing and Optimizing Network Configuration

### Step 1: Characterize the Workload

Document requests/s, average and maximum payload sizes, ingress/egress ratio, concurrent connections, connection rate, connection lifetime, protocols, target RTT, and deployment zones. Separate steady-state, peak, and burst loads.

### Step 2: Map the Path

Diagram paths across clients, instances, load balancers, NATs, service endpoints, databases, and the Internet. Note which layers carry quotas or limits on bandwidth, PPS, connections, or cost. Identify whether traffic stays intra-zone, crosses zones, crosses regions, or exits to the Internet.

### Step 3: Check Instance Limits

Match machine families and sizes against bandwidth, PPS, queues, NICs, and enhanced networking specs. Verify CPU/memory headroom for the network stack, TLS, and application. Confirm baseline/burst behavior and quotas in the target region.

### Step 4: Estimate Capacity

Compute throughput from request rate multiplied by average payload, then add protocol overhead and headroom. Estimate in-flight requests from request rate multiplied by average response time. Derive connection pools, file descriptors, NAT/SNAT capacity, and downstream connection budgets.

### Step 5: Run Controlled Benchmarks

Measure single-flow and multi-flow; ingress and egress; small and large packet sizes; short and sustained runs. Track throughput, goodput, RTT, retransmissions, PPS, CPU, and connection metrics. Test on instance types and placement matching production.

### Step 6: Optimize Application and Infrastructure

Prioritize connection reuse, right-sized pooling, fewer round trips, payload tuning, and worker distribution. Upgrade instance size, NICs, NAT capacity, or source IP counts only when measurements show that layer is the bottleneck.

### Step 7: Test Limits and Failures

Test scale-out, slow backends, NAT/LB capacity, packet loss, and node replacement in staging. Ensure autoscaling cannot exceed database or destination service connection limits. Establish alerts and runbooks before going to production.

## 11. Practical Examples

### Example 1: API with Many Short-Lived Connections

An API handles 5,000 requests/s. Each request calls an internal service, but the client opens a new TCP connection for every request. As load grows, connection errors and CPU spike even though network bandwidth is nowhere near its limit.

**Analysis:** connection establishment rate is very high; each connection requires a TCP handshake, potentially a TLS handshake, holds an ephemeral port while active, and enters `TIME_WAIT` on close. NATs or firewalls must track excessive flows. CPU goes toward handshakes instead of business logic.

**Remediation:** enable keep-alive, use bounded connection pools, evaluate HTTP/2 where appropriate, align timeouts, and re-measure connection rate, `TIME_WAIT`, CPU, retransmissions, and p99 latency. Verify total connections reaching the backend after autoscaling.

### Example 2: Worker Transferring Large Files

A worker reads data from object storage and sends results to a processing node. Throughput reaches only a fraction of the instance's nominal bandwidth.

**Analysis:** run `iperf3` between the two nodes to check the network path; compare single-flow vs. multi-flow; measure RTT, retransmissions, and CPU. Check instance egress limits, NAT/gateways, storage endpoints, and target node bandwidth. Verify whether the application reads/writes with sufficient concurrency and whether storage keeps pace.

**Remediation:** choose an instance with an adequate network baseline, use private endpoints where applicable, increase partitioned read concurrency, tune buffers, and cut round trips. Verify data transfer costs and avoid letting a single stream bottleneck work that can be safely parallelized.

### Example 3: Proxy Sustaining Many WebSockets

A proxy holds hundreds of thousands of long-lived WebSocket connections. Request rate is modest, yet memory and file descriptor usage climb rapidly.

**Analysis:** concurrent connection count differs from request rate. Every socket consumes a file descriptor and kernel/application memory. Track socket states, socket memory, FDs, connection tracking, load balancer timeouts, and per-instance connection counts.

**Remediation:** choose instances with sufficient RAM and vCPUs, raise FD limits with proper controls, use event-driven I/O, configure appropriate idle timeouts, spread connections across instances, and check LB limits. Set capacity targets below hard limits to leave headroom for node failures or rolling deployments.

## 12. Common Mistakes

- **Looking only at Gbps:** ignoring PPS, latency, connection rates, and limits of services along the path.
- **Assuming larger instances always scale network speed linearly with vCPUs:** bandwidth may increase in steps or hit separate caps.
- **Equating requests/s with connection counts:** keep-alive and multiplexing decouple the two metrics.
- **Assuming a 10 Gbps NIC guarantees 10 Gbps at the application:** hosts, routes, NAT, LBs, peers, and protocol overhead all constrain throughput.
- **Growing connection pools without bounds:** can overload databases, NATs, or conntrack tables.
- **Measuring only aggregate CPU:** a single core handling networking/`softirq` can saturate while total CPU appears low.
- **Drawing aggregate capacity conclusions from a single-flow benchmark:** one flow does not represent multi-flow aggregate throughput or PPS.
- **Ignoring baseline vs. burst:** short benchmarks may misrepresent sustained load.
- **Retrying immediately:** retry storms spike connection rates and trigger cascading overload.
- **Disabling timeouts or keeping connections open indefinitely:** stale sockets leak resources and exhaust capacity.
- **Scaling compute without checking downstream limits:** more instances can breach database connection caps.
- **Overlooking egress costs:** cross-zone or Internet traffic can drive substantial charges.

## 13. Checklist Before Finalizing Instance and Network Sizing

- [ ] Measured ingress/egress throughput and goodput under realistic workloads.
- [ ] Measured RTT, p95/p99 latency, packet loss, and retransmissions.
- [ ] Identified typical PPS and packet sizes.
- [ ] Separated request rate, connection rate, and concurrent connections.
- [ ] Verified FDs, socket memory, backlogs, ephemeral ports, and `TIME_WAIT`.
- [ ] Checked conntrack, NAT/SNAT, load balancer, and destination service limits.
- [ ] Matched network bandwidth/PPS against the exact instance family and size.
- [ ] Checked baseline, burst, enhanced networking, NIC queues, and RSS.
- [ ] Calculated required bandwidth, BDP, and connection pools from load estimates.
- [ ] Benchmarked single-flow/multi-flow, bidirectional, and sustained loads.
- [ ] Tuned keep-alive, pooling, timeouts, retries, and payloads.
- [ ] Verified autoscaling impact on total downstream connections.
- [ ] Estimated NAT, egress, cross-zone/cross-region, and gateway costs.
- [ ] Established dashboards, alerts, quotas, and incident runbooks.

## 14. Conclusion

Compute workload network performance is governed by the entire transmission path and processing capacity at each layer. Bandwidth describes nominal capacity; throughput and goodput measure actual data transferred; latency reflects delay; PPS reflects packet-processing demand; and connection capacity depends on limits spanning OS sockets through NAT, load balancers, and destination services.

Instance size shapes bandwidth, packet processing, NIC queues, and connection sustainability, though gains are not necessarily linear with vCPUs. Characterize load patterns accurately, model capacity, check end-to-end limits, and benchmark under representative conditions. Optimizing connection reuse, timeouts, workers, NICs, and instance sizing based on measurements delivers stable performance at predictable cost.
