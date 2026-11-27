# Stateful Rules, Stateless Rules, and Return Ports

A connection can fail even when the right service port is open. The cause often lies in the return direction: packets sent to port 443 on the server do not mean return packets also go to port 443 on the client.

In Oracle Cloud Infrastructure (OCI), security rules in Network Security Groups (NSGs) and security lists can operate in stateful or stateless mode. The difference lies in how flows are tracked and how return traffic is permitted.

This lesson belongs to the **Virtual Cloud Networks** chapter of the Oracle Cloud Infrastructure module. The goal is to read addresses and ports in each direction, pick the right rule mode, avoid overlap errors, and verify return paths when deploying Compute, application services, or Oracle databases in a VCN.

## 1. Read a Flow Before Writing Rules

For TCP or UDP, write down all five components:

~~~text
Protocol
Source IP
Source port
Destination IP
Destination port
~~~

Example of a client calling HTTPS:

~~~text
Client                                       Server
10.50.1.10:53000  ─────── TCP ───────────▶  10.50.2.20:443
10.50.1.10:53000  ◀────── TCP ────────────  10.50.2.20:443
~~~

In the example:

- The client actively opens the connection.
- The server listens on port 443.
- The client uses local port 53000 for this connection.
- When the server responds, the addresses and ports of both ends swap source/destination roles.

TCP has two fields, source port and destination port, to identify the communicating endpoints. See [RFC 9293 — TCP Header Format](https://www.rfc-editor.org/rfc/rfc9293.html#section-3.1).

Observed at the **server's VNIC**:

| Direction at server | Source IP | Source port | Destination IP | Destination port |
| --- | --- | --- | --- | --- |
| Ingress: client sends request | 10.50.1.10 | 53000 | 10.50.2.20 | 443 |
| Egress: server responds | 10.50.2.20 | 443 | 10.50.1.10 | 53000 |

Observed at the **client's VNIC**, those exact two packets have the opposite direction names: the request is egress, and the response is ingress.

Therefore, saying "open inbound 443" always needs an additional answer: **inbound at which endpoint?** When checking rules, do not switch observation points mid-analysis.

## 2. Where Do Stateful and Stateless Differ?

### 2.1. Stateful: Allows Return Traffic Based on Flow State

Stateful rules use connection tracking. When initiating traffic matches a rule, OCI recognizes responses belonging to that flow and permits the return direction without needing a separate symmetric rule on the same VNIC. See [Security Rules — Stateful Compared to Stateless Rules](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/securityrules.htm).

Example at the server:

| Attribute | Value |
| --- | --- |
| Direction | Ingress |
| Mode | Stateful |
| Protocol | TCP |
| Source | 10.50.1.10/32 |
| Source port | All |
| Destination port | 443 |

For the flow in the previous section, this rule permits the request into the server. The response from server:443 to client:53000 is handled via flow state.

That does **not** mean the server can actively open connections to any address. For example, the server opening a new connection from port 54000 to another API on port 443 is a different flow and requires appropriate permissive conditions.

Stateful rules also do not create routes, network paths, or listening processes. If the application is not running on port 443, the right rule is still insufficient for the connection to succeed.

### 2.2. Stateless: Each Direction Needs Explicit Permissive Conditions

Stateless rules do not provide automatic return permission based on connection tracking. For bidirectional exchange, an appropriate rule is needed in the reverse direction; designs typically use an explicit stateless pair.

In the API, isStateless=true selects stateless; false selects stateful. See [AddSecurityRuleDetails](https://docs.oracle.com/en-us/iaas/tools/java/latest/com/oracle/bmc/core/model/AddSecurityRuleDetails.html).

Example rule pair at the server for a test with a fixed client port:

| Direction | Mode | Peer CIDR | Source port | Destination port |
| --- | --- | --- | --- | --- |
| Ingress | Stateless | Source 10.50.1.10/32 | 53000 | 443 |
| Egress | Stateless | Destination 10.50.1.10/32 | 443 | 53000 |

The key point is that the egress row has **source port 443**, while destination port is **53000**.

If you only create egress with destination port 443, that rule does not match server:443 → client:53000 packets. It expresses a different type of traffic.

### 2.3. Comparison Table for Selection

| Aspect | Stateful | Stateless |
| --- | --- | --- |
| Management model | Tracks flows matching the rule | Evaluates permissive conditions per direction |
| How return is designed | Relies on recorded state | Write explicit return-direction conditions |
| Operational work | Monitor connection tracking capacity | Manage rule pairs and port ranges |
| Common mistake | Confusing responses with new connections | Forgetting to swap source/destination ports |
| Verification | Observe new connections and responses | Observe bidirectional packets, match each rule |

This is a choice at the network control layer. It does not describe whether the application holds session state. An application called a "stateless service" can still run behind stateful rules.

## 3. Ephemeral Ports and Return Port Ranges

### 3.1. Service Port vs. Client Port

The service port is where the server listens, such as HTTPS 443 or a database listener in a specific configuration. The client port is usually chosen by the OS when the application opens a connection and is called an **ephemeral port**.

Do not assume every OCI client uses the exact same port range. OS, configuration, and application can change the actual range.

On Linux, you can read the automatic port allocation configuration:

~~~bash
sysctl net.ipv4.ip_local_port_range
~~~

Linux documentation describes ip_local_port_range as the range used to pick local ports for TCP and UDP. See [Linux IP Sysctl](https://docs.kernel.org/networking/ip-sysctl.html).

When clients come from the Internet, the server operations team usually does not control all clients' port configurations. A narrow range inferred solely from one test machine can cause other clients to fail.

### 3.2. Writing Rules with a Defined Range

Let **E** be the set of client ports actually used in the design. For a server receiving HTTPS from a client group:

| Rule at server | Peer | Source port | Destination port |
| --- | --- | --- | --- |
| Stateless ingress | Client CIDR | E or All | 443 |
| Return stateless egress | Client CIDR | 443 | E or All |

Only use E when there is a basis for controlling or verifying it. With uncontrolled clients, All may be needed in the client port field while still restricting protocol, peer addresses, and service port as required.

**All in one port field does not mean every field of the rule is open.** For example, TCP egress with destination client CIDR and source port 443 still has specific conditions. However, a stateless rule does not prove a matching packet is a response to a prior request.

Any packet meeting the same conditions can also be passed by the rule layer. Do not use source port 443 as proof of server identity, TLS session, or business origin.

## 4. When the Instance Is the Active Caller

A Compute instance often both receives requests and calls other APIs or databases. Analyze each role separately.

Example of an app server calling an internal API:

~~~text
App instance                         API endpoint
10.50.2.20:54000  ────────────────▶  10.50.3.30:443
10.50.2.20:54000  ◀────────────────  10.50.3.30:443
~~~

At the **app instance's VNIC**:

| Direction | Source port | Destination port | Peer |
| --- | --- | --- | --- |
| Egress: initiation | 54000 | 443 | Destination 10.50.3.30/32 |
| Ingress: response | 443 | 54000 | Source 10.50.3.30/32 |

If stateful egress is used for the request, the response is handled by state at the app VNIC. If stateless is used, allow ingress with **source port 443, destination port in the client port set**.

Do not create ingress destination port 443 on the app just because the app is calling HTTPS. In this flow, the app is the client; the port receiving responses is 54000.

Also inspect the API endpoint. Egress permission on the app does not substitute for ingress permission at the API, and connection tracking at one end does not configure the other end.

### 4.1. Two VNICs, Two Control Points

When both client and server are Compute instances in a VCN, a typical stateful design has:

| Control point | Initiating traffic to allow |
| --- | --- |
| Client VNIC | Egress to server, service destination port |
| Server VNIC | Ingress from client, service destination port |

Return traffic is handled by state at each respective end. If one end switches to stateless, re-evaluate the return direction at that specific end.

An application calling Oracle Database follows the same reasoning: identify the exact endpoint, the listener port in the deployment configuration, and the actual client ports. Do not open a service port to every subnet just to mask a missing return rule error.

### 4.2. Load Balancers Can Create Multiple Flows

When a load balancer or proxy is present, draw each hop separately:

~~~text
Client ── connection A ──▶ Load Balancer
Load Balancer ── connection B ──▶ Backend
~~~

For deployment types with two independent connections, connection B has its own client address and port on the backend side. Do not take the original client's ephemeral port to write return rules for the backend.

Before applying a port table, determine whether the service terminates connections, preserves source addresses, or forwards via another mechanism. What must be recorded is the actual tuple at the VNIC being inspected.

## 5. Overlapping Rules Can Change Return Behavior

If a packet matches both a stateful rule and a stateless rule in the same direction, **stateless takes precedence and the flow is not tracked under that stateful rule**. See [Security Rules](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/securityrules.htm).

Example at the server:

| Rule | Mode | Source | Protocol | Destination port |
| --- | --- | --- | --- | --- |
| A | Stateful ingress | 10.50.1.10/32 | TCP | 443 |
| B | Stateless ingress | 10.50.0.0/16 | TCP | 443 |

Packets from 10.50.1.10:53000 to server:443 match both A and B. You cannot conclude A will guarantee automatic return traffic.

Without matching egress conditions, requests may reach the server while the return direction fails. Another egress rule, even a stateful one, might allow return packets through; therefore design must inspect all effective rules, not merely check whether "a stateless pair exists."

Recommended management approach:

1. Pick one clear mode per flow group.
2. Check whether broad rules overlap narrow rules.
3. Document why if both modes must be combined.
4. Test with new connections after changes.
5. Do not reason by display order like a first-match ACL.

### 5.1. Check Both Security Lists and NSGs

Security lists attach to subnets; NSGs attach to selected VNICs. Their rules jointly participate in traffic control. See [Security Lists](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/securitylists.htm) and [Network Security Groups](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/networksecuritygroups.htm).

For example, a new NSG has no egress, yet the subnet's security list still allows broad egress. In that case, a test "removing the return rule in the NSG" might still succeed.

Conversely, a broad stateless rule in another configuration can alter tracking assumptions. The inventory should include every security list on the subnet and every NSG attached to the VNIC under review.

## 6. UDP, ICMP, and Packets Unlike Standard TCP

### 6.1. UDP Still Has Source and Destination Ports

Example of an app sending a query to a self-managed DNS server:

~~~text
App 10.50.2.20:54001  ── UDP ──▶  DNS 10.50.3.53:53
App 10.50.2.20:54001  ◀─ UDP ───  DNS 10.50.3.53:53
~~~

At the app, a return stateless rule needs ingress from the DNS server, source port 53, and destination port 54001 or the appropriate client port set.

UDP has a source/destination port structure without a TCP handshake. See [RFC 768](https://www.rfc-editor.org/rfc/rfc768.html). Firewall connection tracking is a separate mechanism; do not assume UDP requires stateless mode.

The example uses a self-managed DNS server to illustrate tuples, not to describe every OCI-specific DNS endpoint. If an application needs both UDP and TCP to a service, evaluate both protocols.

### 6.2. ICMP Uses Type/Code, Not TCP/UDP Ports

Do not write "open ICMP port." For ICMP, the conditions to examine are protocol, type, code, and source/destination addresses.

Especially when using stateless rules with endpoints outside the VCN, ensure Path MTU Discovery messages pass. For IPv4, OCI documentation instructs allowing ingress ICMP type 3, code 4; blocking this message can cause hanging data transfers. See [Hanging Connection](https://docs.oracle.com/en-us/iaas/Content/Network/Troubleshoot/connectionhang.htm).

For IPv6, Packet Too Big messages use ICMPv6 type 2, code 0. See [Security Lists — IPv6 Traffic](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/securitylists.htm).

Ping succeeding also does not prove TCP 443 works. Ping and TCP test different types of traffic.

### 6.3. Note on Fragmented UDP Packets

Only the first fragment contains full port information to match TCP/UDP conditions; filtering by port can cause subsequent fragments to be dropped. OCI has specific guidance for fragmented UDP, including considering All for source and destination ports in relevant rules. See [Security Rules — Fragmented UDP Packets](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/securityrules.htm).

Do not open all rules immediately upon seeing a timeout. First determine whether it is fragmentation, an MTU error, or a normal return-port issue.

## 7. Hands-On: Observing the Difference at the Server

This exercise uses two lab Linux hosts in the same VCN with a direct path. There is no need to expose the test service to the Internet.

| Component | Illustrative configuration |
| --- | --- |
| Client | 10.50.1.10 |
| Server | 10.50.2.20 |
| Test service | HTTP on TCP 8080 |
| Client ports allowed for test | 53000–53009 |
| Point of change | NSG attached to server VNIC |

Use HTTP 8080 to observe networking without adding TLS certificate errors. The server must already have an HTTP service listening and the OS firewall allowing the lab traffic.

Assumptions to verify beforehand:

- Client has stateful egress to server:8080.
- Other security lists and NSGs have no rules masking the test outcome.
- A separate admin path exists, unaffected by the test changes.
- The example does not pass through NAT, proxies, or intermediate firewalls.
- If the environment uses ZPR, relevant policies must also permit the flow.

### 7.1. Read Current Configuration

The following OCI CLI commands use Bash and a principal with appropriate permissions:

~~~bash
export SERVER_NSG_OCID='ocid1.networksecuritygroup.oc1..replace_lab_nsg'

oci network nsg rules list \
  --nsg-id "$SERVER_NSG_OCID" \
  --all
~~~

The list command shows rules in the selected NSG; it does not automatically aggregate all security lists and NSGs on the VNIC. See [OCI CLI: NSG rules list](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/network/nsg/rules/list.html).

Record rule IDs before updating so you can restore the exact configuration. Only adjust assigned lab resources.

### 7.2. Phase A: Stateful Ingress

Configuration at the server:

~~~text
Direction:        Ingress
Mode:             Stateful
Protocol:         TCP
Source CIDR:      10.50.1.10/32
Source port:      All
Destination port: 8080
~~~

From the client:

~~~bash
curl --noproxy '*' \
  --local-port 53000 \
  --connect-timeout 5 \
  --max-time 15 \
  -v http://10.50.2.20:8080/
~~~

The local-port option instructs curl to use the chosen local port; if the port is unavailable, the command may fail before sending a request. See [curl manual](https://curl.se/docs/manpage.html#--local-port).

Expected result: receive an HTTP response without adding separate egress for return traffic at the server. If not achieved, check the listener, OS firewall, client-side rules, and path before concluding anything about stateful behavior.

### 7.3. Phase B: Stateless Ingress, No Return Path Yet

Change the lab ingress rule to stateless, leaving no unintended overlapping test rules. Do not add egress for server responses yet.

Retry using a new port, such as 53001. If no other rule permits the return direction, the client cannot complete the HTTP exchange.

Using a new connection helps avoid misleading results from open sessions, ports already in use, or stale state. A timeout alone does not prove exactly where packets were dropped; cross-check evidence in the next section.

### 7.4. Phase C: Add Return Stateless Egress

Desired rule pair at the server:

~~~text
Ingress:
  TCP, stateless
  Source 10.50.1.10/32
  Source port All
  Destination port 8080

Egress:
  TCP, stateless
  Destination 10.50.1.10/32
  Source port 8080
  Destination ports 53000-53009
~~~

The 53000–53009 range is strictly for controlled testing. It is not OCI's general default ephemeral range.

The following payload illustrates adding **the pair** via the OCI CLI:

~~~bash
oci network nsg rules add \
  --nsg-id "$SERVER_NSG_OCID" \
  --security-rules '[
    {
      "direction": "INGRESS",
      "protocol": "6",
      "isStateless": true,
      "sourceType": "CIDR_BLOCK",
      "source": "10.50.1.10/32",
      "tcpOptions": {
        "destinationPortRange": {
          "min": 8080,
          "max": 8080
        }
      },
      "description": "Lab HTTP ingress from controlled client"
    },
    {
      "direction": "EGRESS",
      "protocol": "6",
      "isStateless": true,
      "destinationType": "CIDR_BLOCK",
      "destination": "10.50.1.10/32",
      "tcpOptions": {
        "sourcePortRange": {
          "min": 8080,
          "max": 8080
        },
        "destinationPortRange": {
          "min": 53000,
          "max": 53009
        }
      },
      "description": "Lab HTTP replies to controlled client ports"
    }
  ]'
~~~

Protocol 6 is TCP. Omitting sourcePortRange on ingress means no source port restriction via that field. Structure is based on [AddSecurityRuleDetails](https://docs.oracle.com/en-us/iaas/tools/java/latest/com/oracle/bmc/core/model/AddSecurityRuleDetails.html) and [OCI CLI: NSG rules add](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/network/nsg/rules/add.html).

**The add command appends rules; it does not replace existing rules.** If you kept ingress from Phase B, add only the missing egress or update the rule set by ID; do not run the pair and accidentally create duplicate rules.

Test the client with local-port 53002. Expected outcome is working HTTP. Afterward, test a port outside the permitted range, such as 54000: if no other permissive path exists, responses will not match the lab egress rule.

At the end of the exercise, restore the recorded configurations and clean up lab resources according to your procedure.

## 8. Verifying with Packets, Flow Logs, and Metrics

### 8.1. Observing at Both Endpoints

On the lab server, you can observe:

~~~bash
sudo tcpdump -ni any 'host 10.50.1.10 and tcp port 8080'
~~~

Examples of interpreting output:

| Evidence | Initial inference |
| --- | --- |
| Client sends SYN, server does not see it | Check path and rules prior to observation point |
| Server sees SYN, does not generate SYN-ACK | Check listener and OS firewall |
| Server generates SYN-ACK, client does not see it | Check return path and rules at both ends |
| HTTP response received but application error code | Continue investigating application layer |
| Cannot bind client port | Check local ports before inspecting OCI rules |

Seeing an outbound packet in OS tcpdump does not guarantee it passed all subsequent network control points. Therefore, combine two-endpoint observation with OCI telemetry.

### 8.2. VCN Flow Logs

VCN flow logs record traffic accepted or rejected according to security lists/NSGs. They can be used to cross-check protocol, IP, port, and direction of the test flow. See [Flow Logs](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/vcn-flow-logs.htm).

Before inferring from "no records seen," confirm flow logs and capture filters cover the right VNIC, time window, and traffic type. An ACCEPT log at the network layer also does not prove the application processed the request successfully.

For the lab flow, look specifically for:

~~~text
10.50.1.10:53002 → 10.50.2.20:8080
10.50.2.20:8080  → 10.50.1.10:53002
~~~

Looking only at the forward direction easily misses the exact return-port error you are diagnosing.

### 8.3. VNIC Metrics and Connection Tracking

Useful metrics in the oci_vcn namespace:

| Metric | Used to observe |
| --- | --- |
| VnicIngressDropsSecurityList | Ingress packets dropped due to security rules |
| VnicEgressDropsSecurityList | Egress packets dropped due to security rules |
| VnicConntrackUtilPercent | Connection tracking table utilization |
| VnicIngressDropsConntrackFull | Ingress packets dropped when tracking table is full |
| VnicEgressDropsConntrackFull | Egress packets dropped when tracking table is full |

See [VNIC Metrics](https://docs.oracle.com/en-us/iaas/Content/Network/Reference/vnicmetrics.htm). Select the exact VNIC and time window matching the test.

Metrics help identify the cause category; they do not replace reading rules and tuples. If tracking utilization rises high, evaluate connection patterns, connection reuse, and performance needs before switching modes broadly.

Do not confuse OCI connection tracking with the Linux OS conntrack table. Observing one layer does not automatically reflect the full state of the other.

## 9. Choosing Mode Based on Operational Needs

A practical selection guide:

| Scenario | Recommended approach |
| --- | --- |
| Standard apps wanting fewer return rules | Start with stateful and restrict peers/service ports |
| High traffic needing tracking limit evaluation | Measure metrics, plan stateless if appropriate |
| Clients with controlled source ports | Can design stateless pairs with specific ranges |
| Uncontrolled external clients | Avoid assuming a narrow port range from a test host |
| Multi-hop connections via proxy or load balancer | Analyze each flow and control point separately |
| Services using multiple protocols | Specify TCP/UDP/ICMP and return requirements per type |

This is design guidance, not a guarantee that stateless is always faster or stateful always suffices for all loads. Choices also depend on operability, connection counts, and the rule scope to maintain.

Tracked state has a lifecycle; after an idle period, a flow may no longer have a tracking entry. Do not treat stateful rules as unlimited return permission. When hitting errors after idle periods, check timeouts, reconnect logic, and intermediate devices. See [Security Rules — Connection Tracking Details](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/securityrules.htm).

For systems requiring high availability, mode changes should have a test scope, before/after measurements, and a rollback plan. A return-rule error can disrupt both application APIs and database connections even while resources remain in a running state.

## 10. Mistakes to Spot Quickly

| Misconception | Corrected reasoning |
| --- | --- |
| Opening port 443 means both directions use destination 443 | Rewrite the tuple for the return direction |
| Stateful ingress lets the server call out anywhere | Distinguish responses from new server-initiated flows |
| Stateless only needs request-direction rules | Specify permissive conditions for the return direction |
| One host's Linux port range applies to all clients | Check actual OS, configurations, and applications |
| Narrow stateful rule beats broad stateless rule | Check stateless precedence when both match |
| NSG lacks egress so packets are definitely blocked | Check all effective security lists and NSGs |
| Ping works so HTTPS must work | Test the exact protocol and service port |
| Changing mode and retrying on an old connection suffices | Create a new connection, record tuple and timestamp |
| An ACCEPT packet means business success | Cross-check listener, TLS, and application output |

When handing over a rule set, include at minimum: the initiator, both endpoints, protocol, service port, client port set, rule mode, and how to test both directions. For stateless, you must be able to explain which rule allows return packets and why that range fits real clients.
