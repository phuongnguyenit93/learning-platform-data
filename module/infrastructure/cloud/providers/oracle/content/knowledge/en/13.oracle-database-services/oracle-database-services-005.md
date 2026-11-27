# Designing Subnets, NSGs, and DNS for DB Systems

In the **Oracle Database on OCI** chapter of the **CLOUD_PROVIDERS_ORACLE** module, this lesson covers network design for an **Oracle Base Database Service** DB System. The material connects tenancy, compartment, IAM, VCN, and Compute with database access, service operations, monitoring, and availability requirements.

An active DB System alone does not prove an application can connect. Clients must also resolve names properly, have bidirectional network paths, pass security controls, and call the right database service. Good design explicitly documents each of these prerequisites before deployment.

## 1. Objectives and Scope

After this lesson, learners will be able to:

- Segment subnets for applications, databases, administration, and DNS endpoints.
- Select routes to applications, on-premises networks, and the Oracle Services Network.
- Build NSGs around required traffic flows while checking security lists.
- Prepare DNS for single-node and RAC DB Systems.
- Design name resolution between OCI and on-premises environments.
- Verify connectivity across DNS, TCP, and Oracle Database layers.

The primary example uses IPv4, a private DB subnet, and OCI's Internet and VCN Resolver. Network CIDRs are illustrative values and should be replaced with your organization's IP plan.

This lesson focuses on Base Database Service DB Systems. Networking for Autonomous Database, Exadata, or dedicated recovery services must be designed per the requirements of those specific services.

## 2. Reference Architecture

An order-processing application runs on Compute inside a VCN and uses a database in a private subnet. Administrators access the system over a controlled management path. If a corporate network exists, private connectivity runs over a DRG and VPN or FastConnect.

| Component | Illustrative CIDR | Role |
| --- | --- | --- |
| VCN | 10.40.0.0/16 | Network address space for the system |
| App subnet | 10.40.10.0/24 | Application hosts permitted to call the database |
| DB subnet | 10.40.20.0/24 | DB System and associated IP addresses |
| Management subnet | 10.40.30.0/24 | Approved administrative hosts or components |
| DNS endpoint subnet | 10.40.40.0/27 | DNS endpoints when cross-network resolution is needed |
| On-premises network | 10.80.0.0/16 | Privately connected corporate network |

~~~mermaid
flowchart LR
    App["App Compute / NSG app"] -->|"SQL*Net"| DB["Private DB subnet / NSG db"]
    Admin["Admin path / NSG admin"] -->|"Controlled SSH"| DB
    Office["On-premises"] --> Link["VPN or FastConnect"]
    Link --> DRG["DRG"]
    DRG -->|"Private route & permissions"| DB
    DB -->|"HTTPS to Oracle services"| SG["Service Gateway"]
    SG --> OSN["Oracle Services Network"]
    CorpDNS["Corporate DNS"] -.->|"Query OCI domain"| Resolver["OCI DNS listening endpoint"]
    Resolver -.-> Names["VCN Private DNS"]
~~~

DNS traffic and SQL traffic are two separate flows. Corporate DNS might resolve the database name while the application host still lacks a route to the database IP. Conversely, connecting by IP might succeed while the application's name configuration remains broken.

In this example, the network compartment may differ from the DB System compartment. Compartments organize resources and scope IAM permissions; they do not automatically create network segmentation between hosts.

## 3. Designing the DB Subnet Before Provisioning

### Choosing a Private Subnet and Regional Scope

Base Database Service requires a VCN, subnets, routes, security rules, and connectivity to the Oracle Services Network. Oracle supports availability-domain-specific or regional subnets, and recommends regional subnets. [Source: VCN and Subnets](https://docs.oracle.com/en/cloud/paas/base-database/guide/vcn-subnets.html).

In the reference design:

- Choose a private subnet for the DB System.
- Use a regional subnet so subnet planning is not tied to a single availability domain.
- Attach the proper route table and DHCP options from the start.
- Separate the application subnet to keep lifecycle and access controls clean.

A regional subnet does not automatically deploy the database across multiple availability domains, nor does it provide a DR solution by itself. Availability also depends on DB System type, node placement, backups, and recovery plans.

A private subnet also does not mean all outbound traffic is blocked. Outbound reachability depends on gateways, routes, and security rules. The design in this lesson uses a Service Gateway for eligible Oracle services.

### IP Planning and Spare Addresses

Do not size a subnet solely by the current number of database hosts. Also account for:

- Platform-reserved IP addresses inside the subnet.
- Node, VIP, and SCAN addresses per the DB System configuration.
- Additional resources or replacement deployments.
- Room for recovery testing and expected growth.

The `/24` range in the example is illustrative for ease of planning, not a mandatory size for every DB System. Check the addressing requirements of your system type and available free IPs before creation.

Avoid CIDR overlaps with the app subnet, on-premises networks, and any VCNs slated for peering. A non-overlapping plan simplifies routing and enterprise connectivity later.

In addition to standard overlap checks, Oracle requires that the client subnet for both single-node and RAC DB Systems not overlap with **192.168.16.16/28**, the range used for the Oracle Clusterware private interconnect. [Source: Create a DB System — Network Information](https://docs.oracle.com/en/cloud/paas/base-database/guide/dbs-create-new.html).

Do not try to reconfigure the service's private interconnect to work around a flawed CIDR plan. Fix the subnet design before deployment.

## 4. Designing Routes by Destination

### DB Subnet Route Table

| Destination | Path in Reference Design |
| --- | --- |
| App subnet in same VCN | Local VCN routing per current configuration |
| Management subnet in same VCN | Local VCN routing with access control |
| 10.80.0.0/16 | DRG, if on-premises connectivity is needed |
| All <region> Services in Oracle Services Network | VCN Service Gateway |
| Other Internet destinations | Add only when a defined need and proper egress path exist |

In a standard VCN model, you do not need an Internet Gateway route for an app subnet to call a DB subnet in the same VCN. If the architecture includes a firewall or intermediate traffic inspection appliance, inspect the actual path in both directions.

For on-premises traffic, the DB subnet route is only one piece. Also check corporate-side routes, the DRG attachment, the DRG route table, and route advertisement or import mechanisms. Asymmetric or one-way routing can prevent the TCP handshake from completing.

### Service Gateway for Service Operations

Oracle's private subnet design uses a Service Gateway to reach the Oracle Services Network for operations such as provisioning, backups, and managed updates, as well as supported Oracle YUM repositories. The route uses a regional service CIDR label rather than a manually entered IP list. [Source: Private Subnet with Service Gateway](https://docs.oracle.com/en/cloud/paas/base-database/guide/vcn-subnets.html).

Configure the exact **All <region> Services in Oracle Services Network** label and the proper gateway in the DB subnet route table. Corresponding egress rules—typically HTTPS to that service label—are also required.

If backing up to Object Storage, include the path to that service in verification. If using a recovery service with its own subnet or endpoint, add that service's networking requirements; do not treat a Service Gateway route as the answer for every backup target.

A Service Gateway does not create a path for arbitrary Internet hosts to call into the database. Nor does it replace routing between the DB subnet and on-premises.

### NAT Gateway and Internet Gateway

A NAT Gateway can serve other outbound Internet needs from private networks when required by the architecture. Do not add a default route through NAT simply because a provisioning error's root cause hasn't been found.

If a resource must communicate with a destination outside the Oracle Services Network, document the destination, protocol, and justification before opening egress. For this lesson's private DB design, the Oracle service path is dedicated via a Service Gateway.

## 5. NSGs: Building Permissions by Role and Traffic Flow

### Groups in the Example

| NSG | Expected Members |
| --- | --- |
| nsg-app-orders | VNICs of the order application hosts |
| nsg-db-orders | DB System serving orders |
| nsg-db-admin | Approved administrative hosts |
| nsg-dns-endpoints | DNS resolver endpoints for cross-network resolution |

Creating an NSG does not make it active on a DB System. You must select the NSG in the DB System configuration or update the association via a service-supported mechanism.

OCI allows an NSG rule to reference another NSG as source or destination **within the same VCN**. Thus, app-to-db traffic can be expressed via group relationships rather than maintaining individual application host IPs. [Source: Network Security Groups](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/networksecuritygroups.htm).

If clients sit in another VCN or on-premises, do not use an NSG from that remote network as a cross-VCN reference. Choose a source CIDR or mechanism matching the connection path and actual source addresses reaching the DB.

### Application and Administrative Permission Matrix

The rules below cover application-level access and do not replace the full set of baseline rules required by the DB System:

| Rule Location | Direction | Source or Destination | Protocol / Target Port | Purpose |
| --- | --- | --- | --- | --- |
| nsg-app-orders | Egress | nsg-db-orders | TCP 1521 | Application initiates SQL connections |
| nsg-db-orders | Ingress | nsg-app-orders | TCP 1521 | Accept connections from application |
| nsg-db-orders | Ingress | nsg-db-admin | TCP 22 | SSH administration over controlled path |
| nsg-db-orders | Ingress | Approved on-premises client CIDR | TCP 1521 | Add only if clients connect directly |
| nsg-db-orders | Egress | Oracle Services Network service label | TCP 443 | Oracle service operations needing HTTPS |

Use **source port = All** for standard client connections, since the source port is typically an ephemeral port chosen by the OS. Port 1521 in the example is the listener destination port, not a port the client uses as its source.

Verify actual ports before deployment. TCPS connections require configuring the listener, certificates or wallets, and the corresponding port; opening TCP 1521 does not automatically enable TLS encryption.

### Baseline Rules and Additional Features

Base Database Service documentation requires accounting for baseline connectivity, ICMP needed by networking, and database-specific flows. For example:

- ICMP type 3 / code 4 for IPv4 Path MTU Discovery.
- ICMP for connection error notifications inside the VCN.
- Bidirectional TCP 22 between nodes as required by RAC.
- TCP 6200 when applications use ONS/FAN by design.
- Flows to Oracle services and required operational targets.

Oracle describes DB System rules as stateful while requiring SSH and egress scopes to be tailored to the hosts that genuinely need communication. [Source: Security Rules for the DB System](https://docs.oracle.com/en/cloud/paas/base-database/guide/security-rules.html).

Do not treat the TCP 1521 table above as a complete firewall set and delete all other rules. For RAC, intra-node rules and provisioning requirements must be verified before tightening rules.

ICMP for Path MTU Discovery is not SQL access from the Internet. Blocking all ICMP can cause subtle failures where small connections work while large data transfers hang.

### Statefulness and Limits of a Single Test

With stateful rules, OCI tracks connections and permits corresponding return traffic. You do not need to open every ephemeral destination port on the DB just to reply to a tracked SQL connection.

If mixing stateful and stateless rules covering the same flow, re-evaluate behavior per OCI documentation. This exercise keeps DB flows aligned with the service's stateful requirements.

Also inspect the OS firewall on the DB System. NSG permissions will not fix a stopped listener, an application targeting the wrong port, or a host-level firewall block. [Source: Stateful Rules and OS Firewall](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/securityrules.htm).

## 6. NSGs and Security Lists Are Additive

Security lists apply at the subnet level, whereas NSGs attach to resources or VNICs in the group. When both are used, the effective allowed rules on a VNIC are the union of relevant rules. A narrow NSG does not override a broad rule in a security list. [Source: Security Rules — Using Both](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/securityrules.htm).

Example of mismatched expectations:

~~~text
DB subnet security list:
  Allows 10.40.0.0/16 to TCP 1521

nsg-db-orders:
  Only declares nsg-app-orders to TCP 1521
~~~

In this situation, other sources within the VCN range are still permitted by the security list. To allow only the app to connect, inspect and tighten that broad rule as well after verifying actual dependencies.

Verification sequence:

1. List all security lists attached to the DB subnet.
2. List all NSGs attached to the DB System.
3. Find rules broadly matching SQL or SSH ports.
4. Reconcile against the approved traffic matrix.
5. Test new connections from both permitted and unpermitted sources.

An existing SQL session is not a valid test for whether a rule change blocks new connections. Use a fresh test session and log the timestamp of the change.

IAM is a separate layer: Console/API permissions to view or modify a DB System do not grant Oracle Database login rights. Network reachability to the listener likewise does not replace database accounts and privileges.

## 7. Internal DNS for DB Systems

### Preparing DNS Labels and DHCP Options

With the Internet and VCN Resolver:

- Enable DNS hostnames when creating the VCN and set a VCN DNS label.
- Enable DNS hostnames when creating the subnet and set a subnet DNS label.
- Attach DHCP options configured to use the Internet and VCN Resolver.
- Choose a valid, unique hostname prefix when creating the DB System.

These DNS labels must be decided upfront because they cannot be changed after creation. A subnet's display name is not a substitute for its DNS label. [Source: DNS in a Virtual Cloud Network](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/dns.htm).

Example:

~~~text
VCN display name: vcn-orders-prod
VCN DNS label:   prodsg
Subnet display: subnet-db-private
Subnet label:   db
Hostname prefix: ordersdb

Illustrative single-node FQDN:
ordersdb.db.prodsg.oraclevcn.com
~~~

This illustrates how the naming structure reads. When configuring clients, retrieve the actual hostname and connection details of the DB System rather than concatenating strings and assuming they exist.

Choose short labels that clearly separate environments and comply with DB System naming limits. When connecting across multiple subnets or VCNs, use FQDNs to avoid relying on client search domains.

### The Resolver Must Resolve Multiple Endpoint Types

A DB System needs name resolution for operations, not just for applications calling SQL. Oracle documentation lists Object Storage, Swift, Oracle YUM repository, and RAC SCAN endpoints.

Base Database Service supports custom resolvers on single-node VM DB Systems under documented conditions; for multi-node RAC, the listed option is Internet and VCN Resolver. [Source: DNS for the DB System](https://docs.oracle.com/en/cloud/paas/base-database/guide/dns.html).

Therefore, do not switch RAC's DHCP DNS to corporate DNS just to resolve one internal company name. Evaluate private resolver endpoints and forwarding within the supported architecture while preserving resolution for service-required infrastructure names.

Changing DHCP options also does not guarantee every host immediately adopts the new setting; account for DHCP lease renewal and DNS caching. Apply changes following procedures suitable for the DB System.

### Resolution Does Not Equal Connectivity

The Internet and VCN Resolver can resolve public names even when a host has no Internet path. Therefore:

~~~text
DNS lookup succeeds
  does not prove a route to the IP exists

TCP to the listener succeeds
  does not prove the Oracle service is registered

Database login succeeds
  does not prove the application has the right business privileges
~~~

When testing the path to the Oracle Services Network, verify endpoint resolution, routing, and egress rules together. Running only `nslookup` and concluding backups work is insufficient.

## 8. DNS for Applications, RAC, and Connection Strings

### Single-Node and RAC Use Different Entry Points

For a single-instance DB System, the connection string typically uses its corresponding hostname. For RAC, clients use **Single Client Access Name — SCAN**. SCAN can return multiple addresses; do not pin a single returned IP into application configuration and discard the rest. [Source: Database Connection Strings](https://docs.oracle.com/en/cloud/paas/base-database/guide/connect.html).

In RAC, the client contacts the SCAN listener and may then be redirected to a local listener on the node serving the service. Hence, routing and security rules must permit the post-redirect target endpoints as well, not just a single SCAN IP picked for a TCP check. [Source: Connecting to Oracle RAC Using SCANs](https://docs.oracle.com/en/database/oracle/oracle-database/19/riwin/about-connecting-to-an-oracle-rac-database-using-scans.html).

This is why a single successful test command to a SCAN port still does not prove a client can complete database connections.

### Choosing the Right Database Service

Applications need a service matching the PDB or workload. The default CDB-level administration service is not the default choice to put into a business application. Obtain service details from database administration and actual connection details. [Source: Database Services](https://docs.oracle.com/en/cloud/paas/base-database/guide/connect.html).

Illustrative JDBC format for testing a single node:

~~~text
jdbc:oracle:thin:@//DB_HOST_FQDN:1521/APP_SERVICE_FQDN
~~~

`DB_HOST_FQDN` is the hostname resolved from where the application runs. `APP_SERVICE_FQDN` is the Oracle Database service name, not the DB System name, SID, or resource display name.

For RAC and high-availability requirements, use a connect descriptor and timeout/retry settings appropriate for the driver and service. This lesson does not treat a minimal URL as a failover guarantee for the whole application.

Never place passwords in URLs or test logs. The connection string describes the path to the service; credentials must be managed via the application's secret mechanism.

## 9. DNS Resolution with On-Premises or Other VCNs

### Two Query Directions Requiring Separate Design

| Query Origin | Target Name | Design Flow |
| --- | --- | --- |
| On-premises client | DB name in OCI | Corporate DNS forwards appropriate domain to OCI listening endpoint |
| OCI host | Corporate service name | OCI forwarding endpoint and resolver rules point to corporate DNS |
| Client in another VCN | DB name in target VCN | Share resolution via private DNS views or appropriate forwarding |
| Client in same VCN | DB name in VCN | Internal resolver per DHCP options |

Having VPN, FastConnect, or peering does not automatically solve private hostname resolution. OCI provides listening endpoints to receive queries from other networks and forwarding endpoints to send queries per resolver rules. [Source: Private DNS](https://docs.oracle.com/en-us/iaas/Content/DNS/Tasks/privatedns.htm).

### Flow from Corporate Network to OCI

A sample design:

1. Create an OCI DNS listening endpoint in a subnet with a route to the corporate network.
2. Confirm the endpoint's resolver can see the domain containing the DB System name.
3. On corporate DNS, create a conditional forwarder for the required OCI domain.
4. Allow corporate DNS servers to reach the listening endpoint IP.
5. Test DNS directly from a corporate client.
6. Then test SQL from an authorized client.

Prefer forwarding specific domains per architecture rather than sending all corporate DNS queries to OCI. Avoid loops between the two resolvers where OCI sends a name back to corporate DNS and corporate DNS forwards it right back to OCI.

Listening and forwarding are two distinct endpoint roles. Endpoints need appropriate subnets, IP addresses, and network permissions; DNS endpoints can also have NSGs attached. [Source: Resolver Endpoints](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/dns-topic-resolver_endpoints.htm).

### Network Permissions for DNS Endpoints

For designs needing both UDP and TCP DNS, document port 53 flows to the exact DNS server or endpoint, along with return traffic per the active stateful/stateless setup. If using stateless rules, do not omit return traffic.

Permitted sources should be the actual corporate DNS servers sending queries, rather than the entire corporate network by default. Bidirectional routing over the private link is also required.

The VCN link-local resolver address **169.254.169.254** is not an endpoint IP for on-premises machines to query directly over VPN. Use a listening endpoint with an address in a subnet designed for that connectivity.

Details on UDP/TCP rules and inter-resolver connectivity are documented in [Private DNS — VCN Connectivity](https://docs.oracle.com/en-us/iaas/Content/DNS/Tasks/privatedns.htm).

## 10. Auditable Deployment Sequence

Execute in a lab compartment or designated environment:

1. Finalize non-overlapping CIDRs and check the private interconnect reserved range.
2. Create the VCN, DNS labels, and required subnets.
3. Attach route tables, DHCP options, and security lists per design.
4. Create the Service Gateway and route to the Oracle Services Network.
5. Prepare the DRG and corporate link if on-premises clients exist.
6. Create NSGs, adding baseline rules and role-based rules.
7. Verify DNS from a test host inside the app subnet.
8. When creating the DB System, select the exact VCN, DB subnet, NSG, and hostname prefix.
9. Retrieve the actual endpoint and service once the DB System is available.
10. Test from both permitted and unpermitted sources.
11. Verify operational tasks, including backup or patching paths per the environment.
12. Save the configuration map and evidence for comparison during future changes.

If a DB System already exists, start by reading its current configuration and identifying dependent applications. Do not alter DHCP, routes, or strip baseline rules wholesale without knowing the blast radius.

Permissions to create networking, permissions to select subnets/NSGs during DB System creation, and permissions to manage the database may belong to separate teams. Prepare IAM policies in the right compartments for each responsibility.

## 11. Reading Configuration with OCI CLI and Testing Connectivity

The commands below are practice guides, not commands already run against a tenancy. You need an authenticated OCI CLI and read permissions for the respective resources.

### Reading DB System and Subnet

~~~powershell
$Region = 'REPLACE_REGION'
$DbSystemId = 'REPLACE_DB_SYSTEM_OCID'
$DbSubnetId = 'REPLACE_DB_SUBNET_OCID'
$DbNsgId = 'REPLACE_DB_NSG_OCID'
$DbRouteTableId = 'REPLACE_DB_ROUTE_TABLE_OCID'

$DbArgs = @(
    'db', 'system', 'get',
    '--region', $Region,
    '--db-system-id', $DbSystemId
)
oci @DbArgs

$SubnetArgs = @(
    'network', 'subnet', 'get',
    '--region', $Region,
    '--subnet-id', $DbSubnetId
)
oci @SubnetArgs
~~~

Reconcile subnet ID, NSG IDs, DNS label/domain, route table, and DHCP options against the design. Do not compare display names alone since display names can duplicate across compartments. [DB System get reference](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/db/system/get.html), [Subnet get](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/network/subnet/get.html).

### Reading All NSG Rules and Route Table

~~~powershell
$NsgArgs = @(
    'network', 'nsg', 'rules', 'list',
    '--region', $Region,
    '--nsg-id', $DbNsgId,
    '--all'
)
oci @NsgArgs

$RouteArgs = @(
    'network', 'route-table', 'get',
    '--region', $Region,
    '--rt-id', $DbRouteTableId
)
oci @RouteArgs
~~~

The `--all` option avoids reading only the first page of NSG rules. Afterwards, still inspect other attached NSGs and related security lists, not just an NSG named "db." [NSG rules list reference](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/network/nsg/rules/list.html), [Route table get](https://docs.oracle.com/en-us/iaas/Content/Network/Tasks/get-details-routetable.htm).

### Testing DNS and TCP from the Right Source

From a Windows host with the designed network path and permissions:

~~~powershell
$DbHost = 'REPLACE_HOST_OR_SCAN_FQDN'
$ListenerPort = 1521

Resolve-DnsName -Name $DbHost -Type A
Test-NetConnection -ComputerName $DbHost -Port $ListenerPort
~~~

Record the active resolver and all returned addresses. For SCAN, test the appropriate addresses and verify an actual database connection, including the hop to the local listener after redirect.

From a Linux client, you can use:

~~~bash
DB_HOST='REPLACE_HOST_OR_SCAN_FQDN'
getent ahostsv4 "$DB_HOST"
~~~

Run this on an application host or representative host sharing the exact subnet, route, and network identity. An external laptop or Cloud Shell lacking the corresponding private connectivity cannot substitute for testing from the app subnet.

### Testing the Database Service

On a host with an Oracle client installed and test application credentials, use the exact service for a single-node test:

~~~text
sqlplus -L app_user@//DB_HOST_FQDN:1521/APP_SERVICE_FQDN
~~~

Enter the password when prompted by the tool. For RAC, use the connect descriptor prepared for the client and corresponding service.

After logging in:

~~~sql
select
    sys_context('USERENV', 'SERVICE_NAME') as service_name,
    sys_context('USERENV', 'CON_NAME') as container_name
from dual;
~~~

The output verifies you reached the expected service and container. Do not stop at an open TCP port and assume the application connection string is correct.

## 12. Verification and Diagnostic Matrix

### Testing Both Permitted and Unpermitted Sources

| Test Source | DNS | New SQL Connection | Meaning |
| --- | --- | --- | --- |
| Host in nsg-app-orders | Resolves properly | Succeeds with valid credentials | Application path works |
| Other VCN host, unapproved | May still resolve | Blocked by design | DNS does not equal access permission |
| Approved admin host | Resolves properly | Per granted rights; SSH checked separately | Admin path is separated |
| Approved on-premises client | Resolves via corporate DNS | Succeeds if route and rules exist | Both DNS and data path work |
| Internet host without private link | Not used to prove private access | No direct connection in this model | Matches private DB design |

A blocked test is only meaningful after confirming the right source, target IP, and traffic flow. If DNS was already broken from the start, a timeout does not prove the NSG is restricting traffic properly.

### Layer-by-Layer Investigation

| Symptom | Check First |
| --- | --- |
| Cannot resolve DB FQDN | Client resolver, DHCP, DNS labels, private view, or conditional forwarding |
| OCI resolves it but on-premises cannot | Listening endpoint, domain forwarder, routing, and port 53 rules |
| IP resolves but TCP times out | Bidirectional routes, NSG/security list, host firewall, listener |
| TCP works but Oracle reports unknown service | SERVICE_NAME, service registration status, and PDB state |
| One SCAN IP connects but app is intermittent | Other SCAN IPs and local listener targets after redirect |
| App connects but backups/updates fail | Service DNS endpoints, Service Gateway, routes, and related egress |
| Non-app host still reaches DB | Broad rules in security lists, other NSGs, or misunderstood source CIDRs |
| Small transfers work but large data hangs | MTU, required ICMP, VPN path, and intermediate devices |
| DNS changed but host still uses old values | DHCP lease, OS cache, runtime cache, or connection pool |

Oracle authentication errors are not solved by widening an NSG. Likewise, DNS errors are not fixed by opening every port to the entire VCN.

When evidence shows packets being dropped, use VCN Flow Logs and appropriate network observability tools. Correlate by timestamp with listener, resolver, and application logs; limit log contents so passwords or business data are not exposed.

## 13. Operations, Availability, and Cost

DNS is a dependency for new connections. Test scenarios where the corporate resolver cannot reach OCI, an endpoint stops responding, or the database is recovered into another environment.

For RAC, do not pin an application to one node as a "quick fix" for a SCAN issue and leave it as the final design. For DR, prepare routes, DNS, security rules, and services for the recovery system; changing a DNS record alone does not switch database state or transactions.

When changing rules, routes, or DHCP:

- Record the current configuration and active consumers.
- Prepare the change alongside a rollback plan.
- Test new connections, application pools, and Oracle service tasks.
- Monitor errors and latency after applying.
- Revoke temporary permissions after verification.

On cost, account for private connectivity, deployed gateways or network appliances, DNS per usage model, logs, test hosts, and database resources. Use an appropriate lab scale and check actual billing terms before deploying.

Do not pick an overly tiny CIDR just to feel like you are saving resources. Conversely, do not provision extra gateways or DNS endpoints without a clear traffic flow requiring them.

## 14. Consolidation Lab Exercise

In a lab environment, complete:

1. Diagram the VCN and subnets, recording CIDRs, DNS labels, and route tables.
2. Write the traffic matrix for app-to-db, administration, DNS, and Oracle Services Network.
3. Inspect effective rules across all relevant NSGs and security lists.
4. Verify the DB FQDN from the app subnet, then log into the exact application service.
5. Attempt a new connection from an unapproved host and explain the result.
6. If on-premises exists, test port 53 DNS and listener port SQL separately.
7. For RAC, explain the path from SCAN to local listener and how to avoid missing endpoints.
8. Draft a verification plan for backups/updates after tightening egress.

Deliverables should include the network diagram, traffic flow list, DNS map, and layer-by-layer test evidence. Retain required service rules, restore any settings altered for fault testing, and clean up only lab resources after checking dependencies.

Subnet design determines placement and routing; NSGs together with security lists govern allowed flows; DNS provides a stable entry point. DB System connectivity is only reliable when all three align with the service and how the application operates.
