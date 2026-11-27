# Intermittent Connectivity: Routes, DNS, Firewalls, and Connection Port Limits

A cloud workload can operate normally for several minutes and then suddenly time out, succeed intermittently, or fail only under rising load. This phenomenon is often harder to diagnose than a complete outage because many layers still work: the host is up, the application is listening, yet some requests never reach the target or responses fail to return along the right path.

Common causes span multiple layers: routing inside the OS or cloud network, inconsistent DNS resolution, firewall/security policies, NAT and connection tracking, ephemeral source port ranges, listen backlogs, file descriptors, or application connection limits. Identical symptoms such as timeouts can stem from very different root causes. Therefore, isolate by timestamp, source, destination, protocol, and each hop along the connection.

This lesson belongs to the **Compute Troubleshooting** chapter of the **CLOUD_CORE_SERVICES_COMPUTE** module. The module helps learners explore cloud compute models—from virtual machines and containers to serverless; how to choose CPU, memory, networking, and security settings; and how to deploy applications, scale under load, ensure availability, and optimize operational cost. Within that scope, diagnosing intermittent connectivity helps separate compute, network, and application faults and identify the exact limit requiring adjustment.

## 1. Understand the path of a connection

### 1.1. Stages of a TCP connection

For a typical TCP connection, the client must resolve the target hostname (if using a hostname), select a route, pick a source IP address and source port, and then send a SYN packet to the destination IP and port.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant D as DNS Resolver
    participant N as Cloud Network / Firewall
    participant S as Server
    C->>D: Resolve hostname
    D-->>C: A/AAAA record
    C->>C: Route lookup + source IP/port
    C->>N: TCP SYN
    N->>S: Forward if route and policy allow
    S-->>N: TCP SYN-ACK
    N-->>C: Return packet
    C->>S: TCP ACK
    Note over C,S: TCP connection established
~~~

Only after the TCP handshake succeeds does the application exchange data. Consequently, distinguish between:

- **DNS failure:** the client fails to obtain an address or obtains an inappropriate address.
- **Route failure:** the OS or cloud network lacks a path to the destination.
- **Firewall/policy drop:** packets are blocked or return traffic has no permitted path.
- **Port/listener failure:** the target host has no process listening on the expected IP/port.
- **Connection resource exhaustion:** the client, server, NAT, or load balancer runs out of connection resources.
- **Application failure:** TCP connects, yet the application fails to respond in time or closes the connection.

A TCP timeout does not tell you which layer failed. A dropped SYN packet, a dropped SYN-ACK, an overloaded server, or an exhausted NAT port pool can all leave the client waiting until timeout.

### 1.2. Layers to inspect

| Layer | Diagnostic question | Example failures |
|---|---|---|
| DNS | Does the name consistently resolve to the right address? | Resolver timeout, stale records, misconfigured split-horizon |
| Routing | Do the kernel and cloud select the right next hop? | Wrong default route, missing route, asymmetric return path |
| Network policy | Are packets permitted through every layer? | Security groups, NACLs, host firewalls, network policies |
| NAT/connection tracking | Are connections translated and state-tracked properly? | NAT port exhaustion, full conntrack table |
| TCP/UDP ports | Is the destination port listening? Are source ports available? | Missing listener, ephemeral port exhaustion |
| Host resources | Does the host have sufficient sockets, FDs, CPU, and memory? | File descriptor limits, SYN backlog, CPU saturation |
| Application | Are pools, timeouts, and concurrency sized properly? | Exhausted pool, hung workers, slow upstream |

### 1.3. Define scope before making changes

First determine whether the failure affects:

- One client or many clients.
- One hostname or all hostnames.
- One destination IP or every IP backing the service.
- One port/protocol or multiple services.
- One subnet, zone, node pool, or the entire system.
- Only new connections or established connections as well.
- A specific time window, such as during traffic surges or after a deployment.

These questions distinguish localized faults from widespread outages. For example, if only one client group fails while another succeeds, compare the two groups' routes, DNS resolvers, source IPs, and firewalls before modifying the server.

## 2. Collect evidence and reproduce the failure

### 2.1. Record details of a failing attempt

Every recorded failure should include at minimum:

- Timestamp with timezone.
- Target hostname or IP.
- Source IP, subnet, node, or instance.
- Protocol and destination port.
- Error type: DNS error, connection refused, timeout, reset, TLS error, or HTTP error.
- Wait duration before failure.
- Request ID or trace ID if available.
- Error rate and total request count over the same window.

Do not write only "flaky network." A record such as "from worker subnet A to api.internal.example:443, TCP timeout at ~3s, affecting 2% of requests over 10 minutes" carries far higher diagnostic value.

### 2.2. Compare successful and failed attempts

Run the same test from the same machine to the same target multiple times, recording timestamps and outcomes. Then test from another machine in the same subnet and a machine in a different subnet.

If failures occur on only one instance, inspect that host's local configuration. If multiple instances fail together at the same time, inspect shared dependencies such as DNS resolvers, NAT gateways, route tables, firewalls, load balancers, or the target service.

### 2.3. Test hop by hop

Do not start by changing multiple settings at once. Check in sequence:

1. Verify the hostname resolves accurately.
2. Verify the selected route and source IP.
3. Verify TCP reaches the destination port.
4. Verify the listener and firewall on the destination host.
5. Verify the return path.
6. Check connection limits and resources under rising load.
7. Correlate application logs, load balancer metrics, and network telemetry.

Save outputs from each step so you can compare before and after changes.

## 3. Diagnose DNS

### 3.1. How can DNS cause intermittent failures?

DNS resolves names into IP addresses. A hostname may return one or more A (IPv4), AAAA (IPv6), CNAME, or other record types. Results can vary by resolver, network location, TTL, health-based routing, or split-horizon configuration.

Common causes:

- Unresponsive or slow resolvers.
- One configured DNS server is unavailable.
- A/AAAA records contain stale addresses or decommissioned endpoints.
- One IP in a multi-record set is unhealthy while other IPs remain healthy.
- Application, OS, or library caches retain stale records longer than expected.
- Internal DNS and public DNS return different answers.
- Search domains or resolver settings append the wrong suffix to short hostnames.
- Some clients prefer IPv6 while the IPv6 path is not fully configured.

An application can report timeouts even while DNS succeeds: the resolver returns a syntactically valid IP, yet the network path to that IP is broken. Test every returned IP individually rather than checking only the hostname.

### 3.2. Check resolution on Linux

Common commands:

~~~bash
# Check resolver configuration
cat /etc/resolv.conf

# Check name resolution via NSS
getent ahosts api.internal.example

# Query A and AAAA records
dig api.internal.example A
dig api.internal.example AAAA

# Query via a specific resolver
dig @10.0.0.53 api.internal.example A

# Inspect CNAME and TTL
dig api.internal.example CNAME
dig api.internal.example A +noall +answer
~~~

`getent` is helpful because it goes through the OS Name Service Switch, which may include DNS, `/etc/hosts`, and other sources. `dig` lets you inspect raw DNS answers, TTLs, resolvers, and query latency directly.

Do not rely solely on `nslookup` or `dig` to assume the application gets the exact same result. Runtimes can maintain separate caches, use different resolvers, or apply different IPv4/IPv6 preference rules.

### 3.3. Check DNS on Windows

~~~powershell
# View DNS servers on interfaces
Get-DnsClientServerAddress

# Resolve hostname
Resolve-DnsName api.internal.example

# Query only A or AAAA
Resolve-DnsName api.internal.example -Type A
Resolve-DnsName api.internal.example -Type AAAA

# Query through a specific DNS server
Resolve-DnsName api.internal.example -Server 10.0.0.53

# Inspect DNS cache
Get-DnsClientCache
~~~

If results differ across machines, compare DNS servers, suffix search lists, interface metrics, caches, and network locations. Do not flush DNS caches fleet-wide before finding the root cause; doing so can trigger query spikes against resolvers and merely mask the underlying issue.

### 3.4. TTL and caching

TTL governs how long a DNS record may be cached under DNS rules. Low TTLs allow faster endpoint cutovers but increase resolver query volume. High TTLs reduce DNS load, yet clients may keep using old addresses longer than intended.

Beyond resolver caching, applications themselves may cache lookups. Some runtimes or libraries enforce independent cache policies, so DNS updates do not always take effect immediately across all processes.

When investigating:

- Compare authoritative answers against recursive resolver answers.
- Record remaining TTLs.
- Check OS and runtime caches.
- Inspect A and AAAA records separately.
- Test each returned IP using connectivity tools.
- Ensure old endpoints stay operational throughout transition windows.

### 3.5. Split-horizon and internal DNS

Split-horizon DNS returns different answers depending on location or resolver. For instance, `db.internal.example` might resolve to a private IP inside a VPC and have no corresponding public DNS record.

This is useful in cloud environments yet error-prone when hosts use the wrong resolver, VPNs do not push internal DNS, or containers receive improper DNS settings.

Test from inside the exact network namespace or container experiencing failures. A successful `dig` on the host does not prove a container uses the same resolver or has a route to the DNS server.

### 3.6. Distinguish DNS errors from broken IP connectivity

Once you obtain the IP, test the IP and port directly:

~~~bash
# Check route to a specific IP
ip route get 10.20.4.15

# Test TCP to the port
nc -vz -w 3 10.20.4.15 443

# Test HTTP/TLS using the hostname to preserve Host/SNI
curl -v --connect-timeout 3 https://api.internal.example/health
~~~

When testing a specific IP over HTTPS, preserve the hostname so TLS SNI and the HTTP `Host` header are sent accurately. Replacing the hostname with an IP directly in the URL can behave differently from real application connections.

## 4. Diagnose routing

### 4.1. Routes in the guest OS and cloud network

Packet paths are typically governed by two layers:

- **Guest OS:** routing table, policy routing, interfaces, source IP selection, and local firewall.
- **Cloud network:** subnet/VPC/VNet route tables, peering, transit gateways, NAT, load balancers, network firewalls, and NIC policies.

A valid route in Linux does not guarantee the cloud network has a path. Conversely, an accurate cloud route table will not help if the kernel picks the wrong NIC or source IP.

### 4.2. Check routes on Linux

~~~bash
# Interfaces and addresses
ip -br link
ip -br addr

# Default and specific routes
ip route
ip route get 10.20.4.15

# Policy routing
ip rule show
ip route show table all

# Check path with a specific source IP
ip route get 10.20.4.15 from 10.10.1.20
~~~

`ip route get` reveals which interface, gateway, and source IP the kernel plans to use for a packet. It does not prove packets pass firewalls or reach the destination.

On multi-NIC or multi-gateway machines, inspect both `ip rule` and custom routing tables. Lower route metrics generally win among equivalent routes, though policy routing can redirect lookups to another table.

### 4.3. Check routes on Windows

~~~powershell
# Interfaces and addresses
Get-NetIPConfiguration
Get-NetIPAddress

# Routing table
Get-NetRoute -AddressFamily IPv4
Get-NetRoute -AddressFamily IPv6

# Interface metrics
Get-NetIPInterface

# Test path to destination
Test-NetConnection 10.20.4.15 -Port 443 -InformationLevel Detailed

# Trace hops if ICMP/TTL-expired is allowed
tracert 10.20.4.15
~~~

`Test-NetConnection` is useful for testing TCP to a port, whereas `tracert` may be blocked by firewalls or intermediate networks. Do not conclude routing is broken merely because traceroute omits hops.

### 4.4. Default routes and multiple gateways

Machines with multiple NICs or gateways can choose unexpected egress paths. For example, a request enters via the frontend NIC while the response exits via the backend NIC due to default route priority. Stateful firewalls or NAT devices may then drop the response.

Determine:

- Which interface received the request.
- Destination and source IPs of the request.
- Route lookup for the response.
- Selected gateway.
- Cloud route tables for both outbound and return directions.
- Whether NAT, peering, or stateful firewalls sit along the path.

When source-IP-based routing is needed, configuring policy routing is usually more appropriate than adding multiple default routes. After changes, re-verify with route lookups and packet captures.

### 4.5. MTU and Path MTU Discovery

A connection can establish cleanly yet hang or crawl when transferring large payloads. One cause is an MTU mismatch along a path segment, or blocked ICMP messages needed for Path MTU Discovery.

Possible symptoms:

- TCP handshake succeeds, yet large file transfers stall.
- Small requests succeed while large responses time out.
- Specific VPNs, overlays, or tunnels fail.
- Retransmissions rise when sending large packets.

Check interface MTU:

~~~bash
ip link show
tracepath 10.20.4.15
~~~

You can use `ping` with the don't-fragment option on IPv4 to assist MTU checks, though flags and permissions depend on the OS. Do not lower MTU across the board based on a single test; verify MTU across the entire path and check the network's ICMP policy.

## 5. Diagnose firewalls and network policies

### 5.1. Firewall layers in the cloud

A cloud connection may pass through multiple enforcement layers:

- Security groups or network security groups attached to the NIC/instance.
- Network ACLs attached to the subnet.
- Cloud firewalls or network virtual appliances.
- Load balancer firewalls.
- Host firewalls inside the guest OS.
- Kubernetes `NetworkPolicy` or CNI policies.
- Destination service firewalls.

Security groups are stateful on many platforms, meaning return traffic for an allowed connection is automatically permitted. Network ACLs are stateless on some platforms, requiring explicit rules for both inbound and outbound directions, including ephemeral source port ranges. Exact behavior depends on the provider and service type.

Never assume that because a security group allows a connection, all other layers allow it too.

### 5.2. Analyze rules by tuple

Evaluate each network rule across:

- Source IP/CIDR.
- Destination IP/CIDR.
- Protocol (TCP, UDP, ICMP, or other).
- Destination port or port range.
- Target interface/subnet.
- Direction (inbound/outbound).
- Rule ordering and default action.
- Whether NAT or a proxy rewrites the source IP.

For example, a server listens on TCP/443 while a firewall only permits sources from an older CIDR. Clients in a new subnet fail while clients in the old subnet succeed. When traffic spreads across multiple sources, this looks like intermittent connectivity.

### 5.3. Check firewalls on Linux

On systems using nftables:

~~~bash
sudo nft list ruleset
sudo nft list counters
~~~

On systems still using iptables:

~~~bash
sudo iptables -S
sudo iptables -L -n -v
sudo ip6tables -S
~~~

With firewalld:

~~~bash
sudo firewall-cmd --state
sudo firewall-cmd --list-all
sudo firewall-cmd --list-all-zones
~~~

These tools may front the same underlying ruleset or coexist depending on distribution configuration. Avoid editing multiple firewall layers directly before knowing which tool is the authoritative configuration source.

### 5.4. Check firewalls on Windows

~~~powershell
Get-NetFirewallProfile
Get-NetFirewallRule -Enabled True
Get-NetFirewallSetting
~~~

To locate port-specific rules, filter further by protocol and port filter. Check Domain, Private, and Public profiles and verify which profile applies to each interface.

### 5.5. Use packet capture to pinpoint drops

On Linux:

~~~bash
# Observe handshakes to a specific host and port
sudo tcpdump -ni any 'host 10.20.4.15 and tcp port 443'

# View only packets with the SYN flag set, including SYN-ACK
sudo tcpdump -ni any 'host 10.20.4.15 and tcp port 443 and (tcp[tcpflags] & tcp-syn != 0)'
~~~

Diagnostic indicators:

| Observation | Investigation direction |
|---|---|
| No SYN leaves the client | Application, local routing, outbound firewall, or host resources |
| SYN leaves client with no SYN-ACK | Routing/cloud policy, intermediate firewall, unresponsive server, or return path |
| Server sees SYN but sends no SYN-ACK | Listener, host firewall, SYN backlog, or overloaded host |
| Server sends SYN-ACK but client never receives it | Return routing, NAT/stateful firewall, or intermediate packet drop |
| Immediate RST | No listener, application rejection, or active firewall reject |
| TCP handshake succeeds then data retransmits | Packet loss, MTU, congestion, slow host/app, or link fault |

Capturing on `any` can show packets across multiple interfaces or stages of the same flow. When NAT is present, capture on both sides of the device or correlate flow logs to match pre- and post-translation addresses.

Packet captures may contain payloads or sensitive data. Scope captures by host/port, duration, and file access controls; prefer header-only captures when appropriate.

## 6. Connection port limits and ephemeral ports

### 6.1. Source ports and destination ports

A TCP connection is identified by a four-tuple:

**source IP : source port -> destination IP : destination port**

Example:

**10.10.1.20:53124 -> 10.20.4.15:443**

Here:

- **Destination port 443** is the HTTPS service port on the server.
- **Source port 53124** is typically a temporary port chosen by the client.
- Each concurrent connection needs a distinct valid tuple; certain combinations can be reused according to TCP rules and socket states.

Temporary source ports are called **ephemeral ports**. Their range is configured by the OS and varies across Linux, Windows, and other platforms.

### 6.2. Ephemeral port exhaustion

A client opening massive numbers of short-lived TCP connections to the same destination IP/port can exhaust available source ports in its ephemeral range. New connections then fail with errors like `Cannot assign requested address`, `Address not available`, or timeouts depending on the stack and application.

Causes of rapid port consumption:

- Opening a fresh connection per request instead of reusing a connection pool.
- Opening and closing connections too rapidly.
- High counts of sockets in `TIME_WAIT`.
- Synchronized retries during upstream failures.
- Many workers connecting concurrently to a single endpoint.
- Applications using multiple source IPs or destinations with ineffective pool configuration.

Check on Linux:

~~~bash
# Ephemeral port range
sysctl net.ipv4.ip_local_port_range

# Socket summary by state
ss -s

# Count TIME_WAIT sockets
ss -ant state time-wait | wc -l

# View sockets connected to a specific destination
ss -ant dst 10.20.4.15:443
~~~

On Windows:

~~~powershell
netsh int ipv4 show dynamicport tcp
netstat -ano
Get-NetTCPConnection | Group-Object State | Sort-Object Count -Descending
~~~

Do not assume enlarging the ephemeral port range alone is enough. First measure new connections per second, socket lifetimes, source IPs, destinations, and connection reuse rates.

### 6.3. TIME_WAIT and connection reuse

`TIME_WAIT` is a TCP state entered after one endpoint actively closes a connection in specific cases. It handles delayed packets and ensures old connections terminate cleanly. Seeing many `TIME_WAIT` sockets does not automatically prove a fault; evaluate the count in context of the port range, connection rate, and destination targets.

Measures usually more effective than arbitrary kernel tuning:

- Enable HTTP keep-alive and connection pooling.
- Reuse database and cache connections.
- Size pools appropriately for upstream capacity.
- Use reasonable timeouts to avoid holding sockets indefinitely.
- Avoid overly aggressive or unbounded retries.
- Use multiple destinations or source IPs when architecture genuinely demands it and the platform supports it.

Do not enable legacy TCP reuse/recycle kernel options from outdated guides without checking your kernel version. Some options have changed behavior or been removed; misconfiguring them can break connections and create security issues.

### 6.4. SNAT/NAT gateway port exhaustion

When multiple workloads access the Internet or external networks through one NAT gateway, the NAT device must allocate source ports to distinguish flows. High volumes of concurrent connections to the same destination or through the same NAT IP can exhaust SNAT ports, depending on platform mechanics and limits.

Indicators:

- Multiple VMs in the same subnet fail outbound connections simultaneously.
- Internal traffic stays healthy while outbound traffic via NAT fails.
- Errors rise alongside new-connection rates or traffic bursts.
- NAT gateway metrics report high port utilization, allocation failures, or drops.
- Adding another NAT path or source IP changes the error rate.

Investigation steps:

1. Confirm whether the subnet and routes traverse the NAT gateway.
2. Inspect provider-specific NAT metrics/counters.
3. Compare new connection rates, concurrent connections, and top destinations.
4. Check whether applications repeatedly open short-lived connections.
5. Check timeouts and connection reuse.
6. Evaluate scaling NAT capacity, adding NAT IP addresses, or splitting traffic per cloud design if needed.

Different platforms allocate NAT ports and enforce quotas differently. Never assume one fixed port count across all cloud providers; rely on metrics and documentation for the active service.

### 6.5. Full conntrack table

Linux can use connection tracking (`conntrack`) to track connection state, commonly used by firewalls and NAT. If entries reach the configured limit, new packets may be dropped or logs may report a full conntrack table.

Check when `conntrack` tools are installed:

~~~bash
sudo conntrack -S
sudo conntrack -C
sysctl net.netfilter.nf_conntrack_max
~~~

Commands and `sysctl` paths depend on loaded kernel modules. Not every VM uses conntrack for all traffic. Inspect insert-failed, drop, and current-count counters before raising `nf_conntrack_max`.

Raising the limit without adding memory or controlling connection volume increases host RAM consumption and masks connection leaks. Identify why entries are accumulating, check mismatched timeouts, or examine workloads opening excessive connections.

## 7. Server-side limits: listeners, backlogs, and file descriptors

### 7.1. Missing listener or wrong bind address

The server may not be listening on the expected port, or may be bound only to loopback. For example, an application bound to `127.0.0.1:8080` will not accept external NIC connections arriving on `10.20.4.15:8080`.

Check on Linux:

~~~bash
ss -lntup
sudo lsof -iTCP -sTCP:LISTEN -P -n
~~~

Check on Windows:

~~~powershell
Get-NetTCPConnection -State Listen
netstat -ano
~~~

Verify bind address, port, protocol, PID, and process state. `0.0.0.0` means listening on all local IPv4 addresses; IPv6 listeners and dual-stack behavior depend on socket options and OS configuration.

### 7.2. TCP listen backlog

When a client sends SYN, the kernel and application cooperate to establish the connection. If the server is overloaded or the application does not call `accept` fast enough, the SYN queue or accept queue can fill up. This causes delayed handshakes, retransmissions, or connection failures.

Relevant Linux settings/metrics:

~~~bash
sysctl net.core.somaxconn
sysctl net.ipv4.tcp_max_syn_backlog
ss -lnt
~~~

`ss -lnt` can display `Recv-Q` and `Send-Q` for listening sockets; exact interpretation depends on socket state and tool version. Check kernel logs and TCP counters if backlog overflow is suspected.

Raising backlog limits helps only if the application can accept and process connections. If CPU, workers, or the database are already saturated, deeper queues merely lengthen wait times.

### 7.3. File descriptor and socket limits

On Unix-like operating systems, sockets are file descriptors. A process opening too many files or sockets can hit `ulimit -n`, systemd `LimitNOFILE`, or system-wide limits.

Check:

~~~bash
ulimit -n
cat /proc/$(pidof my-service)/limits
ls /proc/$(pidof my-service)/fd | wc -l
cat /proc/sys/fs/file-nr
~~~

Replace `my-service` with the actual process name. `ulimit` in your interactive shell does not necessarily reflect the limits of a systemd-managed service. Inspect the unit file, overrides, and live process limits.

When encountering `Too many open files`, look for leaked sockets or files held open, connection leaks, unrotated log files, or pools failing to close resources. Raising limits may be needed alongside controlling memory and connection counts.

### 7.4. Exhausted connection pools

An application may have plenty of OS ports left yet exhaust its internal connection pool. For instance, an API has a pool of 50 database connections. If slow queries hold all 50 connections, new requests queue up even though the database and network are reachable.

Monitor:

- Pool size and active/waiting connection counts.
- Connection acquisition wait time.
- Connection hold duration.
- Query duration and lock waits.
- Timeouts, leak detection, and retry counts.
- Actual open connections on the database.

Do not blindly enlarge pool sizes. Databases enforce connection limits and each connection consumes memory and CPU. Optimize queries, transactions, pool timeouts, and concurrency within database capacity.

## 8. Intermittent connectivity in containers and Kubernetes

### 8.1. Test from the right network namespace

Each container or Pod has its own network namespace. DNS, routes, interfaces, and firewall paths inside can differ from the host. Therefore, a command succeeding on the node does not prove the Pod can connect.

Test from inside the failing container/Pod:

~~~bash
cat /etc/resolv.conf
getent ahosts api.internal.example
ip -br addr
ip route
nc -vz -w 3 api.internal.example 443
~~~

If the application image lacks debug tools, use an ephemeral debug container or a diagnostic Pod sharing the same namespace and network policy per platform procedures. Never install ad-hoc tools into production images just for debugging.

### 8.2. CNI, NetworkPolicy, and service routing

Kubernetes network paths may involve:

- Pod network interfaces and CNI plugins.
- `NetworkPolicy` rules.
- Service `ClusterIP` and `kube-proxy` or an alternative dataplane.
- CoreDNS.
- Ingress/Gateway and load balancers.
- Node routes, overlays, or eBPF dataplanes.
- Node and subnet security groups/firewalls.

If only one namespace or label selector fails, inspect `NetworkPolicy` first. If all Pods on the same node are affected, inspect the node, CNI, routes, and NICs. If a Pod fails to reach a Service while direct Pod IP connections succeed, inspect Service endpoints, dataplane state, and readiness.

### 8.3. DNS in Kubernetes

CoreDNS typically provides DNS for Pods. Causes of failure include CoreDNS overload, upstream resolver errors, `NetworkPolicy` blocking UDP/TCP 53, overly long search paths, or applications flooding DNS queries.

Check:

~~~bash
kubectl get pods -n kube-system -l k8s-app=kube-dns
kubectl get svc -n kube-system kube-dns
kubectl logs -n kube-system -l k8s-app=kube-dns --tail=100
~~~

Labels, namespaces, and CoreDNS deployments vary across clusters. Verify actual deployment/service names before running commands.

DNS normally uses UDP/53 but falls back to TCP/53 for large responses or retries. A firewall allowing UDP while blocking TCP can break certain queries.

### 8.4. Pod churn and connection resets

When Pods restart, scale down, or update endpoints, open connections to old Pods can be reset. Clients must handle connection errors and reconnect cleanly. Readiness probes keep new requests away from unready Pods, yet do not automatically migrate existing long-lived connections to other Pods.

Check:

- Pod restart counts and termination reasons.
- `EndpointSlice` churn.
- Readiness/liveness probes.
- Graceful shutdown and `terminationGracePeriodSeconds`.
- Connection draining at ingress/load balancers.
- Client keep-alive, retry, and idempotency behavior.

## 9. Systematic diagnostic workflow

### 9.1. Step 1: Define symptoms and scope

Record source, destination, port, protocol, timestamps, and error rate. Determine whether failures hit only new requests or existing open connections too.

### 9.2. Step 2: Check DNS

Resolve the hostname from inside the failing environment. Record A/AAAA answers, TTLs, and resolvers, and test each returned IP. Test direct connectivity to each IP while preserving hostname/SNI for TLS checks.

### 9.3. Step 3: Check routes and source IP

Use `ip route get` or an equivalent tool to confirm interface, gateway, and source IP. Inspect cloud route tables, peering, NAT, and return paths.

### 9.4. Step 4: Check ports and firewalls

Confirm the server listens on the right address/port. Inspect host firewalls, security groups, NACLs, `NetworkPolicy`, and load balancers across both outbound and return paths.

### 9.5. Step 5: Check TCP handshake and packet loss

Use `tcpdump`, flow logs, or network metrics to observe SYN, SYN-ACK, ACK, RST, and retransmissions. Pinpoint whether packets vanish at the client, intermediate network, or server.

### 9.6. Step 6: Check connection limits

Measure open sockets, `TIME_WAIT`, ephemeral port range, NAT port usage, conntrack count, listen backlog, file descriptors, and connection pools. Correlate spikes with failure timestamps.

### 9.7. Step 7: Check host and application load

Monitor CPU, memory, network, disk I/O, GC, worker queues, database latency, and upstream response times. TCP can connect cleanly while the application still times out because workers or dependencies are stalled.

### 9.8. Step 8: Apply controlled changes and verify

Change only one related group of settings at a time. Save old configs, prepare a rollback plan, and re-run the exact same test. Afterward, monitor error rates and latency long enough to span the load cycle that originally triggered the issue.

## 10. Symptom-to-investigation table

| Symptom | Possibilities to check | Useful evidence |
|---|---|---|
| Hostname resolves inconsistently | Resolver, upstream DNS, cache, records | `dig`, `Resolve-DnsName`, DNS logs |
| One of several IPs times out | Faulty endpoint, dedicated route, or firewall | Per-IP tests, health checks, flow logs |
| TCP times out while DNS succeeds | Routing, firewall drop, NAT, return path | `ip route get`, packet capture |
| Immediate connection refused | Missing listener or active reject | `ss -lntup`, server logs, RSTs |
| Failures surge under high load | Ports, NAT, conntrack, backlog, pools, FDs | Socket states, NAT metrics, app metrics |
| Only outbound Internet fails | Default route, NAT gateway, egress firewall | Route table, NAT metrics, flow logs |
| Only one subnet fails | Routes, NACLs, security policies, subnet DNS resolver | Cross-subnet configuration comparison |
| Small requests succeed, large payloads stall | MTU/PMTUD, packet loss, congestion | `tracepath`, retransmissions, packet capture |
| Open connections reset during deploys | Pod/VM replacement, draining, process restarts | Deployment events, endpoint changes |
| TCP connects yet HTTP times out | App workers, upstream, DB, pool, queue | Traces, app logs, pool metrics |

This table provides investigation starting points only. A single symptom can have multiple causes; confirm with evidence captured at the moment of failure.

## 11. Real-world troubleshooting examples

### Scenario: Intermittent outbound API failures under load

Workers in a private subnet call a partner API through a NAT gateway. At low load, requests succeed. As concurrent jobs grow, timeout rates climb. DNS still resolves the hostname, and internal database connections remain healthy.

Investigation workflow:

1. Record timestamps, hostname, returned IPs, and timeout rate.
2. Resolve the hostname repeatedly and test each target IP to rule out a bad endpoint.
3. Run `ip route get` to confirm traffic follows the default route to the NAT gateway.
4. Check outbound firewalls and security policies; no unexpected drops appear.
5. Inspect client sockets and observe rapidly growing new connections and high `TIME_WAIT` counts.
6. Check NAT metrics and observe high SNAT port usage alongside allocation failures at the exact error timestamps.
7. Inspect application code and discover every request instantiates a fresh HTTP client without reusing connections.
8. Update the application to use connection pooling/keep-alive, cap concurrency, and add retries with backoff.
9. Monitor new connection rates, NAT port usage, timeouts, and latency post-deployment.
10. If capacity still falls short, evaluate scaling NAT per provider features and distributing traffic according to cloud design.

Verify outcomes with before/after metrics. High `TIME_WAIT` alone does not prove NAT is the culprit; the decisive evidence is NAT allocation failures coinciding with error timestamps and dropping after reducing connection creation rate.

### Scenario: Only some clients see HTTPS errors

A service has two A records. One endpoint was replaced but still lingers in DNS or caches. Clients receive different records depending on resolver and timing. One endpoint works while the retired one no longer has a listener.

Steps:

- Query A records via both internal resolvers and authoritative DNS.
- Record TTLs and returned IP addresses.
- Test TCP/443 to each IP.
- Check health checks and listeners on each endpoint.
- Update records or restore the endpoint per procedure.
- Keep the old endpoint running across a transition period matching TTLs and application caches.
- Track error rates broken down by destination IP.

Lesson: a hostname can resolve successfully while still returning an unserviceable endpoint.

### Scenario: TCP handshake succeeds yet large uploads hang

Clients send small requests fine, while large file uploads time out. Packet captures show retransmissions of large segments. Neither routes nor firewalls show obvious changes.

The team checks MTU across the VPN, overlay, and subnet, finding a tunnel with a lower MTU where ICMP needed for Path MTU Discovery is blocked. After adjusting MTU or ICMP policies per network design, uploads are re-tested across multiple payload sizes.

## 12. Preventing intermittent connectivity

### 12.1. Controlled DNS design

- Use redundant resolvers and monitor query latency/errors.
- Manage TTLs to match endpoint cutover requirements.
- Retire stale records on schedule and monitor application caches.
- Verify both A and AAAA records.
- Use health checks to avoid returning unhealthy endpoints where supported.
- Monitor DNS from every critical subnet or network namespace.

### 12.2. Application connection management

- Use connection pooling and keep-alive.
- Configure separate timeouts for DNS, connect, TLS handshake, request, and response.
- Use bounded retries with exponential backoff and jitter.
- Retry only safely retryable operations; non-idempotent requests require idempotency keys or safeguards.
- Use circuit breakers to prevent retry storms when upstreams fail.
- Cap concurrency and queue depth.
- Close sockets, response bodies, and connections properly.

Total timeout budgets should align with request latency budgets. If connect timeout, read timeout, and retries are all overly generous, one request can pin workers and sockets for too long.

### 12.3. Capacity and connection limits

- Monitor ephemeral ports, `TIME_WAIT`, and connection rates.
- Monitor NAT gateway port usage and allocation failures.
- Monitor conntrack counts, drops, and insert failures.
- Monitor listen backlogs, socket queues, and file descriptors.
- Size pools to match upstream capacity.
- Limit connections per host or tenant.
- Check quotas and limits on load balancers or proxies.

### 12.4. Firewall and route management

- Manage route and firewall configurations as code where appropriate.
- Review changes to security groups, NACLs, `NetworkPolicy`, and host firewalls.
- Maintain symmetric bidirectional routes and verify return paths.
- Test both IPv4 and IPv6 when workloads run dual-stack.
- Avoid changing multiple network layers simultaneously without traces or evidence.
- Monitor flow logs and drop counters.

### 12.5. End-to-end observability

Combine data sources:

- Application logs with request IDs.
- Distributed tracing with DNS/connect/TLS/upstream spans.
- Client connection pool metrics.
- Host metrics and socket states.
- Cloud flow logs, NAT metrics, and load balancer metrics.
- DNS resolver logs and latency.
- Firewall counters and packet captures when required.

Label metrics by workload, zone, node pool, and destination service at controlled cardinality. Avoid using individual client IPs or request IDs as high-cardinality metric labels.

## 13. Common mistakes

**Testing only with ping to a hostname.** Ping typically uses ICMP and does not verify an application's TCP port. DNS may resolve while TCP is blocked.

**Testing only one IP behind a hostname.** DNS may return multiple addresses where only one endpoint is broken. Test every IP.

**Assuming DNS success implies connection success.** DNS only maps names to addresses; routing, firewalls, listeners, and applications can still fail.

**Increasing timeouts to hide failures.** Longer timeouts hold workers and sockets longer, worsening resource exhaustion.

**Unbounded retries.** Retry storms multiply new connections and load on failing services, risking ephemeral or NAT port exhaustion.

**Raising ephemeral port ranges without measuring.** The real issue may be connection leaks, NAT, conntrack, or pools. Find where resources are actually exhausted first.

**Raising listen backlogs or file descriptors without checking the app.** If workers cannot accept or process fast enough, larger queues just make requests wait longer.

**Checking only the host firewall.** Cloud security groups, NACLs, routes, NAT, load balancers, and `NetworkPolicy` can all drop traffic.

**Ignoring the return path.** Requests reaching the server do not guarantee responses return along the right path. Inspect source IPs, policy routing, and stateful devices.

**Editing multiple layers at once.** Changing routes, DNS, and firewalls simultaneously obscures which change fixed or broke traffic. Change one layer at a time and keep evidence.

## 14. Troubleshooting checklist

### Gather information

- [ ] Record timestamp, source, destination, port, protocol, and request ID.
- [ ] Identify affected scope: clients, subnets, zones, nodes, and workloads.
- [ ] Classify failure type: DNS, timeout, refused, reset, or slow application.
- [ ] Compare a successful attempt against a failed attempt.

### DNS and routing

- [ ] Check A/AAAA records, TTLs, resolvers, and caches.
- [ ] Test every returned IP individually.
- [ ] Check routes, source IP, and egress interface.
- [ ] Check cloud route tables, peering, NAT, and return paths.
- [ ] Check IPv4/IPv6 and MTU if failures correlate with payload size.

### Firewalls and TCP

- [ ] Check security groups, NACLs, host firewalls, and `NetworkPolicy`.
- [ ] Confirm a listener is bound to the expected IP/port/protocol.
- [ ] Inspect SYN, SYN-ACK, ACK, RST, and retransmissions.
- [ ] Verify firewall rules in both outbound and return directions.

### Connection limits

- [ ] Check ephemeral port range and socket states.
- [ ] Measure `TIME_WAIT` counts and connection rate.
- [ ] Check NAT/SNAT port usage and allocation failures.
- [ ] Check conntrack count and drops.
- [ ] Check listen backlog, file descriptors, and connection pools.
- [ ] Correlate with CPU, memory, and upstream load.

### Remediation and verification

- [ ] Confirm root cause with evidence captured at failure time.
- [ ] Back up old configurations and prepare rollback steps.
- [ ] Change one related group of settings at a time.
- [ ] Re-run the exact same test from the affected environment.
- [ ] Monitor error rates and latency across a representative load cycle.
- [ ] Document root cause, actions taken, and preventive measures.

## 15. Key takeaways

- Intermittent connectivity can originate from DNS, routing, firewalls, NAT, source ports, backlogs, file descriptors, or the application.
- Successful DNS resolution does not prove every returned IP is healthy.
- Routing must be valid in both the guest OS and cloud network; always check forward and return paths.
- Security groups, NACLs, host firewalls, `NetworkPolicy`, and intermediate firewalls behave differently.
- Ephemeral port exhaustion is usually tied to connection creation rate, `TIME_WAIT`, and missing connection reuse.
- NAT gateways can exhaust port allocation; check service metrics instead of guessing limits.
- Conntrack, listen backlogs, file descriptors, and connection pools are independent limits.
- Packet captures identify SYN/SYN-ACK/RST behavior and pinpoint where packets drop.
- Connection pooling, proper timeouts, backoff retries, and concurrency limits relieve network pressure.
- Every change must be verified with repeatable tests and before/after metrics.

## Glossary

| Term | Meaning |
|---|---|
| DNS | Domain Name System, the system translating domain names into addresses and service records. |
| A record | A DNS record mapping a hostname to an IPv4 address. |
| AAAA record | A DNS record mapping a hostname to an IPv6 address. |
| TTL | Time To Live, the duration a DNS record may be cached. |
| Split-horizon DNS | A DNS setup returning different answers based on resolver or network location. |
| Route table | A table of rules selecting the next hop and interface for packets. |
| Asymmetric routing | Forward and return paths taking different network routes. |
| Security group | A firewall policy attached to cloud network or compute resources. |
| NACL | Network Access Control List, a subnet-level packet-filtering policy on certain cloud platforms. |
| Ephemeral port | A temporary source port assigned by the OS for an outbound connection. |
| Four-tuple | The set of source IP, source port, destination IP, and destination port identifying a TCP/UDP flow. |
| TIME_WAIT | A TCP state entered after one endpoint actively closes a connection under defined protocol rules. |
| SNAT | Source Network Address Translation, rewriting source addresses as packets traverse NAT. |
| Conntrack | Connection tracking mechanism commonly used by firewalls and NAT. |
| Backlog | A queue of connections or requests waiting to be accepted/processed by an application. |
| File descriptor | An identifier for an open process resource, including files and sockets on Unix-like operating systems. |
| Connection pool | A set of reusable connections maintained to reduce connection setup/teardown overhead. |
| Keep-alive | A mechanism keeping a connection open for reuse across multiple requests or exchanges. |
| MTU | Maximum Transmission Unit, the maximum configured packet/frame size over a link. |
| PMTUD | Path MTU Discovery, the mechanism determining an appropriate MTU across an entire path. |
| CNI | Container Network Interface, the networking plugin interface for containers and Pods. |
| NetworkPolicy | A Kubernetes policy controlling ingress and egress Pod traffic. |
| Retransmission | Resending a packet when protocol acknowledgment is not received. |
| Circuit breaker | A pattern that pauses calls to a failing dependency to prevent cascading failures. |
