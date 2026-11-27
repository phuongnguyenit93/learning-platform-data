# Public Load Balancer and Private Load Balancer

In the **Application Load Balancing** chapter of the **CLOUD_PROVIDERS_ORACLE** module, choosing a public or private load balancer determines where clients initiate connections to the application. This decision directly relates to VCN, subnets, routing, IAM, certificates, and how reachability is verified.

A system on Oracle Cloud Infrastructure can expose a website to customers while keeping Compute, storage, and Oracle databases on a private network. That system can also provide internal APIs for other services or office users over a private connection. Both needs can use the same load balancing mechanism, but the network entry point and the scope of clients allowed to access it differ.

## Learning Objectives

After this lesson, learners will be able to:

- Distinguish a load balancer's frontend address from backend addresses.
- Choose a public or private load balancer based on the client groups that actually need access.
- Design subnets, routes, and security rules for each connection leg.
- Explain why a public load balancer does not require backends to have public IPs.
- Verify reachability from the Internet, within the VCN, and over private networks.
- Combine health checks, monitoring, automation, and cost control for the chosen architecture.

## Scope: OCI Load Balancer

This lesson uses the **OCI Load Balancer** service, commonly seen with the flexible shape and the listener, backend set, and backend server components. The service distributes traffic from an entry point to servers reachable from the VCN. See [OCI Load Balancer overview](https://docs.oracle.com/en-us/iaas/Content/Balance/Concepts/balanceoverview.htm).

**Public/private** is a choice about frontend visibility. **Load Balancer/Network Load Balancer** is a choice of service. When doing the lab, choose Load Balancer in the Console and use the `oci lb` command group. Do not apply the source address behavior or configuration of another load balancing service by default to this lesson.

## Frontend and Backend Are Two Separate Legs

A request through a reverse proxy creates two legs to consider:

~~~text
Client
  -> load balancer frontend address + listener port
  -> backend address + application port
~~~

**Frontend** is the point clients connect to. **Listener** receives traffic on the configured port and protocol. **Backend set** groups backends, the distribution policy, and the health check. **Backend server** is the target running the application, such as the private IP of a Compute instance. See [Load Balancer concepts](https://docs.oracle.com/en-us/iaas/Content/Balance/Concepts/balanceoverview_topic-Load_Balancing_Concepts.htm).

For example, a client calls HTTPS port 443 on the frontend; the load balancer forwards to `10.40.20.11:8080`. Port 443 does not have to match 8080. Reaching 443 from the client also does not prove the load balancer can reach backend 8080.

In this design, the backend does not need to accept connections directly from the Internet. It only needs to accept legitimate traffic from the load balancer and authorized operational sources.

## Comparing Public and Private Load Balancers

| Criterion | Public load balancer | Private load balancer |
| --- | --- | --- |
| Frontend address | Public IP | Private IP in the chosen subnet |
| Typical clients | Browsers, applications, or partners accessing over the Internet | Services in a private network, clients over private connectivity |
| Access from the public Internet | Possible, if routes, listener, and security rules allow it | No public frontend for direct access |
| Backends | Can use private IPs | Can use private IPs |
| Typical DNS | Public name pointing to the public frontend | Name in private DNS pointing to the private frontend |
| User authentication | Handled by application design and protection layers | Still requires proper authentication and authorization |
| TLS | Configured per listener and backend set | Also configured per listener and backend set |
| Examples | Customer-facing website, partner API over the Internet | Service-to-service API, internal enterprise portal |

A public load balancer has a public IP as its entry point; a private load balancer uses a private IP. However, private does not mean only clients in the same subnet can access it. Clients from another VCN or an enterprise network can reach the private IP over configured peering or private connectivity. See [visibility and accessing a private frontend](https://docs.oracle.com/en-us/iaas/Content/Balance/Concepts/balanceoverview_topic-Load_Balancing_Concepts.htm).

A public frontend restricted by source in security rules is still a public load balancer. A private frontend whose DNS name is published on the public Internet is still a private frontend; publishing a name does not create a network path to that address.

## Two Typical Architectures

### Public Application, Private Backends

~~~mermaid
flowchart LR
    C["Internet customers"] --> IGW["Internet Gateway and appropriate routes"]
    IGW --> PLB["Public Load Balancer"]
    PLB --> A["Compute A - private IP"]
    PLB --> B["Compute B - private IP"]
    A --> DB["Oracle Database - private network"]
    B --> DB
~~~

In this model, the public load balancer sits in a public subnet, while Compute backends sit in a private subnet. Clients only know the frontend or the application's DNS name. Backends use private connectivity to communicate with the database and internal components.

Placing backends in a private subnet reduces the direct-access surface, but you still need to restrict listeners, backend ports, application accounts, and database permissions. An administrative path forwarded by a public listener can still be exposed even though the servers run in a private subnet.

### Internal API or Enterprise Application

~~~mermaid
flowchart LR
    S["Services in VCN"] --> ILB["Private Load Balancer"]
    O["Office users"] --> VPN["VPN or FastConnect"]
    VPN --> D["DRG and bidirectional routes"]
    D --> ILB
    P["Privately connected VCN"] --> ILB
    ILB --> A["Compute A"]
    ILB --> B["Compute B"]
~~~

Arrows in the diagram represent logical flows, not a substitute for concrete gateway and route design. Besides the path to the private load balancer, there must be a return path to the client. CIDRs must not overlap in ways that make routing ambiguous; security rules must permit the right sources.

For office clients, two separate tasks must be solved: resolving the address via DNS and having connectivity to that address. Private DNS can serve across VCNs and on-premises networks when resolvers, forwarding, and connectivity are configured accordingly. See [Private DNS on OCI](https://docs.oracle.com/en-us/iaas/Content/DNS/Tasks/privatedns.htm).

## Choosing Subnets and Understanding Availability

A public load balancer requires a public subnet. In a multi-Availability Domain region, you can use one **regional public subnet** or two **AD-specific public subnets** in two different ADs. This lab chooses a regional subnet for clearer configuration. A private load balancer uses a single subnet to host its primary and standby components; this lab places it in a regional private subnet. See [Load Balancer network requirements](https://docs.oracle.com/en-us/iaas/Content/Balance/Tasks/managingloadbalancer.htm).

The service's primary/standby mechanism helps preserve the frontend when a component fails. In multi-AD regions, a regional subnet supports placement for failover across ADs. If a region has only one AD, two components in the same AD cannot be treated as surviving a full AD outage. See [load balancer types and failover scope](https://docs.oracle.com/en-us/iaas/Content/Balance/Concepts/load_balancer_types.htm).

Three availability layers must be distinguished:

| Layer | Design question |
| --- | --- |
| Frontend | Can the load balancer maintain the entry point if a serving component fails? |
| Application | Are there healthy backends in another fault domain with enough capacity to absorb extra traffic? |
| Dependencies | Do databases, storage, and supporting services avoid single points of failure? |

Having a load balancer does not automatically make an application redundant. Two backends that depend on the same single process or unavailable shared data can still fail together.

The subnet must also have enough available addresses. In the IPv4 model described in OCI documentation, a public load balancer on a regional subnet uses two private IPv4 addresses; a private load balancer on a subnet uses three private IPs, covering the client-facing address and addresses for service components. Do not budget only one IP just because clients see a single endpoint. See [Load Balancer private IP usage](https://docs.oracle.com/en-us/iaas/Content/Balance/Tasks/managingloadbalancer.htm).

## Routing: Verify Each Leg

### Internet Clients to Public Frontend

The public subnet needs a route to the Internet Gateway per the design and security rules allowing the listener to receive the intended traffic. A public IP is only part of the requirement; a wrong listener port or blocking rule will still cause clients to fail.

A common IPv4 public subnet route is `0.0.0.0/0 -> Internet Gateway`. Do not copy this route to every subnet just to fix a timeout error. It must match the subnet's role and access model.

### Private Clients to Private Frontend

Clients in the same VCN typically use internal VCN routing. For clients over inter-network links, check routes on both sides and intermediate components, such as the DRG for enterprise network links.

A NAT Gateway serves outbound-initiated connections according to its function; it does not turn a private frontend into a public request-receiving endpoint. Adding NAT is not a way to make a private load balancer accept connections from arbitrary Internet users.

### Load Balancer to Backends

The load balancer must be able to reach the backend's private IP and port. For backends in the same VCN, there is no need to route requests out to the Internet and back into a server's public IP.

Verify these conditions independently:

- Route to the backend and return path.
- Load balancer egress and backend ingress.
- OS-level firewall.
- Application process listening on the appropriate network interface.
- Backend set protocol and port matching the application.

An application bound only to `127.0.0.1:8080` may respond to local checks but will not accept requests arriving on its private IP. A health check failing for this reason must not be "fixed" by opening every source in an NSG.

## Role-Based Security Rules

NSGs let you attach rules to groups of resources sharing the same role. One NSG can reference another NSG as source or destination when they are in the same VCN. An NSG is attached to the load balancer, while Compute VNICs are attached to the corresponding backend NSG. See [Network Security Groups](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/networksecuritygroups.htm).

Example for a system using HTTPS frontend 443 and HTTP backend 8080:

| Applied to | Direction | Source or destination | Destination port | Purpose |
| --- | --- | --- | --- | --- |
| Public LB NSG | Ingress | Served Internet client group | TCP 443 | Accept public requests |
| Private LB NSG | Ingress | Authorized internal client CIDR or NSG | TCP 443 | Accept internal requests |
| Public LB NSG | Egress | Backend NSG | TCP 8080 | Forward traffic and health checks if same port |
| Private LB NSG | Egress | Backend NSG | TCP 8080 | Forward traffic and health checks if same port |
| Backend NSG | Ingress | Public LB NSG | TCP 8080 | Accept connections from public LB |
| Backend NSG | Ingress | Private LB NSG | TCP 8080 | Accept connections from private LB |

These are rules for the primary connection path, not the entire firewall of a system. If health checks use a different port, add the exact flow for that port. Management flows, DNS, and application dependencies must be evaluated separately.

With stateful rules, return traffic for an allowed connection is tracked by state. If you choose stateless rules, you must design both return and forward directions; do not take a stateful rule table and assume it suffices for stateless.

Security lists and NSGs both apply to resources. An overly broad allow rule still present in a security list can defeat the restriction you just added in an NSG. They do not implement a "narrow NSG overrides every broader rule" mechanism. See [Security Rules principles](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/securityrules.htm). If the environment also enforces ZPR, flows must comply with the relevant ZPR policies as well.

## Listeners, TLS, and Client Addresses

A listener must match the port and protocol used by clients. Opening a port in an NSG without creating a listener will not make the application appear. Conversely, an existing listener blocked by security rules will still receive no connections. See [Load Balancer listeners](https://docs.oracle.com/en-us/iaas/Content/Balance/Tasks/managinglisteners.htm).

Public/private does not decide whether traffic is encrypted. HTTPS can be deployed for both. Two separate choices must be designed:

- TLS from client to listener.
- TLS or unencrypted connection from load balancer to backend.

With HTTPS, the hostname the client calls must match the certificate and the client must trust the certificate chain. Private DNS does not remove certificate validation requirements. Certificate issuance, renewal, and rotation must be managed for internal endpoints as well. See [managing certificates with OCI Load Balancer](https://docs.oracle.com/en-us/iaas/Content/Balance/Tasks/managingcertificates.htm).

Load Balancer acts as a reverse proxy. For HTTP, forwarded headers such as `X-Forwarded-For` and `X-Forwarded-Proto` help the application learn original connection details. OCI appends the peer address to `X-Forwarded-For`; values sent beforehand by the client in that header are not inherently trustworthy. The application must explicitly configure trusted proxies instead of arbitrarily using the leftmost address for authorization. See [Load Balancer Headers](https://docs.oracle.com/en-us/iaas/Content/Balance/Reference/httpheaders.htm).

## IAM Infrastructure Control vs. Application Access Control

IAM controls who can create, view, or modify Load Balancer resources via Console/API/CLI. It does not automatically require every HTTP request to a listener to carry an OCI user identity.

| Plane | Typical controls |
| --- | --- |
| Resource management | IAM policies, compartments, permissions for network and certificates |
| Network connectivity | Routes, NSGs, security lists, firewalls, and enforced network policies |
| Application access | Login, tokens, business authorization, mTLS when required |
| Operations | Permissions to read metrics/logs, swap backends, update listeners, and deploy configs |

Someone with permission to read load balancer configuration does not necessarily have a network path to a private frontend. A client that can call a listener does not necessarily have permission to create or delete a load balancer.

Scope administrative permissions to assigned compartments, adding necessary network permissions if the VCN and load balancer live in different compartments. Do not solve every error with a tenancy-wide management policy. Refer to [Details for Load Balancing](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/lbpolicyreference.htm).

## Lab: Comparing Two Frontends Over the Same Backend Group

The goal of this lab is to observe the difference in entry points. To reduce the number of servers to prepare, the two load balancers in the lab share two backends returning harmless content. This is an illustrative choice; a real internal admin service must not be placed in a public backend set just because a lab shares servers.

### Preparing the Network and Application

Use an authorized lab compartment. Check quotas and budgets before creating two load balancers. The addressing plan below is an example and must be adjusted if it overlaps your network:

| Component | Illustrative CIDR or address | Role |
| --- | --- | --- |
| VCN | `10.40.0.0/16` | Lab network |
| Regional public subnet | `10.40.0.0/24` | Hosts public load balancer |
| Regional private LB subnet | `10.40.10.0/24` | Hosts private load balancer |
| Regional backend subnet | `10.40.20.0/24` | Two Compute instances without public IPs |
| Regional client subnet | `10.40.30.0/24` | Test machine inside the VCN |
| Backend A | `10.40.20.11:8080` | Returns identifier A |
| Backend B | `10.40.20.12:8080` | Returns identifier B |
| Private client | `10.40.30.10` | Calls the private frontend |

Prepare two Compute instances with an HTTP server installed and listening on port 8080. Each server needs two endpoints:

~~~text
GET /health  -> HTTP 200, body ok
GET /        -> HTTP 200, body backend-a or backend-b
~~~

If NGINX is already installed, you can use the following illustrative server block in a lab configuration loaded in the HTTP context:

~~~nginx
server {
    listen 8080;
    server_name _;
    default_type text/plain;

    location = /health {
        return 200 "ok\n";
    }

    location = / {
        return 200 "backend-a\n";
    }
}
~~~

On server B, change the body to `backend-b`. Validate the configuration and reload using the NGINX service management method of your operating system. The `return` directive returns the status code and response body directly; see [NGINX return documentation](https://nginx.org/en/docs/http/ngx_http_rewrite_module.html#return).

From each backend itself, verify:

~~~bash
curl --fail --noproxy '*' http://127.0.0.1:8080/health
curl --fail --noproxy '*' http://127.0.0.1:8080/
~~~

The commands in this lesson are written for Bash. They are instructions for learners to run in their lab environment, not pre-captured output.

### Configuring Lab Rules

The lab uses an HTTP frontend on port 80 to separate network testing from certificate setup; send only synthetic test data, never accounts or secrets. For real application deployments, design HTTPS as covered earlier.

Create NSGs `lab-public-lb`, `lab-private-lb`, and `lab-backends`:

- Public LB ingress TCP 80 only from the test machine's current public IPv4 address, as `/32`.
- Private LB ingress TCP 80 only from `10.40.30.10/32`.
- Both LBs egress TCP 8080 to the backend NSG.
- Backend ingress TCP 8080 from each LB NSG.

Use stateful rules for these lab flows and verify no other security list or NSG permits broader access than intended. The backend OS firewall must also allow traffic from the LB infrastructure to port 8080 per the design.

Maintain Compute administration access through your approved mechanism, such as Bastion or a private network. You do not need to assign a public IP to a backend to add it to a backend set.

### Creating the Public Load Balancer

In the Console, select the right region and lab compartment, then create a **Load Balancer** resource with this configuration:

| Property | Lab value |
| --- | --- |
| Display name | `lab-public-lb` |
| Visibility | Public |
| Network | Lab VCN |
| Subnet | Regional public subnet |
| NSG | `lab-public-lb` |
| Shape | Flexible, choose bandwidth bounds matching quota and lab needs |
| Backend set | `web-backends` |
| Backend policy | Round Robin |
| Backends | Private IPs of A and B, port 8080, equal weight |
| Health check | HTTP, port 8080, path `/health`, expected status 200 |
| Listener | HTTP port 80, default backend set `web-backends` |

The public subnet needs the prepared Internet Gateway and route. Wait for work requests to complete and backends to become healthy before testing from the Internet.

### Creating the Private Load Balancer

Create another Load Balancer with:

| Property | Lab value |
| --- | --- |
| Display name | `lab-private-lb` |
| Visibility | Private |
| Network | Lab VCN |
| Subnet | Regional private LB subnet |
| NSG | `lab-private-lb` |
| Backend set | `web-backends`, created separately in this LB |
| Backends and health check | Same application contract as the public LB |
| Listener | HTTP port 80 |

Backend sets with the same name in two LBs are two separate configurations. Editing the health check on one LB does not automatically update the other.

Record the OCID and actual frontend address of both LBs. Do not use an internal service-component address as the client endpoint. Console steps for visibility, subnet, listener, and backends are described in the [guide to creating Load Balancers](https://docs.oracle.com/en-us/iaas/Content/Balance/Tasks/managingloadbalancer_topic-Creating_Load_Balancers.htm).

### Reading Configuration and Health via CLI

On an admin machine with OCI CLI configured, replace the values below with real OCIDs:

~~~bash
REGION="ap-singapore-1"
PUBLIC_LB_ID="REPLACE_WITH_PUBLIC_LB_OCID"
PRIVATE_LB_ID="REPLACE_WITH_PRIVATE_LB_OCID"

oci lb load-balancer get \
  --region "$REGION" --load-balancer-id "$PUBLIC_LB_ID"

oci lb load-balancer get \
  --region "$REGION" --load-balancer-id "$PRIVATE_LB_ID"

oci lb backend-set-health get \
  --region "$REGION" --load-balancer-id "$PUBLIC_LB_ID" \
  --backend-set-name web-backends

oci lb backend-set-health get \
  --region "$REGION" --load-balancer-id "$PRIVATE_LB_ID" \
  --backend-set-name web-backends
~~~

The `load-balancer get` command reads resource configuration; it does not open an HTTP connection from your machine to the frontend. See [CLI get Load Balancer](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/lb/load-balancer/get.html). The `backend-set-health get` command reads backend set status; see [CLI get backend set health](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/lb/backend-set-health/get.html).

### Testing from Two Network Locations

On the Internet machine whose address was allowed, substitute the public IP and run:

~~~bash
PUBLIC_LB_IP="REPLACE_WITH_ASSIGNED_PUBLIC_IPV4"

curl --fail --show-error --noproxy '*' \
  --connect-timeout 3 --max-time 10 \
  "http://$PUBLIC_LB_IP/"
~~~

On machine `10.40.30.10` inside the VCN, use the assigned private frontend:

~~~bash
PRIVATE_LB_IP="REPLACE_WITH_ASSIGNED_PRIVATE_IPV4"

curl --fail --show-error --noproxy '*' \
  --connect-timeout 3 --max-time 10 \
  "http://$PRIVATE_LB_IP/"
~~~

You can repeat multiple requests to observe both backends:

~~~bash
for attempt in 1 2 3 4 5 6; do
  curl --fail --silent --show-error --noproxy '*' \
    --connect-timeout 3 --max-time 10 \
    "http://$PRIVATE_LB_IP/"
done
~~~

Evaluate across multiple requests and backend state rather than demanding a strict alternating pattern on every call. Connection settings, persistence, or health changes can affect observations.

Acceptance matrix for the lab configuration:

| Test source | Target | Expected result |
| --- | --- | --- |
| Authorized Internet machine | Public LB, TCP 80 | Receives HTTP 200 from backend |
| Private client `10.40.30.10` | Private LB, TCP 80 | Receives HTTP 200 from backend |
| Internet machine without VPN, proxy, or private path to VCN | Private frontend | Cannot reach the lab endpoint over the Internet |
| Private client not authorized to call backends directly | Backend, TCP 8080 | Restricted by the designed rules |
| LB health checker | Backend, TCP 8080, `/health` | Receives HTTP 200 |

These results are expected test outcomes, not pre-measured evidence. Negative tests must run from the right source to the right endpoint; a DNS failure or wrong IP does not prove a security rule works properly.

### Observing Behavior When One Backend Fails

On lab backend A, temporarily stop the HTTP service using the active service manager. Do not stop backend B.

Monitor the health of both LBs. Once the health check detects that A has failed and updates status, new requests are served by the remaining healthy backend. Errors can occur during the detection window; do not infer absolute zero downtime from a short test.

Restart the service on A, wait for health to recover, and call both frontends again. Health checks continuously evaluate backends per policy; a recovered backend can be placed back into rotation. See [Health Check Policies](https://docs.oracle.com/en-us/iaas/Content/Balance/Tasks/load_balancer_health_management.htm).

Backend health answers the question "can the LB reach the check endpoint". It does not measure the entire path from Internet clients, does not fully test DNS, and does not replace application functional tests.

## DNS and HTTPS After Networking Works

Only after IP-level lab connectivity works should you add DNS so errors remain isolated by layer:

- The application's public name points to the public frontend.
- The name in the private zone points to the private frontend.
- Private clients must use a resolver capable of resolving that zone.
- Office clients need DNS forwarding configuration and connectivity to the appropriate resolver.

A name like `api.internal.example.com` is just an example. Having "internal" in the name does not automatically make an endpoint private.

With HTTPS, test using the real hostname so Host and TLS SNI are accurate. When you need to temporarily bypass DNS to isolate issues while preserving the hostname for TLS, you can use:

~~~bash
curl --fail --show-error \
  --resolve "app.example.com:443:$PUBLIC_LB_IP" \
  "https://app.example.com/health"
~~~

Use this only when you have deployed an HTTPS listener and matching certificate for the substituted hostname. Do not use options that skip certificate verification as an acceptance criterion.

## Monitoring, Automation, and Cost

A public frontend should be probed from a location reflecting external users. A private frontend needs a probe with appropriately scoped private connectivity. Placing a monitor on the public Internet and concluding a private LB is down because it is unreachable creates false alerts.

Combine unhealthy backend count, traffic volume, HTTP errors, latency, and bandwidth utilization. OCI emits Load Balancer metrics in the `oci_lbaas` namespace; select the right resource, listener, or backend set when reading metrics. See [Load Balancer Metrics](https://docs.oracle.com/en-us/iaas/Content/Balance/Reference/loadbalancermetrics.htm).

When automating infrastructure, keep a reproducible design together: compartment, visibility, subnet, NSG, listener, backend set, health check, certificates, and DNS. Before applying changes, check whether the plan exposes an internal listener to the Internet, swaps endpoints, or drops active connections. Never put certificate private keys into documentation or deployment logs.

Flexible shapes have minimum and maximum bandwidth; choose based on load, availability requirements, quotas, and budget. Two LBs serving two access boundaries can make sense, but you do not need to create another LB just for multiple paths if a proper listener/routing configuration already satisfies the requirement. See [bandwidth configuration when creating a Load Balancer](https://docs.oracle.com/en-us/iaas/Content/Balance/Tasks/managingloadbalancer_topic-Creating_Load_Balancers.htm).

Do not assume a private LB is free or a public LB is always more expensive solely due to visibility. Estimate the full architecture, including LBs, backend Compute, network connectivity, logs, and related resources. After the lab, delete the LBs and dedicated resources you created when no longer needed; verify shared resources before deleting NSGs, routes, subnets, or gateways.

## Isolating Issues by Symptom

| Symptom | Layer to check first | Direction to inspect |
| --- | --- | --- |
| Public frontend timeout | Client-to-listener path | Public IP, Internet Gateway route, allowed sources, listener port |
| Private frontend reachable from only one VCN | Inter-network connectivity | Bidirectional routes, peering or DRG, CIDRs, and security rules |
| IP works but hostname fails | DNS or TLS | Resolver, records, Host/SNI, certificate, and trust chain |
| Backend unhealthy | LB-to-backend leg | Port, protocol, path, status code, NSG, firewall, bind address |
| Backends healthy but client cannot connect | Frontend leg or listener config | Listener, ingress rules, routes, and testing from the right source |
| HTTP 502 or 504 received | Upstream connection and response | Backend health, response time, backend TLS, and relevant logs |
| Application sees proxy address | Reverse proxy and app logs | Forwarded headers and trusted proxy configuration |
| User not logged into OCI can still call public site | Application authorization | Check application auth mechanism and listener scope |
| One backend failure takes down entire service | Application availability | Remaining backend capacity, sessions, and shared dependencies |

Do not assign a single cause to every error code. Oracle's [troubleshooting health documentation](https://docs.oracle.com/en-us/iaas/Content/Balance/Reference/troubleshooting_health.htm) guides correlating health checks, timeouts, application behavior, and dependencies during isolation.

## How to Make an Architectural Decision

Choose a public load balancer when the client group needs an endpoint reachable over the Internet and you have defined the controls to enforce at the entry point. Keep backends and databases in private networks when there is no need to expose them publicly.

Choose a private load balancer when clients have a private network path to the service and access requirements do not need a public frontend. Alongside the LB, design routes, DNS, certificates, and application authorization for those clients.

Use both when there are two distinct access boundaries, such as a customer website and an internal API. Separate listeners, backend sets, or actual backends according to data scope; do not accidentally allow a public LB to route to internal-only functionality.

Completion evidence for the design includes reachability from authorized clients, blocking unauthorized sources, healthy backend status, correct application responses, and continued service when one backend fails. Visibility is the starting point of the design; results must be proven across the entire connection flow.
