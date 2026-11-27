# Private Endpoints, Private DNS, and Network Paths to Services

A Spring Boot application may call APIs over HTTPS properly and still fail data protection requirements if traffic unexpectedly traverses the public network. A **private endpoint** brings a service access point into the workload's private network; **private DNS** causes the service hostname to resolve to a private address; and **routing and firewalls** determine whether packets can reach the destination.

All three layers must work together. Simply creating a private endpoint is not enough: the application must sit in a network with a route to the endpoint, DNS must return the right private IP, routes/NSGs/security groups/firewalls must permit the connection, and the service must accept the endpoint. Once connected, TLS and application authentication continue to operate just as before.

This lesson belongs to the **Data Protection** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module practices integrating Spring Boot with managed services from AWS, Azure, and Google Cloud through their respective libraries, covering identity/permissions, storage, messaging, data, secret protection, testing, and provider comparisons. The focus of this lesson is designing private access paths from workloads to services, understanding private DNS, and verifying connectivity from the actual runtime environment.

## 1. Objectives and Real-World Scenario

Suppose `order-service` runs on Kubernetes in a private network and needs to:

- Read configuration from Azure App Configuration.
- Retrieve secrets from Azure Key Vault.
- Read objects from Amazon S3 in an AWS workload.
- Call Google Cloud Storage or an internal API published via Private Service Connect.
- Avoid sending service traffic over the public internet per organizational policy.

After this lesson, you will be able to:

1. Distinguish a private endpoint from a service endpoint, NAT gateway, VPN, and public endpoint.
2. Describe the traffic path from a pod/VM to a service's private IP via DNS, routing, and firewalls.
3. Configure Azure Private Link/Private Endpoint and private DNS zones.
4. Distinguish an AWS interface VPC endpoint (PrivateLink) from a gateway endpoint, especially for S3.
5. Explain Google Cloud Private Service Connect (PSC) endpoints, backends, and DNS.
6. Configure custom DNS, hybrid DNS, and verify resolution from the workload.
7. Preserve hostname/TLS verification when traffic goes through a private IP.
8. Test DNS, TCP, TLS, and authorization, and troubleshoot errors layer by layer.

~~~mermaid
flowchart LR
    A["Spring Boot pod / VM"] --> B["DNS resolver"]
    B --> C["Service FQDN"]
    C --> D["Private DNS record"]
    D --> E["Private endpoint IP"]
    E --> F["Route + firewall / security group"]
    F --> G["Private Link / PrivateLink / PSC"]
    G --> H["Managed service"]
    H --> I["TLS + authentication + authorization"]
~~~

**Key principle:** A private endpoint solves the **network path**. It does not replace TLS, Microsoft Entra ID, AWS IAM, Google Cloud IAM, or service-level authorization.

## 2. Distinguishing Network Concepts

| Concept | Function | Example |
| --- | --- | --- |
| **Public endpoint** | Hostname/IP accessing a service over the public network plane | `vault-name.vault.azure.net` resolves to a public IP from external networks |
| **Private endpoint** | Private network interface/IP for connecting to a service over private link | Azure Private Endpoint, AWS interface VPC endpoint, GCP PSC endpoint |
| **Private DNS** | Resolves a hostname to a private IP within linked networks | `privatelink.vaultcore.azure.net` |
| **Service endpoint (Azure)** | Extends subnet identity to an Azure service over the backbone; the service keeps its public endpoint | Azure Storage service endpoint |
| **Gateway endpoint (AWS)** | Adds a route to an AWS service via a route table without creating an ENI | S3/DynamoDB gateway endpoint |
| **NAT gateway** | Allows private subnet workloads to make outbound connections to public destinations via NAT | Downloading packages or calling public APIs |
| **VPN / ExpressRoute / Direct Connect / Cloud Interconnect** | Private network connectivity between cloud and corporate/on-premises networks | Hybrid connectivity |
| **Private Service Connect (GCP)** | Private endpoints/backends for consumers to access Google APIs or published services | PSC endpoint to a service attachment |

### 2.1. A private endpoint does not mean public access is disabled

Creating a private endpoint typically adds a private access path. Whether the public endpoint remains allowed depends on the service's network access configuration:

- For Azure App Configuration, service documentation states that once a private endpoint is added, data requests over public networks are denied by default; always verify the actual network setting.
- For Azure Key Vault, you must configure Public network access = Disabled if policy requires private-endpoint-only access.
- For AWS/GCP, a private endpoint does not automatically eliminate all other public paths; IAM, endpoint policies, service firewalls, and DNS/routing must be configured according to your goal.

Never conclude "because a private endpoint exists, data cannot be accessed over the internet." Inspect **public network access**, firewalls, and the resource's own policies.

### 2.2. A private endpoint does not replace data permissions

A request arriving at a private IP can still receive 401/403 if the identity lacks permissions:

- Azure: Entra ID token + appropriate Azure RBAC/data-plane role or access policy.
- AWS: IAM role/policy, resource policy, endpoint policy, and VPC endpoint conditions if present.
- Google Cloud: service account/workload identity + IAM role; PSC does not automatically grant bucket/API read permissions.

The private network path and authorization are two independent layers. If DNS and TCP both succeed but the service returns 403, investigate permissions before changing DNS.

## 3. Path of a Request from Spring Boot

Suppose the application uses an SDK to call the Azure Key Vault FQDN `demo-checkout-kv.vault.azure.net`:

1. Spring Cloud Azure/Azure SDK obtains the endpoint hostname from configuration.
2. The JVM queries the container/VM environment's DNS resolver.
3. DNS returns a CNAME and an A record from the private DNS zone, ultimately yielding the private IP of the private endpoint.
4. TCP opens a connection to the private IP on port 443.
5. NSGs, routes, firewalls, and the network interface allow the traffic.
6. Private Link forwards the request to the Key Vault service.
7. TLS verifies the certificate against the original hostname `demo-checkout-kv.vault.azure.net`.
8. The SDK sends a bearer token; Key Vault checks data-plane permissions.
9. The secret response returns to the application.

~~~mermaid
sequenceDiagram
    participant App as Spring Boot
    participant DNS as Private DNS resolver
    participant PE as Private endpoint IP
    participant FW as NSG / Firewall / Route
    participant Svc as Managed service
    App->>DNS: Resolve vault-name.vault.azure.net
    DNS-->>App: CNAME + private A record
    App->>PE: TCP 443
    PE->>FW: Check network path
    FW->>Svc: Private Link
    Svc-->>App: TLS response + HTTP status
    Note over App,Svc: TLS hostname and IAM/RBAC are still verified
~~~

If a step fails, diagnose the exact layer:

- DNS returns a public IP: check private DNS/links/forwarding configuration.
- DNS returns a private IP but times out: check routes, NSGs, firewalls, subnets, or endpoint state.
- TCP succeeds but TLS fails: check certificate chain, hostname, or proxy/TLS inspection.
- TLS succeeds but 403: check IAM/RBAC or service policies.
- 404: check resource, subresource, hostname, or object/secret name.

## 4. Private DNS: The Most Common Source of Failure

### 4.1. The FQDN remains the standard service name

The application should continue calling the service's official hostname:

~~~text
https://demo-checkout-kv.vault.azure.net
https://demo-checkout-config.azconfig.io
https://s3.us-east-1.amazonaws.com
https://storage.googleapis.com
~~~

Private DNS makes that **same hostname** resolve to a private address when queried from configured networks. Do not modify source code to replace the hostname with a private IP, and do not arbitrarily use internal `privatelink` hostnames directly.

Reasons:

- TLS certificates are issued for the standard service hostname.
- SDKs often build the `Host` header, SNI, signing scope, or endpoint metadata from the official hostname.
- DNS is the layer that translates hostnames to IPs; it lets you keep the application and standard endpoints unchanged.

**Exception:** some PSC architectures or privately published services may require a custom endpoint/domain. In that case, configure the client endpoint and ensure `Host`/SNI match the service documentation.

### 4.2. DNS resolution inside a private network

A DNS answer may traverse multiple aliases:

~~~text
demo-checkout-kv.vault.azure.net
       |
       | CNAME
       v
demo-checkout-kv.privatelink.vaultcore.azure.net
       |
       | A record in private DNS zone
       v
10.20.4.7
~~~

From a workload inside a VNet linked to the private DNS zone, the standard hostname resolves to a private IP. From a machine outside the VNet, public DNS may return a public ingress IP. That does not prove the private endpoint does not exist; it only shows that the resolver being used lacks the private zone view.

### 4.3. Split-horizon DNS

**Split-horizon DNS** returns different answers depending on where the query originates:

| Query origin | Expected result |
| --- | --- |
| VM/pod in a VNet linked to the private zone | Private endpoint IP |
| On-premises via proper DNS forwarding | Private endpoint IP |
| Laptop outside VPN/VNet | Public DNS answer or no private route |
| Workload in another VNet without link/forwarding | May receive public IP |

Therefore, `nslookup` from a developer laptop is not enough to prove that Spring Boot in AKS/App Service/EC2/GCE has the right network path. Test **directly inside the pod/VM or an equivalent execution environment**.

### 4.4. Custom DNS and hybrid DNS

If a VNet uses a custom DNS server, private DNS zones may not be queried automatically by the resolver. Forwarding must be designed:

- Internal DNS servers forward the appropriate `privatelink.*` zones to Azure DNS Private Resolver or the configured resolver.
- In AWS, Route 53 Resolver inbound/outbound endpoints and Resolver rules integrate DNS between VPCs and on-premises.
- In GCP, Cloud DNS inbound server policies/forwarding and DNS peering support hybrid name resolution.
- Do not create wildcard forwarding broader than necessary if it conflicts with existing internal zones.

Check both the **DNS query path** and the **network path** to the resolver. A valid private zone that is never queried by the workload's subnet still has no effect.

## 5. Azure Private Link and Private Endpoints

### 5.1. How it works

An Azure Private Endpoint is a network interface in a VNet subnet that receives a private IP and connects to a **Private Link resource** and target subresource. Traffic from workloads to this IP travels over Azure Private Link to the service.

General steps:

1. Select the Azure resource to access.
2. Choose the exact **subresource** (e.g., Blob, File, Key Vault `vault`, App Configuration `configurationStores`).
3. Select the VNet/subnet where the private endpoint is created.
4. Wait for the connection state to become **Approved**.
5. Create/link the private DNS zone and verify the A record.
6. Check NSGs/UDRs/firewalls and hybrid paths if applicable.
7. After testing succeeds, configure the service to block public access if the goal is private-only.

The connection may be Pending when manual approval by the resource owner is required. An endpoint in Pending/Rejected/Disconnected state is not considered an active connection.

### 5.2. Common private DNS zones

| Azure service | Private DNS zone |
| --- | --- |
| App Configuration | `privatelink.azconfig.io` |
| Key Vault | `privatelink.vaultcore.azure.net` |
| Storage Blob | `privatelink.blob.core.windows.net` |
| Storage File | `privatelink.file.core.windows.net` |
| Azure SQL Database | `privatelink.database.windows.net` |
| Cosmos DB SQL API | `privatelink.documents.azure.com` |

Zone names depend on the service, subresource, and cloud environment. For Azure Government/China or sovereign clouds, suffixes differ from public Azure; always consult the official Private Endpoint DNS table for the target cloud.

### 5.3. App Configuration over private endpoint

For Azure App Configuration:

- Create a private endpoint targeting the store with subresource `configurationStores`.
- The standard public Azure private DNS zone is `privatelink.azconfig.io`.
- The application still uses the standard endpoint, e.g., `https://demo-checkout-config.azconfig.io`.
- Do not configure the Spring Cloud Azure endpoint to a hostname with a `privatelink` subdomain.
- When private DNS works, the standard hostname resolves via an alias to the private endpoint IP.
- With geo-replication, each replica has its own endpoint/DNS record; consider a private endpoint per region to maintain availability during regional outages.

Example Spring YAML still uses the normal endpoint:

~~~yaml
spring:
  config:
    import: azureAppConfiguration
  cloud:
    azure:
      appconfiguration:
        stores:
          - endpoint: "${AZURE_APPCONFIG_ENDPOINT}"
~~~

`AZURE_APPCONFIG_ENDPOINT` holds the standard FQDN of the store. Do not put a private IP into the `endpoint` property. DNS and networking are handled by the platform.

### 5.4. Key Vault over private endpoint

For Azure Key Vault:

- The standard public Azure private DNS zone is `privatelink.vaultcore.azure.net`.
- The private endpoint must be in the Approved state.
- Workloads use the standard hostname `https://<vault-name>.vault.azure.net/`.
- The private DNS zone must be linked to the workload's VNet or have matching forwarding.
- You can set **Public network access = Disabled** after verifying that both workloads and administrative pipelines can reach it over the private path.

Example Spring Cloud Azure configuration:

~~~yaml
spring:
  cloud:
    azure:
      keyvault:
        secret:
          property-sources:
            - name: checkout-vault
              endpoint: "${AZURE_KEYVAULT_ENDPOINT}"
              secret-keys:
                - payments-api-token
~~~

The `endpoint` property uses the standard FQDN. Private link does not alter `secret-keys`, Managed Identity, or the Key Vault Secrets User role. The private endpoint only provides the network path to the service.

### 5.5. Public DNS may still respond

A common misconception: the Key Vault FQDN can still resolve in public DNS and show a `privatelink` CNAME even after public network access is disabled. A DNS answer does not mean public requests are permitted. When public access is Disabled, the service rejects data-plane requests arriving through public ingress; only the private DNS overlay inside the VNet returns the private endpoint IP.

Therefore, **do not treat public DNS resolution as proof that public access is still open**. Check the network settings and test connectivity from an external network that has no private route.

### 5.6. Azure service endpoint vs. private endpoint

| Criterion | Service endpoint | Private endpoint |
| --- | --- | --- |
| Destination address in VNet | Service still has a public service IP | Private IP of a NIC in the subnet |
| DNS | Typically still uses public service FQDN/public IP | Private DNS overrides to a private IP |
| Availability | Selected Azure services | Services supporting Private Link |
| Restriction mechanism | Service firewall can allow subnet identity | Private Link connection + network controls |
| Traffic path | Azure backbone after leaving subnet, still targets public service endpoint | Private Link to the specific resource |
| Hybrid DNS integration | Less complex | Requires proper private DNS/forwarding |

App Configuration supports private endpoints; its documentation explicitly notes that it **does not support service endpoints**. Do not apply Storage service endpoint instructions to App Configuration.

## 6. AWS PrivateLink and VPC Endpoints

### 6.1. Interface VPC endpoint

AWS PrivateLink lets VPC consumers access services through an interface VPC endpoint. AWS creates an **Elastic Network Interface (ENI)** in each selected subnet and assigns a private IP. Traffic to the service resolves via DNS to the ENI's private IP and flows over PrivateLink.

Components:

- Workload's VPC and subnets.
- Interface endpoint tied to the service name and region.
- Endpoint ENIs in one or more Availability Zones.
- Security group attached to the endpoint ENI allowing inbound from workloads (typically TCP 443).
- Appropriate Network ACLs and routes.
- Private DNS if using the default service hostname.

### 6.2. Private DNS for interface endpoints

When Private DNS is enabled and the VPC has DNS resolution/hostnames enabled, AWS creates a hidden private hosted zone so the service's default regional hostname resolves to the private IP of the endpoint ENI.

For example, the application still calls the AWS SDK with the regional service endpoint:

~~~java
S3Client s3 = S3Client.builder()
        .region(Region.US_EAST_1)
        .build();
~~~

If the service/endpoint supports private DNS and is configured properly, the SDK uses the default hostname; DNS inside the VPC returns the private endpoint IP. There is no need to hardcode endpoint ENI IPs in Java.

If private DNS is disabled, you may have to use the endpoint-specific DNS name provided by AWS. This can require configuring a custom endpoint in the SDK and verifying hostname/signing behavior.

### 6.3. S3: gateway endpoint vs. interface endpoint

Amazon S3 offers both VPC endpoint types:

| Criterion | S3 Gateway endpoint | S3 Interface endpoint |
| --- | --- | --- |
| Type | Route table target | ENI private IP via AWS PrivateLink |
| DNS | Uses standard S3 DNS name; route table directs traffic via gateway endpoint | Has endpoint-specific DNS; private DNS can be enabled |
| On-premises | Does not support direct access from on-prem via gateway endpoint | Accessible via Direct Connect/Site-to-Site VPN by design |
| VPC peering/Transit Gateway | Gateway endpoints are not shared across peering/TGW in that way | Interface endpoints support broader network connectivity options subject to service rules |
| Endpoint cost | No gateway endpoint charge | Hourly and data processing charges apply |
| Configuration | Route table and endpoint policy | Security group, subnet, endpoint policy, and DNS |

If only workloads inside the VPC need S3, a gateway endpoint is usually simpler and has no endpoint fee. If access from on-premises or other VPCs is needed for supported scenarios, evaluate an interface endpoint.

### 6.4. Security groups and endpoint policies

AWS PrivateLink does not bypass network controls:

- The endpoint ENI's security group must allow inbound traffic from appropriate sources, such as TCP 443 from the workload security group.
- Network ACLs must allow required bidirectional traffic.
- Endpoint policies can restrict which principals/actions/resources may be invoked through the endpoint, but they do not replace IAM policies or resource policies.
- For interface endpoints, select subnets across multiple AZs for fault tolerance.
- Monitor endpoint state, ENIs, DNS entries, and quotas.

Do not open inbound TCP 443 from an entire CIDR if only a specific group of workloads needs access. Use security group references or narrow CIDRs according to your architecture.

## 7. Google Cloud Private Service Connect

### 7.1. What is a PSC endpoint?

**Private Service Connect (PSC)** enables a consumer VPC to access Google APIs or services published in another VPC via an internal IP address in the consumer network. An endpoint is typically created with a forwarding rule pointing to:

- A service producer's service attachment.
- A global Google APIs bundle.
- A supported regional or multi-regional Google API.

For privately published services, the producer can place the service behind a load balancer and publish a service attachment. The consumer creates a PSC endpoint in its own VPC and connects using the internal IP.

### 7.2. Endpoint, backend, and interface differences

| PSC component | Usage direction |
| --- | --- |
| **Endpoint** | Consumer uses a forwarding rule/internal IP for Layer 4 connectivity to the service |
| **Backend** | Consumer places its own load balancer in front of PSC for custom URLs, advanced traffic management, or failover |
| **Interface** | Allows a producer network to initiate connections into a consumer network via a network attachment; different communication model from an endpoint |

For a Spring Boot client calling a published service, a PSC endpoint is usually the starting point. If you need a consumer-side load balancer, custom certificates/domains, or complex failover, evaluate a PSC backend.

### 7.3. DNS for PSC

An endpoint has an internal IP. Clients can call a hostname mapped by DNS to that IP:

~~~text
orders-api.internal.example.com  ->  10.40.2.15
~~~

For a service attachment with a configured DNS domain, Google Cloud/Service Directory can create DNS entries for the endpoint. For Google APIs, PSC can provide names of the form:

~~~text
storage-<endpoint-name>.p.googleapis.com
compute-<endpoint-name>.p.googleapis.com
~~~

The Java client must support custom endpoints if using `p.googleapis.com` names. If the client cannot configure a custom endpoint or the API lacks automatic records, you can create a private DNS zone for the default service name such as `googleapis.com` and point domains/A records to the endpoint IP per Google's guidance.

**Keep the Host header and SNI correct:** with custom libraries, Google requires the `Host` header/SNI to be a valid service hostname, such as `storage.googleapis.com` or `SERVICE-ENDPOINT.p.googleapis.com`. Do not replace the URL with a raw IP if doing so breaks TLS hostname validation and API routing.

### 7.4. Firewalls and regions

- The consumer VPC egress firewall must allow traffic to the PSC endpoint's internal IP.
- Endpoints and published services have regional requirements; verify same-region constraints and global access options where available.
- For hybrid networks over Cloud VPN/Cloud Interconnect, advertise endpoint IP routes and configure DNS forwarding to private zones.
- A PSC endpoint does not grant IAM permissions; the application's service account still needs roles to access APIs/resources.
- Check the consumer accept list/service attachment approval if the producer requires explicit approval.

### 7.5. PSC vs. Private Google Access

These two concepts are not the same:

- **Private Google Access** lets VMs without external IPs reach certain Google APIs over Google's infrastructure.
- **Private Service Connect for Google APIs** provides consumer-controlled internal endpoint IPs and DNS that can steer API traffic to those endpoints.
- **PSC published services** let a consumer VPC access services published by a producer.

Choose based on IP, DNS, endpoint control, routing, and service model requirements. Do not lump all approaches together as "private endpoints" and ignore their differences.

## 8. Comparing the Three Platforms

| Aspect | Azure Private Link | AWS PrivateLink | Google Cloud PSC |
| --- | --- | --- | --- |
| Access point | Private Endpoint/NIC in a subnet | Interface VPC endpoint/ENI | Forwarding rule with internal IP (endpoint) |
| DNS | Private DNS zone and VNet link | Hidden AWS-managed private hosted zone or Route 53 Resolver | Cloud DNS/Service Directory or private zone depending on use case |
| Target services | Azure PaaS and supported published services | AWS services and published endpoint services | Google APIs and service attachments |
| Network policy | NSGs, UDRs, firewalls, endpoint approval | Security groups, NACLs, routes, endpoint policies | VPC egress firewalls, routes, service attachment accept lists |
| Hybrid | VPN Gateway, ExpressRoute, DNS Private Resolver | Direct Connect, Site-to-Site VPN, Route 53 Resolver | Cloud VPN, Cloud Interconnect, Cloud DNS forwarding |
| Application | Usually keeps standard service FQDN | Private DNS allows keeping regional service hostnames | May need custom endpoint/DNS depending on PSC API/service |
| Identity | Entra ID + Azure RBAC | IAM role/policy | Service account/workload identity + IAM |

**Key difference to remember:** Azure and AWS typically provide private DNS mechanisms so clients continue using standard service hostnames; Google PSC for Google APIs may use `p.googleapis.com` names or service-specific DNS overrides. Always check the endpoint requirements of the SDK you use.

## 9. Spring Boot Integration: Where Is Networking Configured?

Spring Boot does not have a single universal property to enable private links across all clouds. Private endpoints are provisioned and configured in the **network/control plane**; the application uses endpoint hostnames and SDK clients as usual.

### 9.1. Azure SDK/Spring Cloud Azure

App Configuration and Key Vault example:

~~~yaml
spring:
  config:
    import: azureAppConfiguration
  cloud:
    azure:
      appconfiguration:
        stores:
          - endpoint: "${AZURE_APPCONFIG_ENDPOINT}"
      keyvault:
        secret:
          property-sources:
            - name: checkout-vault
              endpoint: "${AZURE_KEYVAULT_ENDPOINT}"
              secret-keys:
                - payments-api-token
~~~

The environment variables must contain the standard FQDNs:

~~~text
AZURE_APPCONFIG_ENDPOINT=https://demo-checkout-config.azconfig.io
AZURE_KEYVAULT_ENDPOINT=https://demo-checkout-kv.vault.azure.net/
~~~

The private DNS zone maps both FQDNs to private IPs from the workload's VNet. No Spring dependency changes are needed merely to use Private Endpoints. Credentials/Managed Identity and Azure RBAC must still be configured as normal.

### 9.2. AWS SDK for Java 2.x

For an AWS service with an interface endpoint and Private DNS enabled, keep the default region and service client:

~~~java
S3Client s3 = S3Client.builder()
        .region(Region.US_EAST_1)
        .credentialsProvider(DefaultCredentialsProvider.create())
        .build();
~~~

The SDK uses the regional endpoint, and the resolver inside the VPC returns the private endpoint IP. For an S3 gateway endpoint, the route table determines the path; SDK code still uses the standard S3 hostname.

If you must use endpoint-specific DNS, the SDK supports endpoint overrides:

~~~java
S3Client s3 = S3Client.builder()
        .region(Region.US_EAST_1)
        .endpointOverride(URI.create("https://vpce-example.s3.us-east-1.vpce.amazonaws.com"))
        .build();
~~~

Only use `endpointOverride` when the architecture requires an endpoint-specific hostname and the endpoint/service supports it. Never substitute a raw private IP because TLS and AWS request signing depend on hostname/region.

### 9.3. Google Cloud Java client

For clients that support custom endpoints, a PSC `p.googleapis.com` endpoint can be specified via settings:

~~~java
Storage storage = StorageOptions.newBuilder()
        .setProjectId(projectId)
        .setHost("https://storage-checkout.p.googleapis.com")
        .build()
        .getService();
~~~

Exact APIs may vary by Google Cloud Java library/version. Check the builder of the client you are using and verify that DNS has matching records, `Host`/SNI are valid, and the service account has IAM permissions. If using private DNS to override `storage.googleapis.com`, the client can keep calling the default endpoint without a custom host; pick one approach and verify DNS from the workload.

## 10. Designing DNS for Multi-Network VNets/VPCs

A production topology often includes:

- A Hub VNet/VPC hosting DNS resolvers/firewalls.
- Spoke VNets/VPCs running applications.
- Private endpoints located in a central or service subnet.
- On-premises connected over VPN/ExpressRoute/Direct Connect/Cloud Interconnect.

### 10.1. Hub-and-spoke

~~~mermaid
flowchart TD
    OnPrem["On-prem DNS / workloads"] --> VPN["VPN / dedicated link"]
    VPN --> Hub["Hub VNet/VPC"]
    Hub --> DNS["Central DNS resolver"]
    Hub --> Spoke1["Spoke: Spring Boot"]
    Hub --> PE["Private endpoint subnet"]
    Spoke1 --> DNS
    Spoke1 --> PE
    PE --> PaaS["Managed service"]
~~~

Questions you must answer:

1. Does the spoke have a route to the private endpoint IP?
2. Can the spoke query the private DNS zone?
3. Is the private DNS zone linked to the right VNet?
4. If DNS is centralized in the hub, does the resolver have forwarding rules for private zones?
5. Does on-premises have a route to the endpoint IP and can it query the private zone?
6. Do NSGs/firewalls allow TCP 443 from the actual source?

### 10.2. Peering does not automatically solve all DNS issues

VNet/VPC peering provides network connectivity subject to platform limits, but does not always share private DNS zones automatically. In Azure, link zones to VNets or configure DNS forwarding. In AWS, private hosted zones need proper associations/Resolver rules. In Google Cloud, Cloud DNS private zones need proper network bindings/forwarding.

Never treat "two VNets are peered" as proof that hostnames will resolve properly.

### 10.3. Hybrid DNS

When on-premises needs to call a service via a private endpoint:

- A VPN/ExpressRoute/Direct Connect/Interconnect route exists to the network holding the endpoint.
- On-prem DNS forwards private zones to the corresponding cloud resolver.
- The cloud resolver receives the query and returns the private endpoint IP.
- On-prem and cloud firewalls allow both outbound and return traffic.
- Verify MTU, routing symmetry, and NAT if present.

If DNS returns a private IP but packets lack a return route, TCP still times out. If routing works but DNS returns a public IP, traffic may take the wrong path or be rejected by the service.

## 11. Verifying from the Actual Runtime Environment

Do not test only from a developer workstation. Run commands from a **pod/VM/container sharing the same subnet, DNS, and routes as Spring Boot**.

### 11.1. Checking DNS

Linux:

~~~bash
getent hosts demo-checkout-kv.vault.azure.net
nslookup demo-checkout-kv.vault.azure.net
dig +short demo-checkout-kv.vault.azure.net
~~~

Windows:

~~~powershell
Resolve-DnsName demo-checkout-kv.vault.azure.net
nslookup demo-checkout-kv.vault.azure.net
~~~

Expected result inside a VNet with a private endpoint: the hostname ultimately resolves to a private IP in the VNet's address space. Do not look only at the CNAME line; inspect the final A/AAAA record as well.

### 11.2. Checking TCP 443

Linux:

~~~bash
nc -vz demo-checkout-kv.vault.azure.net 443
~~~

Windows PowerShell:

~~~powershell
Test-NetConnection demo-checkout-kv.vault.azure.net -Port 443
~~~

If DNS returns a private IP but TCP fails, check routes, NSGs, UDRs, firewalls, NACLs, endpoint connection state, and security groups. Do not switch the hostname to a public IP "just for a quick test" in a private-only environment.

### 11.3. Checking TLS while preserving the standard hostname

~~~bash
openssl s_client \
  -connect demo-checkout-kv.vault.azure.net:443 \
  -servername demo-checkout-kv.vault.azure.net \
  -verify_return_error
~~~

The `-connect` option uses the standard hostname; the resolver selects the IP according to current DNS. The `-servername` option sends the exact FQDN in SNI. Do not connect using the raw private IP when testing the service's hostname certificate.

### 11.4. Testing HTTP without leaking secrets

You can issue an unauthenticated request or hit an appropriate health endpoint to verify TLS/networking. If the service returns 401/403, that can prove TCP/TLS reached the service while authorization is not yet satisfied. Never pass bearer tokens, API keys, or secrets in `curl` commands that may remain in shell history.

### 11.5. Checking inside Java

You can log non-sensitive metadata:

~~~java
InetAddress[] addresses =
        InetAddress.getAllByName("demo-checkout-kv.vault.azure.net");

for (InetAddress address : addresses) {
    // Log the IP for diagnostics; never log tokens/secrets.
    System.out.println("Resolved address: " + address.getHostAddress());
}
~~~

This snippet only checks DNS resolution used by the JVM. It does not prove TLS, authorization, or that the SDK's requests use the same HTTP transport. Integration tests must invoke the real client from an equivalent runtime.

## 12. Integration Testing Private Networking

### 12.1. Layer-by-layer test matrix

| Layer | Test | Expected result |
| --- | --- | --- |
| DNS | Resolve standard FQDN from pod | Private endpoint IP |
| Hybrid DNS | Resolve from on-prem | Private IP via forwarding |
| TCP | Connect to port 443 | TCP handshake succeeds |
| TLS | Verify CA + hostname | Valid certificate |
| Endpoint | Connection state | Approved/Available |
| Network policy | NSG/SG/NACL/firewall | Only required sources/ports permitted |
| Authentication | Token/credential | Correct principal |
| Authorization | Read test resource | Allowed per IAM/RBAC |
| Public isolation | Test from external network | Denied when public access is disabled |
| Application | Spring SDK request | Reads/writes test data per granted permissions |

### 12.2. Integration testing with Azure

Using a dev App Configuration/Key Vault:

1. Create private endpoints for the store and vault.
2. Link private DNS zones `privatelink.azconfig.io` and `privatelink.vaultcore.azure.net` to the workload VNet.
3. Ensure the App Configuration and Key Vault endpoints remain standard FQDNs.
4. Deploy a test pod into the target VNet/subnet or an environment with VNet integration.
5. Verify DNS returns private IPs and TCP 443 succeeds.
6. Run Spring Boot with Managed Identity and `App Configuration Data Reader`/`Key Vault Secrets User` roles.
7. Verify requests succeed; then verify public access according to policy.
8. Remove permissions or block a route on test resources to confirm tests distinguish 403 from timeouts.

### 12.3. Integration testing with AWS

1. Create an interface VPC endpoint for the target AWS service; select subnets in at least two AZs if HA is required.
2. Enable Private DNS when using standard service hostnames and verify the VPC has DNS hostnames/resolution enabled.
3. Allow inbound 443 on the endpoint security group from the workload security group.
4. For S3, choose a gateway or interface endpoint based on client location and cost.
5. Run AWS SDK Java tests from EC2/EKS/ECS inside the VPC.
6. Verify endpoint ENI/DNS, IAM role, bucket policy, and endpoint policy.
7. Test from a network outside the VPC to verify access restrictions match design.

### 12.4. Integration testing with Google Cloud

1. Create a PSC endpoint pointing to the appropriate service attachment or Google API bundle.
2. Choose an internal IP and region according to service requirements.
3. Create/verify the Cloud DNS zone and records.
4. Ensure VPC egress firewalls allow traffic to the PSC endpoint IP.
5. Configure the Google Cloud Java client endpoint if using `p.googleapis.com`.
6. Test DNS, Host/SNI, IAM service account, and real requests.
7. For hybrid setups, verify routes advertised over Cloud VPN/Interconnect and DNS forwarding.

### 12.5. Tests that must not be skipped

- Endpoint in Pending or Rejected state.
- Private DNS zone exists but is not linked to the VNet.
- Custom DNS does not forward `privatelink` zones.
- Hostname returns a private IP but NSG/SG blocks port 443.
- TLS hostname mismatch because code calls a raw private IP.
- IAM/RBAC works in dev but is missing on the production identity.
- An AZ/region loses connectivity.
- Public endpoint unintentionally left open.
- SDK uses a different endpoint override than the one tested.

## 13. Troubleshooting by Symptom

| Symptom | Likely failing layer | Remediation |
| --- | --- | --- |
| DNS returns a public IP inside the VNet | Private DNS zone missing, unlinked, or custom DNS not forwarding | Check zone, A record, VNet link, and resolver |
| DNS returns NXDOMAIN | Wrong hostname, zone shadowing, or missing record | Verify FQDN and zone authority |
| DNS returns private IP but times out | Route/NSG/SG/NACL/firewall or endpoint not Approved | Check TCP 443, effective routes, and endpoint state |
| TCP succeeds, TLS fails | Wrong hostname/SNI, trust chain, or TLS inspection | Use standard FQDN and inspect the certificate |
| TLS succeeds, HTTP 403 | RBAC/IAM, endpoint policy, or service firewall | Check principal and data-plane permissions |
| HTTP 404 | Wrong resource path, service subresource, or endpoint | Verify store/vault/bucket name and endpoint target |
| One pod works, another fails | Different subnet, node pool, DNS policy, or network policy | Compare routes, DNS resolvers, and source IPs |
| VNet peering exists but private names fail to resolve | Private zone unlinked or DNS forwarding unconfigured | Configure zone associations/forwarding |
| On-prem resolves private IP but times out | Missing route, return path, firewall, or MTU | Check VPN/ExpressRoute/Direct Connect/Interconnect |
| App Configuration works but Key Vault fails | Separate private endpoints/DNS/firewalls per service | Check `privatelink.vaultcore.azure.net` zone and routes |
| AWS SDK bypasses endpoint | Private DNS disabled or different endpoint hostname used | Check endpoint DNS entries, private DNS, and region |
| GCP PSC endpoint has IP but requests fail to arrive | DNS/routes/egress firewall or service attachment acceptance | Check forwarding rule, firewall, region, and consumer accept list |

## 14. Security and Operations

### 14.1. Reducing the public attack surface

Once the private path is verified:

- Disable public network access on supporting resources per policy.
- Allow only required subnets/security groups.
- Use controlled private DNS and resolvers.
- Restrict permissions to create/modify endpoints and private DNS zones.
- Monitor changes to endpoints, DNS records, routes, and firewall rules.
- Never use a private endpoint as a substitute for IAM/RBAC or TLS.

In Azure, complete private DNS setup and workload testing before disabling public access to avoid locking out applications or management pipelines.

### 14.2. High availability

A private endpoint is part of the network path; account for failure domains:

- Azure: regional private endpoints, DNS records per replica, redundant VNet peering, and redundant resolvers.
- AWS: interface endpoint ENIs across multiple Availability Zones; never select only a single AZ for production services.
- Google Cloud: regional endpoints, global access where supported, PSC backends/load balancers, or service-appropriate failover.
- DNS: TTLs, resolver availability, JVM/OS caching, and propagation times.
- Application: bounded timeouts/retries, circuit breakers, and proper health checks.

Do not retry indefinitely on bad DNS or denied permissions. Retries cannot fix endpoint configuration or authorization errors.

### 14.3. Cost and limits

Private connectivity incurs costs and quotas:

- Azure Private Endpoints incur per-endpoint/region and data processing charges per current pricing.
- AWS interface endpoints bill hourly per AZ plus data processed; S3 gateway endpoints have no endpoint fee.
- GCP PSC pricing/quotas depend on endpoints, forwarding rules, load balancers, and traffic.

Account for endpoint counts, AZ/region counts, data volume, DNS resolvers, cross-region traffic, and hybrid links. Do not provision one endpoint per application without considering shared models, security boundaries, and blast radius.

### 14.4. Do not hardcode DNS or IPs in the application

Do not store private endpoint IPs in `application.yml`, Java code, or Config Server. IPs can change when endpoints are recreated or networks redeployed. Use standard service hostnames and let DNS manage the mapping.

If a service requires a custom endpoint such as certain GCP PSC API use cases, manage the hostname through environment configuration—never hardcode raw IPs.

## 15. Comprehensive Hands-On Exercise

An `order-service` deployed on AKS needs:

- `orders-config` from Azure App Configuration.
- `orders-kv` from Azure Key Vault.
- An S3 bucket from an integrated AWS system in a private VPC.
- A Google API over PSC from a workload running in GCP.
- On-premises networks also need access to internal APIs.

**Design requirements:**

1. Create separate Azure Private Endpoints for App Configuration and Key Vault; configure the right private DNS zones.
2. Keep Spring Cloud Azure endpoints as standard FQDNs; do not use `privatelink` hostnames.
3. Choose an AWS S3 gateway endpoint or interface endpoint based on workload location and on-prem/cross-VPC requirements.
4. Set up a GCP PSC endpoint and matching DNS records; verify `Host`/SNI if using a custom endpoint.
5. Design DNS forwarding from on-premises to cloud resolvers.
6. Write an NSG/SG/firewall/route checklist for TCP 443.
7. Verify TLS, Managed Identity/IAM, and real SDK requests from each runtime.
8. Disable public access after proving the private path works and prepare a rollback plan.

**Self-assessment questions:**

- Why can a private endpoint exist while the application still resolves a public IP?
- Why should standard hostnames be used instead of private IPs in `application.yml`?
- Which private DNS zone does an App Configuration private endpoint require?
- Why does Amazon S3 offer both a gateway endpoint and an interface endpoint?
- How do a PSC endpoint and a PSC backend differ?
- If DNS is right but TCP times out, which layer needs investigation?
- If TLS succeeds but returns 403, is that a DNS error or an authorization error?
- Why does creating a private endpoint not automatically prove that public access is disabled?

**Guided answers:** private DNS is not linked/forwarded or queries hit a different resolver; standard hostnames preserve TLS/SNI and SDK behavior; App Configuration uses `privatelink.azconfig.io`; S3 gateway uses route tables whereas interface uses ENIs/private IPs and supports certain hybrid use cases; PSC endpoint is an L4 forwarding rule while backend adds a load balancer; timeouts point to routing/firewalls/endpoints; 403 is authorization/policy; public access must be verified separately on the resource.

## 16. Official References

- [Microsoft Learn – What is a private endpoint?](https://learn.microsoft.com/en-us/azure/private-link/private-endpoint-overview): NIC/private IP, target subresources, approval, DNS, and network security.
- [Microsoft Learn – Azure Private Endpoint DNS configuration](https://learn.microsoft.com/en-us/azure/private-link/private-endpoint-dns): private DNS zones for each Azure service.
- [Microsoft Learn – Use private endpoints for Azure App Configuration](https://learn.microsoft.com/en-us/azure/azure-app-configuration/concept-private-endpoint): endpoints, DNS, public access, and geo-replication.
- [Microsoft Learn – Integrate Key Vault with Azure Private Link](https://learn.microsoft.com/en-us/azure/key-vault/general/private-link-service): private DNS zones, endpoint states, and Key Vault connection verification.
- [Microsoft Learn – DNS security and private name resolution](https://learn.microsoft.com/en-us/azure/networking/design-guide/dns-security): hybrid DNS, DNS Private Resolver, and hub-spoke.
- [AWS – Access AWS services through AWS PrivateLink](https://docs.aws.amazon.com/vpc/latest/privatelink/privatelink-access-aws-services.html): interface endpoints, DNS, and multi-AZ.
- [AWS – Create an interface VPC endpoint](https://docs.aws.amazon.com/vpc/latest/privatelink/create-interface-endpoint.html): subnets, ENIs, security groups, and NACLs.
- [AWS – Gateway endpoints for Amazon S3](https://docs.aws.amazon.com/vpc/latest/privatelink/vpc-endpoints-s3.html): comparing S3 gateway and interface endpoints.
- [Google Cloud – Private Service Connect overview](https://docs.cloud.google.com/vpc/docs/private-service-connect): endpoints, backends, interfaces, and Google APIs.
- [Google Cloud – Access published services through endpoints](https://docs.cloud.google.com/vpc/docs/configure-private-service-connect-services): endpoints, subnets, firewalls, regions, and hybrid access.
- [Google Cloud – Access global Google APIs through endpoints](https://docs.cloud.google.com/vpc/docs/configure-private-service-connect-apis): `p.googleapis.com` DNS, default hostnames, and Host/SNI.

**Remember:** A private connection only works when **the endpoint is approved, DNS resolves properly, routes/firewalls permit traffic, TLS verifies the hostname, and the identity has permissions**. In Spring Boot, keep the proper service endpoint hostnames and test from the actual runtime network to prove the connection path is genuinely private.
