# MTU, Packet Loss, and Latency in Inter-Workload Communication

Two virtual machines can sit inside the same VPC/VNet with valid routes and security rules yet still communicate slowly, intermittently, or fail on certain payloads. The root cause may be a mismatched MTU, dropped packets, link congestion, elevated latency, or an intermediate device handling packets differently than expected.

When operating cloud workloads, you must understand packet sizes, fragmentation, Path MTU Discovery, the impact of packet loss, and how to measure latency. This knowledge helps diagnose issues such as TCP connections hanging on large payloads, APIs exhibiting high p99 latency, VPNs working for small requests but failing on large files, or low throughput despite high nominal bandwidth.

## 1. What Is MTU?

**MTU (Maximum Transmission Unit)** is the maximum size of a network-layer packet that an interface or link can forward in a single transmission without IP-layer fragmentation. In IP over Ethernet networks, MTU usually refers to the maximum IP packet size, excluding the Ethernet header and frame overhead.

Standard Ethernet typically uses a 1500-byte IP MTU. Some environments support jumbo frames with a larger MTU, such as around 9000 bytes or a nearby value. The exact figure depends on the hardware, cloud platform, instance type, and end-to-end path. Do not assume every NIC, subnet, gateway, VPN, peering link, or intermediate service supports the same MTU.

MTU affects how many packets must be sent to transfer a given amount of data:

- Smaller MTUs require more packets for a stream, increasing header overhead and packet-processing work.
- Larger MTUs can reduce packet counts and link overhead, but only help when the entire path supports that size.
- If a packet exceeds a hop's MTU, it may be fragmented at the IP layer, dropped, or require the sender to shrink packet sizes.

Distinguish MTU from Ethernet frame size. When IP MTU is 1500 bytes, the Ethernet frame adds its own header and trailer. Therefore, when reading NIC specs or capture tools, check whether the number refers to IP packets, Ethernet frames, or application-protocol payloads.

## 2. MTU, MSS, and Payload Size

MTU limits IP packet size. For TCP, both endpoints exchange **MSS (Maximum Segment Size)** to cap the amount of TCP data per segment. MSS excludes the IP header and TCP header.

In the simple case without IP or TCP options:

\[
\text{MSS} = \text{Path MTU} - \text{IP header} - \text{TCP header}
\]

For example, with a 1500-byte IPv4 MTU, a 20-byte IPv4 header, and a base 20-byte TCP header:

\[
1500 - 20 - 20 = 1460\text{ bytes}
\]

With base IPv6, the IP header is 40 bytes, so the same 1500-byte MTU and base 20-byte TCP header yield an MSS of 1440 bytes. TCP options such as timestamps occupy extra header bytes in real packets; TCP adjusts segment data so packets stay within limits.

MSS is negotiated in each direction during the TCP handshake. However, MSS advertisement does not automatically discover every MTU along the path. If an intermediate hop has a lower MTU than both endpoints, Path MTU Discovery or an equivalent adjustment mechanism must still function.

With UDP, the application chooses the datagram size itself. UDP has no MSS negotiation like TCP and does not retransmit lost datagrams automatically. Applications using UDP must consider path MTU, datagram size, and application-layer recovery. Sending oversized datagrams can trigger IP fragmentation or packet drops on some paths.

## 3. IP Fragmentation and Path MTU Discovery

A transmission path can cross many hops: the sender's NIC, virtual network, gateways, security appliances, VPN tunnels, destination network, and receiver's NIC. The smallest MTU along the path determines the **Path MTU (PMTU)**:

\[
\text{PMTU} = \min(\text{MTU of each hop along the path})
\]

If a sender transmits packets larger than the PMTU, packets must be handled according to the IP version rules and relevant flags.

### IPv4

IPv4 can fragment packets at the source or at intermediate routers if a packet exceeds a hop's MTU and the Don't Fragment (DF) flag is unset. Fragments are reassembled at the destination. If any fragment is lost, the entire original datagram cannot be reassembled.

Fragmentation adds overhead and can degrade transfer efficiency. Some firewalls, NATs, or network devices handle fragments differently or drop fragments for security, resource, or configuration reasons. When DF is set, routers may not fragment the packet; instead, the router can send an ICMP message indicating the packet must be reduced.

### IPv6

IPv6 routers do not fragment packets in transit. If a packet is too large for the next link's MTU, the router drops the packet and sends an ICMPv6 Packet Too Big message so the sender adjusts. The source can fragment IPv6 packets using a Fragment header if needed, but fragmentation is performed by the source node.

### Path MTU Discovery

Path MTU Discovery (PMTUD) allows the sender to discover the usable MTU along a path. For IPv4, traditional PMTUD relies on DF-marked packets and ICMP Destination Unreachable (fragmentation needed) messages. For IPv6, PMTUD relies on ICMPv6 Packet Too Big messages.

General flow:

1. The source sends packets sized for its assumed MTU.
2. If a packet is too large at a hop, the device that cannot forward it drops the packet and sends the appropriate ICMP notice.
3. The source receives the notice, shrinks packet size, or updates its PMTU cache.
4. The flow continues with better-sized packets.

If the required ICMP messages are blocked along the path, notices never reach the source. Small packets pass through while large packets silently drop, creating a **PMTU black hole**. With TCP, an application can connect and exchange small messages yet hang when sending large responses. With IPv6, blocking ICMPv6 Packet Too Big breaks PMTUD and severely impairs connectivity.

Do not block all ICMP/ICMPv6 indiscriminately with a blanket rule. Allow required ICMP types per platform guidance and security policy while restricting other message types as needed.

## 4. MTU in Cloud Networks and Tunnels

In the cloud, packets traverse multiple virtual network layers and provider-internal encapsulation. Users rarely see the physical infrastructure directly, yet must still honor the MTU published for NICs and network links.

Key considerations:

- **NICs and instance types:** maximum MTU can vary by instance type, driver, enhanced networking, or network service.
- **VPC/VNet and subnets:** jumbo frame support may depend on platform and traffic type; subnets are not always where MTU is configured.
- **Peering and transit:** paths traversing transit services may carry different limits than direct intra-VPC paths.
- **VPN/IPsec:** encapsulation adds outer IP, UDP, ESP, or other headers, shrinking the inner payload that fits without exceeding the outer MTU.
- **Overlay networks:** VXLAN, Geneve, or other encapsulation protocols add headers, so workload MTUs must leave room for overhead.
- **Internet and partners:** you do not control MTUs of external networks; never assume end-to-end jumbo frames.

For tunnels, the effective inner packet size is typically smaller than the outer link's MTU. Exact overhead depends on IPv4 vs. IPv6, tunnel mode, cryptographic algorithms, NAT-T, and encapsulation options. Do not subtract a single fixed number for every VPN. Use the MTU/MSS recommended by your provider or VPN appliance, then test from both ends of the tunnel.

A practical rule is setting MTU according to the lowest-MTU path the workload traverses. If an application communicates both over an internal jumbo network and over a lower-MTU VPN, you may need appropriate interface or route-specific MTUs, MSS clamping on the gateway, or separate traffic paths to avoid sending one flow across incompatible MTUs.

## 5. What Is Packet Loss and How Does It Impact Workloads?

**Packet loss** occurs when transmitted packets fail to arrive at the destination or fail to be processed at the network layer. Common causes include:

- Congestion filling queues at a NIC, switch, router, or gateway.
- Packet-per-second (PPS), bandwidth, or quota limits on an instance or gateway.
- Physical faults or errors in interfaces, drivers, virtual NICs, or intermediate devices.
- Firewalls, ACLs, routes, or NAT dropping packets.
- Mismatched MTU, lost fragments, or blocked PMTUD ICMP notices.
- Guest or host CPU overload preventing timely packet processing.
- Unstable Wi-Fi, public Internet, or partner links.

Packet loss impacts protocols differently. TCP detects loss via ACKs, duplicate ACKs, or timeouts and retransmits. Retransmissions add latency and trigger congestion control, usually causing TCP to throttle its sending rate to avoid worsening congestion. Consequently, even a small packet-loss rate can slash throughput over high-RTT paths.

UDP does not retransmit automatically. Applications can lose datagrams, experience audio/video stuttering, or miss telemetry samples. If an application requires reliability over UDP, it must implement sequence numbers, timeouts, retransmissions, or error-correction mechanisms itself.

Not every dropped packet indicates a fault. Firewalls intentionally drop unauthorized traffic; ICMP echo may be rate-limited; some counters record policy drops. Correlate packet loss with traffic type, interface counters, flow logs, firewall logs, and metrics at both ends.

## 6. Latency: Latency, RTT, and Jitter

**Latency** is the time it takes data to travel from source to destination. Operationally, teams frequently measure **RTT (Round-Trip Time)**—the time from sending a packet to receiving its reply. RTT covers both outbound and return paths, so it does not necessarily equal twice the one-way latency if routes are asymmetric.

Latency consists of multiple components:

\[
\text{Latency} \approx \text{Propagation} + \text{Serialization} + \text{Queueing} + \text{Processing}
\]

- **Propagation delay:** time for signals to cross physical distance; depends on distance and transmission medium.
- **Serialization delay:** time to clock an entire packet onto the link; larger packets or slower links increase this component.
- **Queueing delay:** time spent waiting in queues during congestion or traffic bursts.
- **Processing delay:** time spent by routers, firewalls, hosts, or applications processing packets.

Low average latency does not guarantee a consistent experience. Inspect p50, p95, and p99 percentiles to expose tail latency. **Jitter** is variation in latency across packets or samples; high jitter especially disrupts voice, video, and real-time protocols.

Application latency also includes server processing, thread-pool waits, databases, caches, and downstream calls. If ping between two machines is low yet the API remains slow, measure DNS, connection setup, TLS handshakes, server processing, and dependent calls separately.

## 7. Relationship Between Bandwidth, RTT, and Throughput

Bandwidth is a link's maximum transmission capacity under given conditions. Throughput is the actual data rate achieved by an application. The two are not equal: throughput can fall below bandwidth due to packet loss, congestion, PPS limits, TCP windows, CPU, encryption, disk I/O, or slow servers.

A useful concept is the **Bandwidth-Delay Product (BDP)**—the amount of data that must be "in flight" to fill a pipe with a given bandwidth and RTT:

\[
\text{BDP (bits)} = \text{Bandwidth (bits/s)} \times \text{RTT (s)}
\]

For example, a 1 Gbit/s path with a 40 ms RTT has a BDP of:

\[
1{,}000{,}000{,}000 \times 0.04 = 40{,}000{,}000\text{ bits}
\]

This equals roughly 5 MB of data in flight. If the TCP receive window or congestion window is much smaller than the BDP, the connection cannot saturate available bandwidth even with zero packet loss.

When throughput is low, do not immediately upgrade instance bandwidth. Pinpoint the bottleneck by measuring RTT, retransmissions, windows, CPU, PPS, NIC throughput, and application performance together. A single TCP stream may also fail to reach the aggregate speed achievable across multiple streams.

## 8. Jumbo Frames: Benefits and Limits

A jumbo frame is an Ethernet frame larger than the standard Ethernet frame size. In many environments, the term refers to an IP MTU around 9000 bytes, though definitions and supported values vary across platforms.

Potential benefits:

- Fewer packets needed to send the same volume of data.
- Lower header overhead and fewer packet-processing events in certain workloads.
- Improved efficiency for bulk data transfers, storage networks, or high-throughput internal flows.

Limits and risks:

- Every hop along the path must support the larger size; a single lower-MTU hop can drop or fragment packets.
- Not all cloud services, Internet gateways, VPNs, load balancers, or endpoints support jumbo frames.
- Larger MTUs do not solve congestion, PPS-limited packet drops, or distance-induced latency.
- Some applications sending large datagrams or overlays require separate MTU tuning.

Enable jumbo frames only when the provider confirms path support and end-to-end testing passes. Never raise MTU on a single NIC expecting every connection to speed up.

## 9. Measuring MTU and Testing PMTU

You can check the interface MTU inside the guest OS, then test the largest packet size that traverses the path. These two checks answer two different questions: what the local MTU is set to, and what the actual PMTU between two endpoints is.

### Linux

View interface addresses and MTUs:

```bash
ip -br link
ip link show dev eth0
```

Test unfragmented IPv4 packets with `ping`:

```bash
ping -4 -M do -s 1472 -c 4 10.20.16.25
```

With a 20-byte IPv4 header and 8-byte ICMP header, a 1472-byte payload produces a 1500-byte IP packet. If the path MTU is smaller and DF is set, the command returns a fragmentation-needed error or times out. Lower the payload size progressively to find the maximum passing size, while verifying ICMP is not blocked and the target responds to echo.

`tracepath` can help discover PMTU along the path:

```bash
tracepath 10.20.16.25
```

Results depend on intermediate devices and permitted ICMP types. Not every router provides enough feedback for `tracepath`.

### Windows

View interface configuration:

```powershell
Get-NetIPInterface | Format-Table InterfaceAlias,AddressFamily,NlMtu
```

Test IPv4 packets with DF set:

```powershell
ping -f -l 1472 10.20.16.25
```

The `-f` flag sets Don't Fragment and `-l` sets the ICMP payload size. Remember to add the 20-byte IPv4 header and 8-byte ICMP header when computing IP packet size.

The commands above are examples; replace interfaces and target addresses with actual endpoints. ICMP echo can be blocked or rate-limited, so a failed ping does not by itself prove application packet loss. When needed, test with TCP connections or dedicated measurement tools.

## 10. Measuring Packet Loss, Latency, and Throughput

Measuring from multiple vantage points helps isolate problems. Run tests from source workload to destination workload, from each machine to its gateway, and to a controlled reference endpoint. Record timestamps, regions/AZs, instance types, interfaces, and traffic direction for comparison.

| Tool | Purpose | Known limitations |
|---|---|---|
| `ping` | RTT and echo-reply loss rate | ICMP may be blocked or prioritized lower than application traffic |
| `traceroute` / `tracert` | Inspect hops and per-hop response times | Some hops do not reply; routes can be asymmetric |
| `mtr` / `pathping` | Track per-hop loss and latency over many samples | Loss at an intermediate hop without destination loss often indicates ICMP rate limiting |
| `tracepath` | Inspect path and PMTU on Linux | Relies on ICMP support along the path |
| `iperf3` | Measure TCP/UDP throughput between two controlled endpoints | Requires choosing stream count, direction, duration, and avoiding production impact |
| `ss` / `netstat` | Inspect sockets, retransmissions, or connection states | Does not replace end-to-end tests |
| Cloud metrics / flow logs | Observe throughput, drops, errors, and traffic by interface or flow | Metric names and granularity vary by provider |

Example throughput test with `iperf3` in a test environment:

```bash
# On the target machine
iperf3 -s

# On the source machine, test TCP for 30 seconds
iperf3 -c 10.20.16.25 -t 30

# Try multiple TCP streams to compare
iperf3 -c 10.20.16.25 -t 30 -P 4
```

Run the `iperf3` server only on an authorized port in a test network or controlled maintenance window. Multiple streams can generate heavy load and may not represent a single real application connection. When testing UDP, set an appropriate bitrate and monitor jitter/loss; do not transmit faster than the link can carry.

## 11. Diagnosing Common Symptoms

### Connection Succeeds but Large Transfers Hang

The first suspect to check is a PMTU black hole or mismatched MSS. Small packets and TCP handshakes pass through while large data packets drop. Check interface MTUs, test DF with decreasing sizes, verify ICMP fragmentation-needed or Packet Too Big messages can return to the sender, and inspect tunnel overhead. If traffic crosses a VPN, compare MTU/MSS against appliance or provider recommendations.

### Ping Shows Loss Without Matching Application Errors

Some devices deprioritize or rate-limit ICMP echo while forwarding TCP/UDP normally. Compare ping against application-layer packet loss, TCP retransmissions, flow logs, and measurements to the final endpoint. If loss appears only at an intermediate hop while the final hop shows zero loss, router ICMP rate limiting is likely responsible.

### RTT Spikes During Peak Hours

Check queueing delay, throughput, PPS, CPU, NIC drops, and gateway limits. If RTT climbs alongside high link utilization, congestion is likely. If RTT climbs while bandwidth remains low, inspect host CPU, firewall inspection, route changes, or slow downstream services.

### Low TCP Throughput on High-RTT Links

Check packet retransmissions, congestion windows, receive windows, and socket buffers. Use BDP to estimate required in-flight data. Test single-stream vs. multi-stream separately in a controlled environment. If multiple streams reach high aggregate throughput while one stream stays slow, inspect TCP windows, congestion control, and application behavior.

### UDP Data Loss or High Jitter

Inspect send bitrate, PPS, queue drops, and receiver packet-processing capacity. Verify the application implements sequence numbers, jitter buffers, or appropriate recovery mechanisms. Because UDP never retransmits on its own, raising MTU or bandwidth alone will not eliminate all causes of datagram loss.

## 12. Optimizing MTU and Networking for Workloads

No single MTU value is optimal for every workload. Choose based on the actual path, traffic pattern, and compatibility requirements.

| Workload | What to prioritize |
|---|---|
| Public Internet web API | Broadly compatible MTU, working PMTUD, low TCP retransmissions, stable p95/p99 |
| Internal communication between VMs in same cloud network | Confirm end-to-end jumbo support before raising MTU; monitor PPS and throughput |
| Database replication or backups | Consistent throughput, low loss, appropriate RTT, and uniform MTU across all nodes |
| Site-to-site VPN | Account for tunnel overhead, choose proper MTU/MSS, and allow required ICMP |
| Voice/video or real-time UDP | Jitter, packet loss, queueing delay, and suitable datagram sizes |
| Overlay/container networks | Account for VXLAN/Geneve encapsulation overhead and lower workload MTU accordingly |

Optimization steps can follow this sequence:

1. Identify endpoints, protocols, traffic direction, and every hop traffic traverses.
2. Measure current NIC MTUs and end-to-end PMTU.
3. Verify required ICMP, firewalls, VPN, and overlay overhead.
4. Measure baseline RTT, loss, retransmissions, throughput, PPS, and interface drops.
5. Test MTU/MSS or route changes in staging first.
6. Test small packets, large packets, TCP, and UDP if used by the workload.
7. Roll out in staged groups, monitor metrics, and keep a rollback plan ready.

Avoid changing MTU across production simultaneously before verifying every path. Changing MTU on one side without updating the peer or intermediate appliances can break connectivity. In multi-route environments, test each path rather than a single host pair.

## 13. Example: Internal API Over VPN Hanging on Large Responses

An API on a private VM accepts small requests from on-premises over a site-to-site VPN. Health checks and TCP handshakes succeed. However, when the API returns a large file or JSON payload, the client stalls and times out.

Diagnostic workflow:

1. Confirm the failure correlates with response size: small responses work, large responses fail.
2. Measure RTT and packet loss to the endpoint; check retransmissions on both client and server.
3. Inspect NIC MTUs on both sides and the VPN tunnel configuration.
4. Test DF-marked IPv4 packets with shrinking payloads to estimate PMTU; verify whether ICMP fragmentation-needed messages return to the sender.
5. Check whether tunnel overhead, NAT-T, or firewalls are dropping fragments or required ICMP notices.
6. Adjust tunnel MTU or TCP MSS per appliance guidance, then retest with large payloads.
7. Monitor errors and latency after the change in both directions.

In this case, raising the API timeout only makes clients wait longer. Fix the reason large packets fail to cross the path. If retransmissions persist after tuning MTU/MSS, continue checking congestion, asymmetric routing, and gateway packet drops.

## 14. Common Mistakes

- **Raising MTU without end-to-end verification:** large packets drop at an intermediate hop. Measure PMTU across each critical path.
- **Blocking all ICMP:** PMTUD never receives size-reduction notices. Allow required ICMP/ICMPv6 per policy.
- **Confusing MTU with MSS:** MTU bounds IP packets, whereas MSS bounds TCP payloads. Account for headers accurately during diagnostics.
- **Treating ping as a complete test:** ICMP may be rate-limited or handled differently from TCP/UDP. Correlate with application traffic.
- **Blaming bandwidth when throughput is low:** packet loss, RTT, PPS, CPU, or TCP windows may be the true bottleneck.
- **Using jumbo frames over VPN or the Internet:** tunnels and external paths rarely support them. Size according to actual PMTU.
- **Measuring only one direction:** asymmetric routing gives different bidirectional latency and loss. Test from source, destination, and return paths.
- **Running high-load iperf on production:** the test itself can induce congestion. Use controlled environments and maintenance windows.

## 15. Operations Checklist

- [ ] Known NIC MTUs and supported MTUs along critical paths.
- [ ] Distinguished IP MTU, Ethernet frame size, and TCP MSS.
- [ ] PMTUD works; required ICMP fragmentation-needed or ICMPv6 Packet Too Big messages are not blocked.
- [ ] VPN tunnels and overlays account for encapsulation overhead.
- [ ] Jumbo frames enabled only where full end-to-end path support is confirmed.
- [ ] Measured RTT, p95/p99 latency, jitter, and packet loss from real endpoints.
- [ ] Monitored TCP retransmissions, NIC drops/errors, PPS, and throughput.
- [ ] Distinguished ICMP rate limiting from application-traffic packet loss.
- [ ] Throughput tests are load-bounded and do not impact production workloads.
- [ ] MTU/MSS changes are staged, rolled out in groups, and backed by a rollback plan.

MTU, packet loss, and latency directly govern the reliability of inter-workload communication. By understanding PMTU and MSS, keeping PMTUD working, measuring loss/RTT/throughput at both ends, and checking NIC, gateway, and tunnel limits, operations teams can isolate network faults accurately and optimize performance with evidence.
