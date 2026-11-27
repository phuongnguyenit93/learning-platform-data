# Private Endpoints, Egress, and Internet Outbound Control

## Learning Objectives

After this lesson, you can:

- Distinguish inbound connections to a function (ingress) from outbound connections from a function to other systems (egress).
- Explain private endpoints, private IPs, VPC/VNet integration, NAT, and firewalls in serverless architectures.
- Design private access paths from internal workloads to HTTP functions or managed services.
- Control internet outbound traffic using routes, NAT, firewalls, proxies, and allowlists.
- Connect Java functions to databases, object storage, internal APIs, and cloud services over private networks.
- Identify DNS, route, IAM, security group, quota, and connection limit failures.
- Apply common configuration patterns on AWS Lambda and Google Cloud Run functions.

## 1. Why Does Serverless Still Need Network Design?

Serverless removes most server management tasks, yet functions must still communicate with other systems. A Java function may receive HTTP requests from applications, read data from a private database, download files from object storage, call a partner API, and publish messages to a queue. Every connection traverses a network path with its own routing rules, DNS, authentication, and access controls.

If a function only calls public services, the architecture can be simple. However, production systems commonly require:

- Databases must not be exposed to the public internet.
- Only workloads inside the corporate network may call an internal endpoint.
- Functions must call a partner API from a fixed egress IP for partner allowlisting.
- All internet traffic must pass through a firewall or proxy for inspection and logging.
- Cloud services are accessed via private endpoints to avoid traversing the public internet.
- Production, staging, and development environments must be network-isolated.
- Hybrid connections must pass through a VPN or dedicated link to a data center.

Therefore, even though functions are managed by the serverless platform, the architecture must still define where the function accepts traffic from, where it calls out to, which source address it uses, and who is allowed to establish connections.

### 1.1. Ingress and Egress Are Two Different Directions

**Ingress** is traffic entering a function or service. For example, an internal application calling the function's HTTP endpoint.

**Egress** is traffic initiated by the function going outward. For example, a function opening a connection to Cloud SQL, RDS, a partner API, or the internet.

~~~mermaid
flowchart LR
    A[Internal client] -->|Ingress| B[HTTP function]
    B -->|Private egress| C[Private database]
    B -->|Internet egress| D[NAT / Firewall]
    D --> E[Partner API]
    B -->|Private service access| F[Managed cloud service]
~~~

A private ingress configuration does not automatically restrict egress. Similarly, routing egress through a VPC does not make an HTTP endpoint private on its own. Both directions must be designed and tested independently.

### 1.2. What Is a Private Endpoint?

A private endpoint is a connection point allowing workloads to access a service over a private network, typically using a private IP address or a dedicated routing mechanism. The goal is to keep traffic within a controlled network boundary, reduce reliance on the public internet, and shrink the service's exposure surface.

Depending on the cloud provider, implementations can be:

- A private endpoint/interface endpoint attached to a network interface inside a VPC.
- A gateway endpoint routing traffic to a managed service without requiring a public IP.
- A Private Service Connect endpoint or service attachment.
- An internal load balancer fronting the service.
- Private DNS resolving a service hostname to a private address.
- Private link or private endpoints for databases, storage, and SaaS.

A private endpoint does not equate to authentication. A client may be able to reach a private IP and still require IAM, database credentials, TLS, or application authorization. Networking and identity are two complementary layers of defense.

### 1.3. A Private Network Does Not Mean No Internet

A function can simultaneously:

- Access a database via private IP.
- Call Google APIs or AWS APIs via private endpoints.
- Call a partner API via NAT with a static public IP.
- Be blocked from accessing websites or destinations outside an allowlist.

This is a common architecture: internal paths go through the VPC, while internet paths are controlled at a centralized egress point.

## 2. Network Components to Understand

### 2.1. VPC, Subnets, and Route Tables

A VPC is a logically isolated private network in the cloud. Subnets partition a VPC into IP address ranges and are typically bound to a zone or region depending on the service. Route tables determine which next hop packets take toward a destination.

For example, a subnet might have:

| Destination | Next hop | Meaning |
|---|---|---|
| `10.20.0.0/16` | Local | Internal communication inside the VPC |
| `10.40.0.0/16` | Peering/VPN | To another connected network |
| `0.0.0.0/0` | NAT Gateway | IPv4 egress to the internet |
| Cloud service prefix | VPC endpoint/PSC | Service access via private path |

A route table only determines the path. It does not replace firewalls, IAM, or TLS checks. The existence of a route does not guarantee a connection will succeed; security groups, firewall rules, network ACLs, DNS, and target-side policies can still block it.

### 2.2. Private IP and Public IP

Private IPs are used within private networks or connected networks with appropriate routes. Public IPs are routable on the internet. Serverless workloads typically do not have a fixed per-invocation public IP of their own.

When a partner requires allowlisting a source IP, you need an egress point with a static public address, such as a NAT Gateway using an Elastic IP on AWS or Cloud NAT using reserved IP addresses on Google Cloud. The function initiates outbound connections; the public address the partner sees is the NAT/proxy address per network design.

Do not confuse an endpoint's IP address with an egress IP address. An HTTP function can receive requests via a public hostname while calling a partner API through a dedicated NAT IP.

### 2.3. NAT Gateway and Why NAT Is Not a Firewall

NAT (Network Address Translation) translates IP addresses/ports between a private network and an external network. A NAT Gateway enables workloads without public IPs to initiate outbound internet connections, while partners see the NAT's public address.

NAT primarily solves address translation and routing. It does not create an allowlist policy by HTTP hostname or content on its own. To restrict destinations, combine firewalls, route policies, proxies, or appropriate egress control mechanisms.

~~~mermaid
flowchart LR
    A[Serverless function] --> B[Private subnet / VPC route]
    B --> C[NAT Gateway]
    C --> D[Static public IP]
    D --> E[Internet API]
    B --> F[Private endpoint]
    F --> G[Managed service]
~~~

### 2.4. Firewalls, Security Groups, and Network ACLs

These mechanisms serve distinct roles:

- **Security group:** a resource/interface-level firewall, typically stateful; defines inbound/outbound rules by protocol, port, and source/destination.
- **Network ACL:** applied at the subnet level, typically stateless; requires evaluating both outbound and return traffic, including ephemeral ports.
- **Cloud firewall:** applies policies at the network or organization level; can control traffic across subnets, the internet, and hybrid networks.
- **Egress proxy:** an intermediary point to enforce hostname allowlists, inspect TLS per policy, authenticate, or log requests.
- **Route table:** determines the next hop, not a mechanism for inspecting traffic contents.

A connection can be blocked at any layer. When investigating, check DNS, routes, firewalls/security groups, NAT, TLS, and destination-side policies in sequence.

### 2.5. Private and Public DNS

DNS resolves hostnames to IP addresses. With private endpoints, private DNS zones typically ensure the same service hostname returns a private IP when queried from an associated VPC.

For example, `db.internal.example` might resolve to `10.20.5.12` inside the production VPC, while not existing or returning a different result on external networks. Split-horizon DNS lets the same hostname return different results depending on query origin.

Misconfigured DNS can cause a function to attempt connecting to a public endpoint despite a private route being configured. During testing, verify the exact hostname the application uses, the DNS resolver, private zone associations, and DNS TTL/caching.
 
## 3. How Serverless Function Networking Differs from VMs

A function is not a virtual machine that a team can SSH into, assign a public IP to, and manually manage routes on. The platform creates execution environments and manages their lifecycle. How a function connects to a VPC depends on the serverless service and the provider's network integration configuration.

General principles:

- Functions typically initiate outbound connections; they do not necessarily listen on a user-managed private IP.
- A VPC-attached function may use platform-managed network interfaces or connection paths.
- Each invocation does not necessarily get a dedicated IP; the source IP can change by instance or egress path.
- To obtain a stable source IP, a NAT/proxy or egress gateway with a static address is required.
- VPC integration can change the default path and introduce routing, DNS, firewall, and NAT requirements.
- Serverless concurrency can scale rapidly; calculate total connection counts to databases and private endpoints.

### 3.1. Network Connectivity Does Not Equal a Public Endpoint

An HTTP function can have a public URL while allowing only authenticated callers. Conversely, an endpoint with a private IP still needs authorization. When designing, answer two questions separately:

1. Who can establish a network connection to the endpoint?
2. Who is authorized to perform business actions after connecting?

The first belongs to ingress, routing, and firewalls. The second belongs to IAM, tokens, application authorization, and resource policies.

### 3.2. Common Connectivity Patterns

| Need | Common Implementation |
|---|---|
| Function calls a private database | VPC/VNet integration, private subnet, and firewall rules |
| Internal workload calls an HTTP function | Private ingress, internal load balancer, or private API endpoint |
| Function calls cloud services | Private service endpoint, gateway endpoint, or private API access |
| Function calls the internet with a fixed IP | NAT gateway or egress proxy with a static public IP |
| Function may call only specific domains | Egress firewall/proxy with an allowlist |
| Function accesses a data center | VPN, Interconnect/Direct Connect, or equivalent hybrid network |

## 4. Private Ingress: Restricting Who Can Call the Function

Private ingress is useful when a function processes internal data or exposes APIs exclusively for applications inside a corporate network. However, configuration differs across platforms.

### 4.1. AWS Lambda: Private API Endpoint in Front of the Function

Lambda does not operate like a VM with a fixed private IP where clients in a VPC connect directly to the function's port. A common pattern is placing an API Gateway private REST API in front of Lambda:

~~~mermaid
flowchart LR
    A[Client in VPC] --> B[Interface VPC endpoint]
    B --> C[Private API Gateway]
    C --> D[Lambda integration]
    D --> E[Application logic]
    E --> F[Private database]
~~~

Clients inside the VPC reach API Gateway through an interface VPC endpoint for the `execute-api` service. An API Gateway private API can be protected with a resource policy restricting the VPC/VPC endpoint, alongside IAM authorization or an appropriate authentication mechanism. Lambda permissions restrict which API Gateway is allowed to invoke the function.

Another option is an internal Application Load Balancer integrating a Lambda target in suitable architectures. In that setup, the load balancer and listener act as the private ingress point; configure security groups, target permissions, and application-layer authentication.

Do not confuse configuring Lambda inside a VPC for outbound access with creating a private inbound endpoint. Lambda VPC configuration primarily provides network access from the function to resources inside the VPC; a private API Gateway or internal load balancer is what accepts connections from clients.

### 4.2. Google Cloud Run Functions: Ingress Settings and Internal Load Balancing

Cloud Run functions (2nd gen) run on Cloud Run. Ingress can be configured to restrict request sources, such as accepting only internal traffic or traffic routed through an internal Application Load Balancer as supported.

Ingress options are typically interpreted as follows:

- **All:** accepts requests from sources permitted by IAM and service configuration.
- **Internal:** accepts only traffic identified by Google Cloud as internal under network/service conditions.
- **Internal and Cloud Load Balancing:** accepts internal traffic and traffic via supported Cloud Load Balancing.

The ingress setting controls the inbound path to the service. It does not create a private IP for the function on its own, nor does it configure the egress path to a database. If a private endpoint is needed for users in a VPC or hybrid network, choose an internal load balancer, Private Service Connect, or an internal access path fitting the client type and product in use.

### 4.3. Private Ingress Still Requires IAM

Even when an endpoint accepts only internal traffic, configure invoker permissions. For example, a workload inside a VPC may reach a private API yet should not be allowed to invoke every operation.

Apply simultaneously:

- Ingress restrictions to limit network sources.
- IAM/authentication to identify callers.
- Application authorization to enforce per-resource permissions.
- TLS to protect data in transit.
- Rate limits and quotas to bound usage.

## 5. Private Egress: Allowing Functions to Access Internal Networks

Private egress is the path allowing a function to initiate connections to private addresses such as databases, internal APIs, caches, or services in a VPC. Feature names and attachment mechanisms depend on the cloud provider.

### 5.1. AWS Lambda VPC Configuration

When configuring Lambda in a VPC, select subnets and security groups. Lambda manages the network interfaces needed for the function to access resources in the VPC.

SAM example:

~~~yaml
Resources:
  OrderFunction:
    Type: AWS::Serverless::Function
    Properties:
      Runtime: java21
      Handler: com.example.OrderHandler
      CodeUri: target/function.zip
      VpcConfig:
        SubnetIds:
          - subnet-private-a
          - subnet-private-b
        SecurityGroupIds:
          - sg-lambda-egress
~~~

Subnets are usually chosen across multiple Availability Zones for high availability. Lambda's security group should allow outbound traffic only to required destinations/ports. The database's security group must allow inbound traffic from Lambda's security group on the exact database port.

A Lambda placed in a subnet with a local route to a private database can reach the database without NAT. However, if the function needs to call the public internet, the private subnet route must have an appropriate egress path, typically a NAT Gateway. Assigning Lambda to a subnet labeled public does not assign a public IP to the Lambda ENI or automatically grant internet access.

### 5.2. Google Cloud: Serverless VPC Access Connector

Cloud Run functions 2nd gen can use a Serverless VPC Access connector to send traffic from the function into a VPC. A connector is a regional resource that connects to a VPC network. Configure the IP range, region, throughput, and scaling based on load requirements.

You can choose the egress policy:

- `private-ranges-only`: traffic to private ranges is routed through the VPC; remaining internet traffic can take the serverless environment's default path.
- `all-traffic`: all outbound traffic goes through the VPC, where centralized routes, NAT, and firewalls can be applied.

Flag names and configuration options can vary across CLI versions and deployment methods. With `gcloud functions deploy` gen2, configure the connector and egress settings per the current Google Cloud CLI documentation.

### 5.3. Direct VPC Egress on Google Cloud

On supported platforms and regions, Direct VPC egress allows Cloud Run/Cloud Run functions to connect directly to a VPC via subnets without needing a Serverless VPC Access connector. It removes the separate connector layer and enables applying VPC routes/firewalls.

Verify support for your workload type, region, networking mode, and current limits. Direct VPC egress and connectors have different startup, scaling, IP allocation, throughput, and cost characteristics; benchmark under realistic concurrency.

### 5.4. Connecting to a Private Database

A function can connect to a database via private IP when network paths, DNS, and firewalls are properly configured. Example:

~~~mermaid
flowchart LR
    A[Java function] --> B[VPC integration]
    B --> C[Private DNS]
    C --> D[Database private IP]
    D --> E[Database port]
~~~

Checkpoints:

1. The function is attached to the right VPC/network and subnets.
2. A route exists to the database CIDR or peered/hybrid network.
3. Security groups/firewalls allow the exact protocol and port.
4. The database listens only on required interfaces and addresses.
5. Private DNS resolves the hostname to the right private IP.
6. TLS and database authentication are properly configured.
7. Connection pools and concurrency do not exceed database capacity.

If the database uses private service access or Private Service Connect, configure the provider's connection mechanism properly. Never open a database to the public internet just to work around a function routing error.


## 6. Accessing Managed Services via Private Endpoints

Many cloud services provide private endpoints so workloads can access them without sending traffic over the public internet. Benefits include reduced public exposure, path control, and endpoint-level policies. Exact setup depends on the service.

### 6.1. AWS: Gateway Endpoints and Interface Endpoints

AWS offers two common groups of VPC endpoints:

**Gateway endpoints** are used for services such as Amazon S3 and DynamoDB. The endpoint is attached to subnet route tables; traffic to the service's prefix is routed through the gateway endpoint. It does not create a separate network interface inside the subnet.

**Interface endpoints** use AWS PrivateLink and create network interfaces in selected subnets. Clients connect to the private IP of the interface endpoint. The endpoint's security group controls traffic into the interface; private DNS can resolve the service's default hostname to the private endpoint.

~~~mermaid
flowchart TD
    A[Lambda in private subnet] --> B{Target service}
    B -->|S3 or DynamoDB| C[Gateway endpoint]
    B -->|Secrets Manager, SQS, SNS...| D[Interface endpoint]
    C --> E[Managed service]
    D --> E
~~~

When using an interface endpoint:

- Select subnets in appropriate Availability Zones.
- Allow TCP 443 from Lambda's security group to the endpoint's security group.
- Enable private DNS if using the service's default hostname.
- Check both the endpoint policy and the principal's IAM policy.
- Verify DNS and routes from each subnet.

With a gateway endpoint, attach the endpoint to the right route tables. If Lambda sits in a subnet using a different route table, traffic may still follow the default route and bypass the endpoint.

An endpoint policy is an additional filtering layer. It does not replace the caller's IAM policy or the service's resource policy. Requests must be permitted by all applicable policy layers.

### 6.2. Google Cloud: Private Google Access and Private Service Connect

On Google Cloud, there are multiple ways to access Google APIs and managed services privately:

- **Private Google Access:** lets workloads without external IPs in a subnet access supported Google APIs/services over Google infrastructure.
- **Private Service Connect (PSC):** creates a private endpoint inside a VPC to access Google APIs, published services, or other PSC-supported services.
- **Private Service Access (PSA):** a private service connectivity mechanism via VPC peering for certain managed services, such as traditional Cloud SQL private IP configurations.
- **Managed service private IP:** the service receives a private address inside a connected network per provider-supported mechanisms.

These mechanisms are not strictly interchangeable. Choose based on the specific service, connection direction, DNS requirements, region, and VPC topology. Read the target service's documentation to see whether it supports Private Google Access, PSC, or PSA.

### 6.3. Cloud SQL: Private IP and Connectors

Cloud SQL can be accessed using a private IP in a properly configured network. Google Cloud SQL connectors/Auth Proxy assist with authentication, encryption, and connection management, but the connector itself does not make every network path private. If traffic must avoid the public internet, configure private IP/PSC per supported options and ensure the function has VPC egress to that network.

Distinguish:

- **Network path:** whether the function has a route to the database's private IP.
- **Authentication:** which identity is allowed to connect.
- **Database authorization:** which database user/role is allowed to read or write tables.
- **Transport security:** whether the connection is protected with TLS or appropriate encryption.

A connector can simplify authentication and TLS, yet it does not remove the need to configure routes, firewalls, DNS, and database permissions.

### 6.4. Private Endpoints Do Not Guarantee All Traffic Is Private

An SDK may choose a public hostname by default even when the VPC has a private endpoint. Private DNS must be configured so that hostname resolves to the endpoint address. Some services have dedicated hostnames for private endpoints or require enabling private DNS.

During testing, verify:

1. Which hostname the application calls.
2. Whether DNS returns a private or public address.
3. Whether the route table has a path to the endpoint.
4. Whether security groups/firewalls allow the required TCP port.
5. Whether the endpoint policy and IAM allow the request.
6. Whether the TLS certificate remains valid for the hostname the client uses.

## 7. Controlling Internet Egress

Egress is one of the most critical points in securing serverless workloads. A function can be exploited to exfiltrate data, call malicious domains, or generate excessive traffic. Egress control restricts destinations and provides visibility into outbound traffic.

### 7.1. Three Levels of Egress Policy

Policies can be classified by control level:

| Model | Behavior | When Suitable |
|---|---|---|
| Direct/default egress | Function uses the platform's default internet path | Simple workloads not requiring a static IP or centralized inspection |
| Private-range egress | Private traffic routes through the VPC; internet traffic takes the default path | Need private database access without controlling all internet traffic |
| All-traffic through VPC | All traffic traverses the VPC, NAT, and firewall/proxy | Need static IPs, auditing, or centralized egress allowlisting |

Exact mode names and semantics depend on the provider. On Google Cloud, `private-ranges-only` and `all-traffic` VPC egress options are common examples. On AWS Lambda in a VPC, route tables and endpoints determine whether traffic traverses NAT, endpoints, or other paths.

### 7.2. Routing All Egress Through NAT and Firewall

A centralized architecture might look like:

~~~mermaid
flowchart LR
    A[Serverless functions] --> B[Private VPC subnet]
    B --> C[Route table]
    C --> D[Firewall / egress proxy]
    D --> E[NAT Gateway]
    E --> F[Static public IP]
    F --> G[Allowed Internet destinations]
    D --> H[Blocked destinations]
~~~

Steps:

1. The function connects to the VPC or subnet via the serverless networking mechanism.
2. Route tables direct internet traffic to a firewall, proxy, or NAT per design.
3. The firewall/proxy enforces allow/deny policies.
4. NAT performs address translation and provides a stable public source IP.
5. Logs and metrics capture destinations, bytes, errors, and connection counts.

In some architectures, the firewall sits in front of NAT; others place the firewall after NAT or use a dedicated proxy. Ordering depends on the product, route symmetry, and observability requirements. Verify both request and response paths to avoid asymmetric routing.

### 7.3. NAT Does Not Restrict Domains

NAT Gateway or Cloud NAT generally does not inspect HTTP hostnames. If you only configure NAT and assign a static IP, the function can still call many internet destinations depending on existing routes and firewalls.

To allow only necessary domains, consider:

- An egress proxy with a hostname allowlist.
- A firewall supporting appropriate FQDN/domain policies.
- DNS policies/filtering combined with network controls.
- Application-level allowlists for hostnames and ports.
- An egress firewall blocking unapproved destinations by IP/CIDR where appropriate.

IP allowlists can be hard to maintain for SaaS/CDN endpoints because IP addresses change and multiple domains share IPs. Hostname allowlists are easier to operate with supporting proxies or firewalls, but require understanding how the product handles DNS, TLS, redirects, and QUIC/UDP.

### 7.4. DNS Filtering Is Not the Sole Layer of Defense

Blocking DNS alone is insufficient to guarantee safe egress. Workloads can use raw IPs, DNS-over-HTTPS, alternate resolvers, or connect to an allowed hostname that redirects to another destination.

Combine DNS policies with firewalls/egress proxies, application allowlists, and IAM controls. If TLS inspection is needed, evaluate its impact on certificate pinning, mTLS, privacy, and data regulations.

### 7.5. Static Egress IP for Partners

Some partner APIs allow requests only from registered IPs. In that case, functions must route through a NAT/proxy with static public IPs:

- On AWS, NAT Gateway can use an Elastic IP.
- On Google Cloud, Cloud NAT can use reserved IP addresses.
- With a centralized proxy architecture, the proxy or firewall can serve as the public egress point.

Register all IPs that could be used under HA design. If NAT runs across multiple zones or multiple egress paths exist, the partner must allowlist all of them. Never assume a function has a fixed egress IP unless a NAT/proxy is explicitly configured.

### 7.6. IPv4 and IPv6 Egress

If a VPC/subnet supports IPv6, design routes and firewalls separately for IPv6. An IPv4 NAT Gateway does not handle IPv6 automatically. On AWS, outbound IPv6 from private subnets typically uses an egress-only Internet Gateway when one-way internet connectivity is needed. On other platforms, IPv6 egress mechanisms may differ.

If you control only IPv4 and overlook IPv6, functions may exit via an unpoliced path. Inventory both A/AAAA DNS records, IPv6 routes, and firewall rules before declaring egress restricted.

## 8. Egress Inside a Java Function

Java code initiates outbound connections using a hostname or IP; the actual network path is governed by network integration, DNS, routes, firewalls, and NAT. Code changes cannot replace VPC configuration. Still, applications must restrict destinations at the business layer, set timeouts, and avoid opening too many concurrent connections.

### 8.1. Using Hostnames and TLS

Prefer service hostnames over hardcoded IPs, especially when using private DNS or managed endpoints. Hostnames let DNS resolve to the appropriate IP per environment. TLS must validate certificates and hostnames; never disable hostname verification just because you are connecting over a private IP.

Java HTTP client example:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.Set;

public final class PartnerClient {

    private static final Set<String> ALLOWED_HOSTS =
            Set.of("api.partner.example");

    private final HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(3))
            .build();

    public String fetchStatus(String orderId) throws Exception {
        URI uri = URI.create(
                "https://api.partner.example/v1/orders/" + orderId);

        String host = uri.getHost();
        if (host == null || !ALLOWED_HOSTS.contains(host)) {
            throw new SecurityException("Destination host is not allowed");
        }

        HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(8))
                .header("Accept", "application/json")
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());

        if (response.statusCode() / 100 != 2) {
            throw new IllegalStateException(
                    "Partner API returned status " + response.statusCode());
        }

        return response.body();
    }
}
~~~

This example illustrates an application-level hostname allowlist, which does not replace a firewall. If URLs can be influenced by users, validate scheme, hostname, port, redirects, and post-DNS-resolution IP addresses to mitigate SSRF risks. Be especially cautious with redirects: an allowed hostname can return a redirect to another host.

`connectTimeout` bounds connection establishment time; `HttpRequest.timeout` bounds request/response wait time. Both must fit within the function's remaining deadline. If a function runs multiple requests concurrently, reuse clients and bound concurrency/connection pools.

### 8.2. When to Use a Proxy?

An egress proxy is appropriate when an organization needs to:

- Allowlist domains and ports at a centralized point.
- Log destinations and request metadata per policy.
- Authenticate workloads before permitting egress.
- Route traffic through security inspection or TLS inspection.
- Maintain an egress point with static IPs for partners.

Applications must be configured to use the proxy via a mechanism supported by the HTTP client/SDK. Not every SDK honors system proxy settings automatically. Verify each client library separately and avoid configuring proxies by passing secrets or credentials in URLs.

A proxy is a critical path component; design HA, capacity, timeouts, DNS, TLS certificates, and failure handling when the proxy is unavailable. If a proxy fails and the function falls back directly to the internet, the egress policy can be bypassed. Explicitly choose fail-closed or fail-open behavior based on security requirements.

### 8.3. Preventing SSRF and Unintended Destinations

Server-Side Request Forgery (SSRF) occurs when an attacker controls the address a server calls. In serverless, SSRF can cause a function to reach metadata endpoints, private APIs, databases, or internal services that the caller is not allowed to access directly.

Countermeasures:

- Do not allow clients to pass arbitrary URLs unless strictly necessary.
- Prefer mapping a service code to a fixed hostname in an allowlist.
- Allow only required schemes and ports, typically HTTPS/443.
- Inspect redirects and the final hostname after redirects.
- Block loopback, link-local, private IPs, or sensitive ranges if the use case does not require them.
- Do not rely solely on application DNS checks; enforce egress firewalls/proxies.
- Do not grant runtime service accounts broad permissions to access all internal resources.

Cloud metadata endpoints can supply credentials or tokens to workloads. Egress policies should prevent unnecessary requests to sensitive endpoints; additionally, use service identity and metadata protection per provider guidance.

## 9. Network Configuration Across Serverless Platforms

### 9.1. AWS Lambda in a VPC

When Lambda is attached to a VPC, define:

1. Private subnets in the required Availability Zones.
2. Lambda's security group with minimal outbound rules.
3. Database/internal API security groups allowing inbound traffic from Lambda.
4. Route tables to databases, peering, VPN, or Transit Gateway.
5. NAT Gateway if IPv4 internet access is required.
6. Gateway/interface VPC endpoints for frequently accessed AWS services.
7. Private DNS and endpoint policies when using interface endpoints.
8. Reserved concurrency or account concurrency to protect downstream systems.

Simple route table sample:

| Destination | Target |
|---|---|
| VPC CIDR | `local` |
| Data center network CIDR | VPN/Transit Gateway |
| S3/DynamoDB prefix | Gateway endpoint |
| `0.0.0.0/0` | NAT Gateway |

If all internet traffic must traverse a firewall, the `0.0.0.0/0` route can pass through AWS Network Firewall or an appliance/proxy per chosen architecture before exiting via NAT. Ensure symmetric return routing and avoid routing loops.

### 9.2. Google Cloud Run Functions

For Cloud Run functions 2nd gen, choose among:

- Serverless VPC Access connector to route traffic into a VPC.
- Direct VPC egress if supported by the platform, region, and function configuration.
- Private ingress or internal load balancing to restrict callers.
- Cloud NAT with reserved IP addresses for static IPv4 egress.
- Cloud Firewall/Cloud NGFW or proxy to control destinations.
- Private Google Access or PSC to reach Google APIs/services over private paths.

With a connector, choose a non-overlapping IP range, select the matching region, and size for throughput. With Direct VPC egress, check support, IP allocation, network tags, and service limits. In both cases, verify the egress mode: private ranges only or all traffic.

### 9.3. Azure Functions

On Azure Functions, VNet integration is commonly used to control outbound traffic from a function to resources inside a VNet. Private Endpoints can bring supported services such as Storage, Key Vault, or apps onto a private network. NAT Gateway or Azure Firewall can provide static egress IPs and outbound control depending on plan/networking configuration.

Exact capabilities and limits depend on hosting plan, OS, region, and networking features. Verify that your plan supports VNet integration, route-all, and private endpoints for the exact services before finalizing the design.

### 9.4. Quick Provider Comparison

| Need | AWS | Google Cloud | Azure |
|---|---|---|---|
| Function outbound to VPC | Lambda VPC configuration | VPC connector or Direct VPC egress | VNet integration |
| Private access to services | Interface/Gateway VPC endpoint, PrivateLink | PSC, Private Google Access, PSA | Private Endpoint |
| Static egress IP | NAT Gateway + Elastic IP | Cloud NAT + reserved IP | NAT Gateway |
| Centralized egress control | Network Firewall/proxy, routes | Cloud Firewall/Cloud NGFW/proxy, routes | Azure Firewall/proxy, routes |
| Private inbound HTTP | Private API Gateway/Interface endpoint or internal ALB | Internal ingress/load balancer, PSC per supported model | Private Endpoint or internal ingress per hosting model |

Do not treat feature names across providers as completely equivalent. Verify semantics, regions, quotas, pricing, and limits of the exact serverless service in use.

## 10. Identity, Network Policies, and Defense in Depth

Private networks restrict connectivity paths, yet do not fully define business authorization. A request can traverse a VPC endpoint and still be denied by IAM; conversely, a caller with IAM permissions but no route or firewall rule cannot connect either.

### 10.1. Separating Control Layers

| Layer | Question | Example Mechanism |
|---|---|---|
| Network reachability | Is there a network path to the destination? | Routes, VPC, VPN, peering |
| Network filtering | Is traffic allowed through? | Security groups, firewalls, NACLs |
| Service exposure | Does the endpoint accept traffic from this source? | Private ingress, API endpoint policy |
| Identity | Who is calling? | IAM, service account, workload identity |
| Authorization | What can the caller do on the resource? | IAM role, database role, application policy |
| Transport security | How is data protected? | TLS, mTLS, certificate validation |
| Application validation | Is the request valid and safe? | Schema validation, allowlists, SSRF protection |

Never rely on a single layer. For example, a private endpoint restricts only the network path; if every principal in the VPC has permission to access data, the risk surface remains large.

### 10.2. Least Privilege for Egress

Allow functions to connect only to required destinations:

- Open only the database port to the database's security group.
- Allow HTTPS only to required APIs.
- Use endpoint policies to restrict services/resources when supported by the provider.
- Separate subnets or security groups by workload type.
- Do not share a broad outbound security group across functions with different needs.
- Scope runtime service accounts and secret access per function.
- Maintain firewall rules with an owner, purpose, and review date.

If a function only needs to access a database and S3, broad internet egress does not need to be allowed. You can use a private endpoint for S3, route to the private database, and deny other destinations via network policy.

### 10.3. TLS and mTLS

A private network does not mean traffic is encrypted. Use TLS for database and HTTP API connections when supported by the service. For systems requiring mutual authentication, mTLS can verify both client and server using certificates.

Manage certificates through appropriate services, plan rotation, and never disable certificate verification as a temporary workaround. TLS inspection via a proxy can alter the certificate chain seen by clients; design trust stores and certificate pinning accordingly.

### 10.4. Environment and Tenant Segmentation

Do not share broad network policies between production and development. Separate VPCs/VNets or subnets by environment and apply distinct routes/endpoints. If using a Shared VPC or central network, still isolate via subnets, security groups, firewall policies, and IAM.

With multi-tenancy, bound concurrency and egress per tenant when needed. Do not let tenants supply arbitrary URLs or IPs for a function to call on their behalf. If the product must integrate with tenant-configured endpoints, enforce domain verification, block sensitive IP ranges, and check redirects/DNS rebinding.

## 11. Designing Static Egress and High Availability

A centralized egress point simplifies allowlisting and auditing, yet also creates a critical component in the request path. If NAT, the firewall, or the proxy becomes unavailable, functions can lose the ability to call external services.

### 11.1. Zonal/Regional NAT

On AWS, NAT Gateways are typically deployed per Availability Zone, with private subnet routes pointing to the matching NAT in that zone to reduce cross-AZ dependency. If multiple subnets route through a single NAT in another zone, a failure in that zone can impact multiple workloads and incur cross-AZ data transfer costs.

Cloud NAT on Google Cloud is a regional managed service, yet still requires configuring IP addresses, subnets/ranges, logging, and capacity per requirements. On all providers, check port/connection limits, NAT IP counts, and how scaling behaves as concurrency rises.

### 11.2. Static IPs and Partner Allowlisting

If a partner allows only registered IPs:

1. Reserve static public addresses at the NAT/proxy layer.
2. Route all required outbound paths through that exact point.
3. Register all IPs that could be used under failover/HA.
4. Test the actual source IP from the deployed environment.
5. Monitor NAT/proxy and alert when egress paths change.

Never register an IP based on tests from a laptop or local environment. A local machine's source address differs from the NAT address used by functions in the cloud.

### 11.3. Capacity and Port Exhaustion

NAT/proxies have limits on concurrent connections, port mapping, and throughput. A serverless function can scale faster than an egress point can allocate ports or handle traffic.

To prevent bottlenecks:

- Reuse HTTP clients and connection pools safely.
- Set limits on connection pools and concurrency.
- Use appropriate keep-alive settings to reduce new connection creation.
- Provision enough NAT IPs/capacity for concurrent connections.
- Monitor port allocation, dropped packets, connection errors, and latency.
- Use retries with backoff and jitter, avoiding retry storms when NAT/proxies are overloaded.

Do not increase max instances merely to fight latency if the bottleneck is NAT, a proxy, or a target API. Increasing concurrency can worsen port exhaustion.

## 12. Observing and Troubleshooting Connectivity Issues

When a function cannot reach a private endpoint or the internet, trace the packet path. A generic error log such as `Connection timed out` does not reveal whether the root cause lies in DNS, routing, firewalls, or the destination.

### 12.1. Diagnostic Workflow

1. **Confirm hostname and port:** is the application calling the right hostname, protocol, and port?
2. **Check DNS:** does the hostname resolve to a private or public IP? Is the private zone associated with the right VPC?
3. **Check routes:** does the function's subnet have a route to the destination or NAT/endpoint?
4. **Check firewalls:** do security groups, NACLs, cloud firewalls, and endpoint SGs allow outbound and return traffic?
5. **Check NAT/endpoint:** does NAT have valid addresses and capacity? Is the VPC endpoint attached to the right subnets/route tables?
6. **Check TLS:** are certificates, hostname verification, trust stores, and system clocks valid?
7. **Check IAM/policies:** does the caller have permission to invoke the function or use the target service?
8. **Check destination:** is the database/API listening, within capacity, and permitting the source to connect?

Distinguish common errors:

| Symptom | Possible Cause |
|---|---|
| `UnknownHostException` | Misconfigured DNS resolver, private zone, or wrong hostname |
| `Connection timed out` | Missing route, firewall drop, NAT/endpoint error, or unresponsive destination |
| `Connection refused` | Reached host, but port is not listening or service refused |
| `UnknownHost` on private endpoint | Private DNS not associated with the right VPC/subnet |
| `SSLHandshakeException` | Certificate, TLS version, hostname, or trust store issue |
| `403` from managed service | IAM, endpoint policy, or resource policy |
| `429` or throttling | Quotas, rate limits, or service capacity |
| Intermittent connections at scale | NAT/port exhaustion, connection pool, or downstream limits |

### 12.2. Network Logs and Metrics

Observability sources can include:

- VPC Flow Logs to view metadata on accepted/rejected network traffic.
- NAT Gateway/Cloud NAT metrics and logs to detect errors, dropped packets, port usage, or throughput.
- Firewall logs to identify which rules allow/block traffic.
- DNS query logs to investigate misresolved hostnames.
- API Gateway/Cloud Run request logs and Lambda/Cloud Run function logs.
- Distributed traces to pinpoint whether time is spent in DNS, connect, TLS, server, or database.
- Application metrics for timeouts, connection pools, connection counts, and retries.

Flow logs typically do not contain application payload contents. They help identify addresses, ports, protocols, and traffic status; combine them with application and target service logs to understand the full cause.

### 12.3. Avoid Over-Logging Data

Log IP addresses, hostnames, and request IDs when needed for investigation, while avoiding logging tokens, cookies, queries containing personal data, or full request bodies. For user-supplied hostnames or IPs, consider privacy and retention policies.

Choose metric dimensions with reasonable cardinality. Never create a separate time series per request ID or arbitrary URL; put request IDs in logs/traces instead of metric labels.

## 13. Common Architecture Patterns

### 13.1. Function Accessing Only a Private Database

~~~mermaid
flowchart LR
    A[Internal HTTP caller] --> B[Authenticated function]
    B --> C[VPC integration]
    C --> D[Private database]
~~~

Suitable when a function serves only internal applications and does not need internet access. Disable public ingress if supported by the architecture, restrict IAM invokers, and open database ports only from the required security group/connector.

### 13.2. Function Accessing Managed Services via Private Endpoints

~~~mermaid
flowchart LR
    A[Function] --> B[Private network]
    B --> C[Private endpoint]
    C --> D[Object storage or secret service]
~~~

Suitable when accessing S3, DynamoDB, Secrets Manager, Google APIs, or supported managed services over private paths. Combine endpoint policies, IAM, private DNS, and firewalls.

### 13.3. Function Calling the Internet via Centralized Egress

~~~mermaid
flowchart LR
    A[Function] --> B[VPC egress]
    B --> C[Firewall / proxy]
    C --> D[NAT static IP]
    D --> E[Partner API]
~~~

Suitable when partners require static IPs, the organization requires egress auditing, or domain allowlists must be enforced. Design HA and capacity for the firewall/proxy/NAT.

### 13.4. Function with Both Private and Public Destinations

~~~mermaid
flowchart TD
    A[Function] --> B{Destination}
    B -->|Private service| C[Private route / endpoint]
    B -->|Internet API| D[Firewall / proxy / NAT]
    C --> E[Internal database or managed service]
    D --> F[Approved external API]
~~~

This is the most common pattern. Crucially, routes to private services must not accidentally get NATed out to the internet, while internet traffic must not bypass the firewall/proxy when policy requires centralized egress.

## 14. Private Endpoint and Egress Design Checklist

- [ ] Ingress and egress are clearly distinguished.
- [ ] Which clients call the function and which destinations the function calls are identified.
- [ ] Databases and internal services are not exposed publicly just to fix connection errors.
- [ ] Private endpoints/service endpoints are selected appropriately per service and provider.
- [ ] Private DNS resolves to the right IP from the function's network.
- [ ] Route tables have valid outbound and return paths.
- [ ] Security groups, NACLs, and firewalls open only required protocols/ports.
- [ ] IAM, endpoint policies, and resource policies are configured independently of the network.
- [ ] Egress mode is explicitly selected: direct, private ranges, or all traffic through VPC.
- [ ] NAT/proxy has static IPs if partners require allowlisting.
- [ ] NAT is not mistaken for a firewall; domain allowlists are enforced at the proper layer.
- [ ] Both IPv4 and IPv6 are accounted for.
- [ ] Runtime service account has least privilege.
- [ ] HTTP clients have connect/request timeouts and bounded connection pools.
- [ ] SSRF protections exist if functions call user-supplied URLs.
- [ ] Flow logs, firewall/NAT/DNS logs, and appropriate application metrics are enabled.
- [ ] Tested at scale, during endpoint/NAT failures, and during DNS changes.
- [ ] Plans exist for HA, capacity, and periodic rule reviews.

## 15. Self-Check

**Question 1.** How do private ingress and private egress differ?

**Suggested Answer:** Private ingress restricts which sources can invoke the function. Private egress allows the function to initiate connections to resources in a private network. Configuring one direction does not automatically secure the other.

**Question 2.** Why does a Lambda attached to a VPC still need NAT when calling the public internet?

**Suggested Answer:** A Lambda in a private subnet can reach internal resources, yet does not automatically get a public IP or an internet route. It needs a route through a NAT Gateway or a properly designed egress path.

**Question 3.** Can a NAT Gateway block all domains except an allowlist?

**Suggested Answer:** NAT mainly performs address translation and provides an outbound path; it is not an HTTP-hostname-aware firewall. You need an FQDN-capable firewall, an egress proxy, or an appropriate destination control mechanism.

**Question 4.** Why does a private endpoint still need IAM and TLS?

**Suggested Answer:** A private endpoint restricts the network path, yet does not define what the caller is allowed to do and does not guarantee end-to-end encryption on its own. IAM/authorization controls identity and permissions; TLS protects data in transit.

**Question 5.** Why can private DNS cause a function to connect to the wrong endpoint?

**Suggested Answer:** The private zone may not be associated with the VPC, the hostname may resolve to a public IP, or resolvers/caches may return stale entries. Test DNS directly from the actual network/runtime that holds the connection path.

**Scenario Exercise:** A Java order-processing function needs to read a private Cloud SQL/RDS database, fetch a secret, and then call a partner API that accepts only allowlisted IPs. The company requires all internet egress to be logged and only the partner domain to be permitted. Design ingress, private egress, private endpoints, NAT/static IP, firewall/proxy, IAM, and DNS. Describe how to implement this for AWS Lambda and Google Cloud Run functions, along with the tests to execute.

**Hint:** Keep the database private and place the function in a VPC/VPC connector or appropriate Direct VPC egress. Use an interface endpoint for Secrets Manager on AWS or private access/PSC for the corresponding Google Cloud service. Route internet traffic through an egress firewall/proxy and NAT with static IPs; register all HA IPs with the partner. NAT does not replace domain filtering, so use a proxy or FQDN-policy firewall. Grant the runtime identity permissions to read only the specific secret and database; restrict callers with private ingress/IAM. Test DNS, routes, firewalls, endpoint policies, actual source IP, TLS, redirects, retries, and behavior when NAT/proxy is unavailable.

## Conclusion

Network design for serverless requires separating ingress, egress, and access permissions. Private endpoints paired with VPC/VNet integration let functions reach databases and managed services without public exposure. NAT provides an outbound path and stable source IPs, while firewalls/proxies enforce destination policies and logging. Private DNS, routes, security groups, IAM, TLS, and capacity must all be verified together. When deploying on AWS Lambda, Google Cloud Run functions, or Azure Functions, select the provider's appropriate networking mechanism, restrict egress to actual needs, and test at near-production concurrency.
