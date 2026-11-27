# TLS Policies, mTLS, and Managing Trust Between Components

## Learning Objectives

In a distributed system, encrypting connections solves only part of the protection problem. A service needs to know which server it is talking to; in many internal flows, the server also needs to know precisely which workload is calling it. TLS provides an encrypted channel and server authentication. Mutual TLS (mTLS) extends that process by requiring both sides to prove their identities with digital certificates.

After this lesson, learners can:

- Distinguish TLS, server authentication, mTLS, and application-layer authorization.
- Read a certificate chain and explain the roles of root CA, intermediate CA, leaf certificate, trust store, and key store.
- Select TLS security policies based on security, compatibility, and compliance requirements.
- Design certificate lifecycles for public, partner-to-service, and service-to-service communication.
- Choose mTLS deployment approaches suited for Application Load Balancer, Network Load Balancer, API Gateway, or applications running on EC2, ECS, and EKS.
- Operate trust bundles, rotate CAs, revoke certificates, and troubleshoot handshake errors.

## 1. Context: Protecting the Request Path

Consider an e-commerce system with these components:

- Mobile apps and browsers calling public APIs.
- An API gateway or load balancer accepting external connections.
- A Checkout service calling Order, Inventory, and Payment.
- A shipping partner sending webhooks into the system.
- Workloads running on ECS, EKS, and EC2, potentially across multiple subnets or accounts.

Security groups, network ACLs, and route tables govern packet paths. They restrict sources and destinations, yet they do not prove workload-level identity. If two services reside in the same VPC, a security group permitting connectivity does not automatically guarantee a request came from the Checkout service.

TLS protects data on each connection. mTLS adds client-side identity authentication via certificates. Applications still require authorization to decide what actions an authenticated identity is permitted to perform.

| Question | Mechanism |
|---|---|
| Who can open a connection to port 443? | Security groups, network ACLs, firewalls, routing |
| Can data in transit be read or tampered with? | TLS and appropriate cipher/protocol settings |
| Is the client connecting to the right server? | Server certificate and hostname verification |
| Does the client or calling workload have a trusted identity? | Client certificate in mTLS |
| Is that identity allowed to read orders or issue refunds? | Authorization in the application or policy engine |

Do not conflate these questions into one. A successful mTLS connection can still carry an unauthorized request.

## 2. What Does TLS Protect?

TLS (Transport Layer Security) establishes a channel between two endpoints. During the handshake, both sides negotiate protocol version and cipher suite, establish session keys, and then protect data with authenticated encryption. Modern TLS provides three core properties:

1. **Confidentiality:** observers on the wire cannot read the payload.
2. **Integrity:** tampering with data in transit is detected.
3. **Authentication:** normally the client verifies the server's identity via certificate. With mTLS, the server also verifies the client.

TLS does not automatically encrypt data once it reaches the destination process. Nor does it protect a compromised endpoint, validate business correctness, or replace encryption at rest.

### 2.1. Server Authentication

When a browser visits `https://shop.example.com`, the server presents a certificate. The client verifies:

- The certificate is valid at the current time.
- The certificate is signed by a CA in the client's trust store via a valid signature chain.
- The domain accessed by the client matches a Subject Alternative Name (SAN) in the certificate.
- Algorithms, key sizes, and signatures meet client policy.
- Revocation checks performed by the client or environment, if configured and supported.

If the certificate names `shop.example.net` while the client calls `shop.example.com`, hostname verification must fail even if the certificate is signed by a trusted public CA.

### 2.2. Client Authentication

In standard one-way TLS, the server does not require the client to present a certificate. The server may authenticate users at the HTTP layer using sessions, OAuth 2.0, OIDC, API keys, or other mechanisms.

In mTLS, the server requests a certificate during the handshake. The client presents its certificate and proves possession of the corresponding private key. The server validates the certificate chain and related conditions before accepting the handshake.

A certificate only proves that a public key was issued by a CA to an identity under the CA's policy. It does not by itself grant the certificate holder permission to call every API.

## 3. Reading Certificates and Certificate Chains

An X.509 certificate binds a public key to an identity and is signed by a CA. Key fields include:

| Field | Operational Meaning |
|---|---|
| Subject | Identity recorded in the certificate; do not rely solely on Common Name in new designs |
| Subject Alternative Name (SAN) | DNS names, URIs, or other identifiers represented by the certificate |
| Issuer | CA that signed the certificate |
| Serial Number | Certificate identifier scoped to the CA |
| Not Before / Not After | Validity window of the certificate |
| Public Key | Public key used in cryptographic operations |
| Key Usage / Extended Key Usage | Restricts key purposes, such as `serverAuth` or `clientAuth` |
| Signature Algorithm | Algorithm used by the CA to sign the certificate |

A single certificate typically does not form a complete trust chain on its own. Example:

~~~text
Corporate Root CA
  └── Workload Issuing CA
        ├── checkout.prod.internal
        ├── inventory.prod.internal
        └── payment.prod.internal
~~~

- **Root CA:** trust anchor at the top of a PKI hierarchy. Root CA private keys must be strictly protected; many organizations keep root CAs offline.
- **Intermediate CA:** signed by the root CA and used to issue certificates to workloads. Can be separated by environment, business unit, or purpose.
- **Leaf certificate:** certificate of a specific server, client, service, or workload.
- **Certificate chain:** certificates linking the leaf through intermediates to the trust anchor.

A client typically installs the root CA or appropriate trust anchor in its trust store. The server is responsible for presenting required intermediates in a client-compatible manner. Missing intermediates are a common cause of verification failures even when the root CA is installed.

### 3.1. Trust Store and Key Store

These two concepts are often confused:

- **Trust store** holds CA certificates a process trusts to verify peer certificates.
- **Key store** holds the process's own private key and certificate, typically with its certificate chain.

In an mTLS connection between Service A and Service B:

- A needs a key store containing A's certificate and private key to prove client identity.
- A needs a trust store containing the CA A trusts to verify B's server certificate.
- B needs a key store containing B's certificate and private key to prove server identity.
- B needs a trust store containing the CA B trusts to verify A's client certificate.

Each side may use a single PKCS#12 file holding multiple entries or separate trust store and key store files. What matters is keeping workload private keys distinct from CA public certificates.

### 3.2. Never Share Private Keys

Never embed root CA or workload private keys in source code, container images, Git, shared AMIs, or logs. Each workload requires its own key pair. Secret read access must be scoped per workload; issuance and rotation workflows must be auditable.

AWS Certificate Manager manages private keys for certificates integrated with AWS services. When deploying private certificates to self-managed servers or applications, private certificates can be exported via ACM under supported conditions, and exported key files must be protected. Calling AWS Private CA directly to issue certificates from a CSR is a separate flow where the caller generates and retains the private key.

## 4. TLS Policies: Versions and Cipher Suites

Certificates answer the identity question; TLS security policies govern which protocol versions and cipher suites an endpoint accepts. Picking a strong certificate while permitting outdated TLS or weak ciphers weakens the entire connection.

### 4.1. TLS 1.2 and TLS 1.3

For new systems, set TLS 1.2 as the broad-compatibility minimum and prefer TLS 1.3 when clients support it. TLS 1.0 and TLS 1.1 are deprecated; do not enable them merely to keep an old client working without risk assessment and a retirement plan.

TLS 1.3 simplifies allowed cipher suites, drops legacy choices, and improves handshake efficiency. TLS 1.2 can remain secure when configured with modern ciphers, forward secrecy, and weak algorithms disabled.

**Forward secrecy** protects previously recorded sessions if the server's long-term private key is later compromised, provided the session used an appropriate ephemeral key exchange mechanism.

### 4.2. How to Choose a Policy

Do not select a policy merely because its name contains "TLS 1.3". Before applying, determine:

1. The actual client population and the TLS versions/ciphers they support.
2. Minimum requirements from internal standards or regulations.
3. Whether FIPS-validated cryptographic modules or FIPS policies are required.
4. Whether post-quantum algorithms or specific RFC requirements apply.
5. Whether backend connections are compatible with the policy used by the AWS service.

Elastic Load Balancing provides multiple policy families for ALB and NLB, including TLS 1.2/1.3 policies, FIPS policies, post-quantum policies, and compatibility policies. Policy lists and names vary by service. Consult the current list in documentation for the exact load balancer type and Region before deploying.

Example ALB policy name supporting TLS 1.3 and TLS 1.2:

~~~text
ELBSecurityPolicy-TLS13-1-2-2021-06
~~~

This name illustrates naming conventions, not a universal default for every workload. If an organization requires FIPS or post-quantum policies, check front-end, back-end, clients, and targets before switching.

### 4.3. Checking Compatibility Before Tightening Policies

A policy change can lock out older clients. Deployment procedures should include:

- Collecting current TLS protocols, ciphers, and handshake errors from access logs or connection logs where supported.
- Segmenting clients by app version, OS, TLS library, and criticality.
- Testing the new policy in a test environment against representative clients.
- Monitoring handshake failure rates and error rates after the change.
- Maintaining a tested policy rollback plan.

With ALB, access logs and connection logs provide visibility into negotiated protocols and ciphers. Log data lets you decide based on real clients rather than assumptions.

## 5. mTLS Handshake and Trust Model

In mTLS, both parties verify the peer's certificate. General flow:

~~~mermaid
sequenceDiagram
    participant A as Client / Service A
    participant B as Server / Service B
    A->>B: ClientHello (protocol, cipher, key share)
    B->>A: ServerHello + server certificate + CertificateRequest
    A->>A: Verify server chain, SAN, validity
    A->>B: Client certificate + proof of private key
    B->>B: Verify client chain, usage, validity, revocation policy
    A->>B: Finished
    B->>A: Finished
    A->>B: Encrypted application request
    B->>B: Map certificate identity to authorization policy
~~~

Message details differ between TLS 1.2 and TLS 1.3, but the operational principle is identical: both parties establish session keys and verify identities against a trust policy.

An mTLS system must clearly answer:

- Which CA is authorized to issue workload certificates?
- Are certificates permitted for `clientAuth`, `serverAuth`, or both?
- Where in the SAN is the workload identity stored?
- Which services are permitted to trust that CA?
- How are revoked or expired certificates handled?
- How do verified identities map to business permissions?

### 5.1. Trust Boundaries

The trust store defines the trust boundary. If all services trust one broad root CA, any certificate issued by that CA can pass TLS verification. Separating CAs by environment and purpose reduces blast radius.

Example:

| Trust Domain | Workloads | Rule |
|---|---|---|
| dev | checkout-dev, inventory-dev | Development environment only |
| staging | checkout-stg, payment-stg | Must not accept dev certificates |
| production | checkout-prod, payment-prod | Dedicated Issuing CA, restricted issuance permissions |
| partner | shipping partners | Dedicated trust per partner or partner group |

Do not place individual client certificates into the trust store as a static list when a dedicated CA can be used. CA-based trust scales better, though it requires strict control over certificate issuance permissions.

### 5.2. Certificate Authentication Is Not Authorization

After a successful handshake, the application must extract the verified identity and map it to policy. Example:

| Certificate Identity | Application Permission |
|---|---|
| `spiffe://shop/prod/checkout` or equivalent SAN URI | Call Order API to create orders |
| `spiffe://shop/prod/inventory` | Update inventory via internal endpoint |
| Certificate of `partner-carrier-a` | Submit shipping status for partner A's shipments |

These are logical identity examples; exact SAN URI formats must align with the certificate issuance system. Never grant permissions solely from a Subject string sent by a client in an HTTP header. Verify the certificate at the TLS endpoint and pass verified identity only over a protected backend channel.

## 6. Building a PKI and Certificate Lifecycle

A workload PKI requires an end-to-end lifecycle:

~~~mermaid
flowchart TD
    A[Define identity and trust domain] --> B[CA policies and issuance permissions]
    B --> C[Generate key pair on workload or key store]
    C --> D[CSR / certificate request]
    D --> E[CA verifies and signs]
    E --> F[Distribute certificate chain]
    F --> G[Establish TLS or mTLS]
    G --> H[Monitor expiry and handshake errors]
    H --> I[Renew / rotate / revoke]
    I --> F
~~~

### 6.1. Issuance

Issuance workflows must verify the caller is authorized to represent the requested identity. A role permitted to call a certificate issuance API should not be able to request arbitrary SANs belonging to another workload. Constrain templates, subjects, SANs, key usage, and validity periods to reduce abuse.

### 6.2. Renewal and Rotation

Certificates expire. Renewing a certificate and rotating a key pair are related yet distinct operations. Reissuing a certificate with the same key pair leaves exposure intact if the private key was compromised.

A safe rotation workflow typically:

1. Generates a new key pair for the workload.
2. Requests a new certificate from the trusted CA.
3. Installs the new certificate and chain without removing the old one while clients still need it.
4. Verifies bidirectional connectivity using the new certificate.
5. Shifts all traffic to the new certificate.
6. Revokes or stops trusting the old certificate per policy.
7. Deletes the old key from storage after the rollback window closes.

When rotating CAs, provide an overlap period: trust stores accept both old and new CAs, workloads gradually migrate to certificates from the new CA, and then the old CA is removed from trust stores. Removing the old CA before all clients and servers transition causes widespread connection failures.

### 6.3. Revocation

Certificates may need revocation before expiration if a private key is exposed, a workload is decommissioned, or an identity is no longer valid. Common mechanisms:

- **CRL (Certificate Revocation List):** list of revoked serial numbers published by the CA.
- **OCSP (Online Certificate Status Protocol):** queries certificate status via an OCSP responder.
- **Short-lived certificates:** shorten lifetimes to shrink the exposure window when issuance and distribution automation supports it.

Not all AWS services check revocation identically. For instance, API Gateway mTLS does not check whether a certificate has been revoked. If immediate revocation is required, select an architecture that supports it or add checks at the application layer.

### 6.4. Private Key Management

Root CA private keys require stronger protection than leaf certificate keys. Restrict CA issuance permissions, enable auditing, protect backup procedures, and maintain a compromise response plan. For workload keys, prefer generating keys in controlled environments and never distribute one shared key across multiple replicas.

AWS Private CA manages the CA hierarchy and CA private keys inside the service. IAM policies and CA policies determine who can create CAs, issue certificates, revoke certificates, or alter configurations. Use dedicated roles and restrict issuance permissions by template/identity.

## 7. Certificate Options in AWS

| Service | Best When | Key Points |
|---|---|---|
| AWS Certificate Manager (ACM) public certificate | Public endpoints using integrated AWS services like ALB, CloudFront, API Gateway | ACM manages certificates and private keys for supported integrations; DNS validation is typically best for auto-renewal |
| ACM private certificate with AWS Private CA | Endpoints or workloads needing a private PKI, especially when attached to ACM-integrated services | Trust is established when clients install the appropriate CA |
| Direct issuance via AWS Private CA | Need to generate CSRs, hold private keys yourself, or integrate custom PKI | Caller manages keys and certificate lifecycle |
| Certificate import | Existing external PKI or certificates issued by another CA | Organization manages renewal, keys, and deployment updates |

ACM public certificates suit public domains. ACM private certificates suit internal trust domains. Private certificates are not automatically trusted by browsers or external clients; clients must install the corresponding CA.

### 7.1. ACM and Managed Renewal

ACM can automatically renew eligible certificates. For private certificates requested via the ACM console or ACM `RequestCertificate` API, ACM can perform managed renewal while the CA remains active and usage conditions are met. Certificates issued directly via the AWS Private CA `IssueCertificate` API are outside ACM's managed renewal flow.

If private certificates are exported and installed manually on servers, ACM issuing a new certificate does not mean servers have updated. You need a distribution pipeline, process reload, connectivity checks, and active-version monitoring.

### 7.2. AWS Private CA Hierarchy

AWS Private CA lets you build root CAs and subordinate CAs for internal PKI. CAs can be split by environment or purpose, with CRL and OCSP configured as appropriate.

Reference hierarchy:

~~~text
Organization Root CA
  ├── Production Issuing CA
  │     ├── Server certificates
  │     └── Client/workload certificates
  ├── NonProduction Issuing CA
  │     ├── Development
  │     └── Staging
  └── Partner Issuing CA
        └── Certificates for approved integrations
~~~

Do not create many CAs unnecessarily. Every new CA increases cost, operational overhead, and the number of trust anchors to manage. Align CA boundaries with trust boundaries and blast radius.

## 8. mTLS on Application Load Balancer

Application Load Balancer (ALB) supports mTLS on HTTPS listeners. ALB offers two modes with distinct purposes:

| Mode | Behavior | When Suitable |
|---|---|---|
| Verify | ALB validates X.509 client certificates against a trust store; supports configuring a certificate revocation list | When you want ALB to authenticate clients before forwarding requests |
| Passthrough | ALB accepts the certificate chain and forwards certificate details to targets via HTTP headers; target applications validate and decide | When applications need custom validation logic or full chain metadata |

In verify mode, create a trust store from a CA bundle, optionally add a CRL, and attach the trust store to the HTTPS listener. A secure listener binds to one trust store at a time; one trust store can be shared across multiple listeners.

### 8.1. Verify Mode Flow

~~~mermaid
flowchart LR
    C[Partner client] -->|TLS + client certificate| A[ALB HTTPS listener]
    A -->|Verify chain / expiry / revocation policy| T[Trust store]
    T -->|Trusted| F[Forward request]
    T -->|Untrusted| X[Reject handshake]
    F --> B[Application target]
    B --> Z[Authorize by partner identity]
~~~

ALB validates the certificate at the front end. The application must still map the certificate identity to the right partner and determine which resources that partner may access. When using `X-Amzn-Mtls-*` HTTP headers, trust them only when targets accept traffic exclusively from trusted ALBs and direct access paths to targets are blocked. Never allow clients to inject same-named headers via another path and have the app treat them as verified identities.

### 8.2. Example: Creating a Trust Store and Attaching to a Listener

Assume the PEM CA bundle sits in a secured S3 bucket. The example below configures an existing ALB; replace ARN, bucket, and key values for your environment:

~~~bash
aws elbv2 create-trust-store --name partner-client-ca --ca-certificates-bundle-s3-bucket security-artifacts --ca-certificates-bundle-s3-key pki/partner-ca-bundle.pem
~~~

After creating the trust store, take `TrustStoreArn` from the output and attach it to the listener:

~~~bash
aws elbv2 modify-listener --listener-arn arn:aws:elasticloadbalancing:ap-southeast-1:111122223333:listener/app/shop/abc/def --ssl-policy ELBSecurityPolicy-TLS13-1-2-2021-06 --mutual-authentication "Mode=verify,TrustStoreArn=arn:aws:elasticloadbalancing:ap-southeast-1:111122223333:truststore/partner-client-ca/1234567890"
~~~

These commands require Elastic Load Balancing IAM permissions and S3 object read permissions. A trust store takes effect only after attaching to a listener. In real deployments, verify trust store state, PEM bundle, CRL, quotas, and handshake logs before opening traffic.

### 8.3. Passthrough Mode

Passthrough mode does not mean ALB verified the client certificate. ALB forwards the certificate chain to targets in headers formatted per AWS documentation. The target must verify the chain, validity window, usage, and required revocation policy. If an application merely decodes `Subject` and trusts it blindly, clients can spoof identities using invalid certificates.

Choose passthrough when the application needs full control over certificate logic or specific chain attributes. Choose verify when ALB can perform standard validation and you want to offload certificate handling from applications.

## 9. mTLS on Network Load Balancer

Network Load Balancer (NLB) supports mTLS verify mode on TLS listeners. NLB validates X.509 client certificates against a trust store and can apply identity filters and revocation checks per configuration.

If you need to pass raw TLS connections to targets so applications or proxies handle mTLS themselves, use a TCP listener on the TLS port rather than a TLS listener. With a TCP listener, NLB forwards encrypted traffic; the target terminates TLS and performs certificate verification.

| Listener Type | Where TLS Terminates | mTLS |
|---|---|---|
| NLB TLS listener | NLB | Supports verify mode per NLB mTLS features |
| NLB TCP listener on 443 | Target | Target implements mTLS itself |

Important backend note: when a target group uses the TLS protocol, NLB establishes a TLS connection to targets but does not verify target certificates. Therefore, do not treat this configuration as certificate-based authentication of backend identities. AWS documents traffic inside the VPC as packet-level protected in that model; if your threat model requires verifying backend identity, implement mTLS at the target or proxy and control the corresponding network paths.

## 10. mTLS on Amazon API Gateway

API Gateway supports mTLS for Regional custom domains on REST APIs and HTTP APIs. Clients must present a certificate accepted by the trust store when calling the API through the custom domain.

Key requirements:

- Use a Regional custom domain.
- REST APIs require security policy `TLS_1_2`.
- HTTP APIs require minimum TLS version 1.2.
- The trust store is stored in Amazon S3.
- Client certificates must have an issuer and full chain to a root CA in the trust store.
- mTLS is not supported for private APIs.
- API Gateway does not check whether a certificate has been revoked.

### 10.1. Example: Configuring an HTTP API Custom Domain

~~~bash
aws apigatewayv2 create-domain-name --domain-name api.partner.example.com --domain-name-configurations CertificateArn=arn:aws:acm:ap-southeast-1:111122223333:certificate/12345678-1234-1234-1234-123456789012,EndpointType=REGIONAL,SecurityPolicy=TLS_1_2 --mutual-tls-authentication TruststoreUri=s3://security-artifacts/pki/partner-truststore.pem
~~~

After creating the custom domain, configure API mappings and DNS records per design. Trust stores can hold public or private CA certificates. For API Gateway, enable bucket versioning so you can pin trust store object versions when updating.

### 10.2. Updating the Trust Store

When adding or rotating a CA, upload the updated bundle to S3 and update the custom domain to the appropriate object version. REST APIs support updating `truststoreVersion`; HTTP APIs have a corresponding version field in mutual TLS configuration.

API Gateway returns warnings when processing a trust store containing invalid certificates at domain update time. The service does not automatically alert when a certificate inside the trust store later expires. Operations teams must monitor expiration dates of both CAs and leaf certificates.

### 10.3. Choosing API Gateway or ALB

API Gateway fits API management, custom domains, API mappings, throttling, and API integrations. ALB fits HTTP/HTTPS routing to target groups and web workloads. If client certificate revocation must be enforced at the TLS termination point, note that API Gateway mTLS does not check revocation; ALB can configure CRLs in verify mode.

## 11. TLS Between Workloads on EC2, ECS, and EKS

When services call services, treat each hop as a distinct connection. TLS at a public ALB does not automatically protect the hop from ALB to target, or from Checkout to Payment.

A reference architecture:

~~~mermaid
flowchart LR
    subgraph VPC
      A[Checkout workload<br/>client cert + private key]
      B[Payment workload<br/>server cert + client trust]
      C[Inventory workload<br/>server cert + client trust]
      A -->|mTLS| B
      A -->|mTLS| C
    end
    CA[AWS Private CA / enterprise CA] -->|Issue identities| A
    CA -->|Issue identities| B
    CA -->|Issue identities| C
~~~

mTLS can be implemented at:

- **Application:** Spring Boot, Netty, Node.js, Go, or servers configured directly with TLS.
- **Sidecar/proxy:** Envoy or a suitable service mesh managing TLS and certificates beside each workload.
- **Load balancer/API gateway:** terminates mTLS at system entry and passes verified identity to backends over a protected channel.

On ECS or EKS, adding a sidecar does not automatically produce mTLS. You must configure certificate issuance, trust bundle distribution, inter-service policies, readiness during certificate rotation, and strict read permissions on private keys. Never assume VPC encryption or security groups already provide workload authentication.

### 11.1. TLS Termination and Individual Hops

Suppose a client connects via HTTPS to an ALB, and the ALB forwards HTTP to ECS. The client–ALB leg is encrypted, while the ALB–ECS leg lacks TLS.

If the ALB forwards HTTPS to targets, the backend leg is encrypted. However, ALB does not verify target certificates in HTTPS target groups. If backend identity verification via certificates is required, add an appropriate mechanism in the app/proxy or redesign TLS termination points.

| Hop | Goal | Possible Configuration |
|---|---|---|
| Client → ALB | Protect public connection | HTTPS listener, ACM certificate, TLS security policy |
| Client → ALB | Verify client/partner | ALB mTLS verify or passthrough |
| ALB → target | Encrypt internal traffic | HTTPS target group |
| Service A → Service B | Authenticate both workloads | mTLS in app or sidecar/proxy |
| Partner → API Gateway | Verify partner certificate | Regional custom domain and mTLS trust store |

Do not call an architecture "end-to-end mTLS" if TLS terminates at the ALB and backends receive plain HTTP. Document every TLS hop, decryption point, and authorization point explicitly.

## 12. Example mTLS Configuration for a Java Application

The example below uses Spring Boot to illustrate a server requiring client certificates. In practice, secrets holding key stores must be injected via an appropriate secret management mechanism and never baked into images.

### 12.1. Creating a Trust Store from a CA Certificate

Suppose `workload-root-ca.pem` is the CA certificate the server uses to verify clients:

~~~bash
keytool -importcert -noprompt -alias workload-root-ca -file workload-root-ca.pem -keystore client-ca-truststore.p12 -storetype PKCS12
~~~

The command prompts for a trust store password if not supplied. In pipelines, never write real passwords into command history or repositories.

### 12.2. Server Configuration

The server needs a key store containing the server certificate, private key, and chain, plus a trust store containing CAs authorized to issue client certificates:

~~~properties
server.port=8443
server.ssl.enabled=true
server.ssl.key-store=classpath:payment-server.p12
server.ssl.key-store-type=PKCS12
server.ssl.key-store-password=<injected-secret>
server.ssl.trust-store=classpath:client-ca-truststore.p12
server.ssl.trust-store-type=PKCS12
server.ssl.trust-store-password=<injected-secret>
server.ssl.client-auth=need
server.ssl.enabled-protocols=TLSv1.3,TLSv1.2
~~~

`client-auth=need` requires clients to present certificates. The `want` setting allows clients without certificates, making it unsuitable when an endpoint mandates mTLS. After the TLS handshake succeeds, the application must still read the verified principal/certificate and enforce authorization.

### 12.3. Calling with curl

The client needs its own certificate and private key. `--cacert` specifies the CA to verify the server; `--cert` and `--key` prove client identity:

~~~bash
curl --verbose --cacert server-root-ca.pem --cert checkout-client-chain.pem --key checkout-client.key https://payment.internal.example:8443/health
~~~

Never use `--insecure` to bypass certificate errors in production. That flag disables server certificate verification and can mask trust or hostname errors.

### 12.4. Checking Handshakes with OpenSSL

~~~bash
openssl s_client -connect payment.internal.example:8443 -servername payment.internal.example -CAfile server-root-ca.pem -cert checkout-client.pem -key checkout-client.key -verify_return_error -tls1_3
~~~

If the server does not support TLS 1.3, test TLS 1.2 separately in a test environment. Never weaken production policy just to make a test command succeed.

## 13. Designing Inter-Service Trust Policies

A strong trust policy specifies identity, issuer, purpose, and permissions:

| Attribute | Policy Example |
|---|---|
| Issuer | Accept only Production Workload Issuing CA |
| Environment | Production certificates must not be accepted in staging |
| SAN | Accept only identities matching registered namespaces |
| EKU | Client certificates must have `clientAuth`; server certificates must have `serverAuth` |
| Validity | Certificate is active and within maximum allowed lifetime |
| Revocation | Check CRL/OCSP if endpoint supports and requirements demand it |
| Authorization | Checkout may call only authorized Order endpoints |

### 13.1. Separating CAs by Role

You do not necessarily need a separate CA per microservice. However, avoid a single CA authorized to issue arbitrary certificates across every environment. Consider splitting CAs by:

- Production vs. non-production.
- Server identity vs. client/workload identity if policy demands it.
- Partners or partner tiers with differing trust levels.
- Accounts or business units with separate governance boundaries.

CA separation decisions must balance blast radius, cost, service quotas, and operational complexity.

### 13.2. Workload Identity

SAN is the right place to embed server or workload identifiers. DNS SANs suit DNS names. URI SANs can represent workload identities under organizational conventions. Applications must verify identities per those conventions; never infer permissions solely from IP addresses or self-reported hostnames.

## 14. Protecting Trust Stores and Certificate Artifacts

A trust bundle is a security configuration. If an attacker adds their own CA to a trust bundle, certificates issued by that CA will be accepted wherever the bundle is used.

For trust stores in S3:

- Enable block public access and bucket policies restricting read/write principals.
- Enable versioning to recover prior versions and roll out changes safely.
- Enable appropriate encryption, such as SSE-KMS per governance requirements.
- Audit object changes, updaters, and deployed versions.
- Never grant ordinary workloads write permissions on trust bundles.
- Validate PEM contents and chains before publishing.

For private keys:

- Store in a secret manager or suitable key management system.
- Scope read permissions to the specific workload identity.
- Never log private keys, passphrases, or full secrets.
- Never bake keys into container images, source repositories, or shared AMIs.
- Rotate immediately upon suspected compromise and maintain a certificate replacement procedure.

## 15. Monitoring and Operations

TLS/mTLS often receives attention only when certificates expire or handshakes fail. Production systems must actively track:

| Signal | Operational Question |
|---|---|
| Days remaining on server certificate | Is there enough lead time to renew and distribute? |
| Days remaining on CA/intermediate | Can new certificates still be issued across workload lifetimes? |
| TLS handshake failures | Did errors spike after changing policies, bundles, or certificates? |
| Protocol/cipher distribution | Which older clients still rely on weak TLS? |
| mTLS authentication failures | Are clients omitting certificates, sending broken chains, or using expired certs? |
| Trust store version | Which bundle is each listener/domain actively using? |
| CA issuance/revocation events | Are there anomalous certificate requests or emergency revocations? |

Combine appropriate log sources:

- ALB access logs and connection logs to investigate requests and TLS connections.
- CloudTrail to audit administrative actions on ACM, AWS Private CA, ELB, and API Gateway.
- CloudWatch metrics/logs and EventBridge for alerting and routing operational events.
- Application logs to record verified identities, authorization decisions, and correlation IDs.

Never log private keys, passphrases, or unnecessary sensitive certificate fields. If logging serial numbers or subjects for investigation, define retention and access controls.

### 15.1. Certificate Expiry Alerting Workflow

An actionable alert should include:

1. Service/domain name or workload identity.
2. Certificate ARN or serial number, issuer, and expiration date.
3. Where the certificate is deployed.
4. Owner responsible for renewal.
5. Renewal status and any remaining distribution steps.
6. Runbook link and priority level.

For ACM-managed certificates, monitor renewal status and related events. For exported certificates or certificates issued directly via Private CA, also monitor actual deployment steps, since issuing a new certificate does not guarantee endpoints have loaded it.

## 16. Troubleshooting TLS and mTLS

| Symptom | Common Cause | How to Check |
|---|---|---|
| `certificate has expired` | Leaf or intermediate expired; system clock skew | Check Not Before/Not After and system clock |
| `unknown ca` / `unable to get local issuer certificate` | Trust store missing root/intermediate or wrong CA | Print chain and inspect issuer at each level |
| Hostname mismatch | SAN lacks hostname called by client | Inspect DNS SANs and SNI |
| `bad certificate` | Client certificate wrong chain, key usage, or rejected | Check EKU, key usage, CA, and certificate request |
| `handshake failure` | No common protocol/cipher or mTLS config mismatch | Compare client/server TLS policies and handshake logs |
| ALB errors when verify enabled | Invalid trust store, malformed CA bundle, or untrusted client cert | Inspect trust store, PEM, chain, and CRL |
| API Gateway returns 403 on mTLS | Untrusted, expired, or unsupported-algorithm certificate | Inspect trust store and client certificate |
| Only one client group fails after policy change | Clients do not support new protocol/cipher | Correlate connection logs by client and change timestamp |
| Service A → B fails after rotation | A doesn't trust new CA yet, B hasn't loaded new cert, or chain incomplete | Inspect trust bundles in both directions |

### 16.1. Certificate Inspection Commands

Inspect certificate details:

~~~bash
openssl x509 -in client.pem -noout -subject -issuer -serial -dates -ext subjectAltName -ext extendedKeyUsage
~~~

Verify chain against root CA and intermediate:

~~~bash
openssl verify -CAfile root-ca.pem -untrusted intermediate-ca.pem client.pem
~~~

Test endpoint and TLS negotiation:

~~~bash
openssl s_client -connect api.example.com:443 -servername api.example.com -showcerts -verify_return_error
~~~

During investigation, record hostname, timestamp, client runtime, protocol, cipher, certificate issuer/serial, and exact error. Never attach private keys or keystore files to tickets.

## 17. Hands-On Lab: Enabling mTLS for Partners Calling an ALB

The lab goal is to let a partner holding an issued client certificate call an endpoint via an ALB. Only certificates issued by CAs in the trust store pass authentication.

### 17.1. Preparation

- An ALB with an HTTPS listener.
- A valid server certificate in ACM.
- A PEM CA bundle containing only CAs authorized to issue partner client certificates.
- A private S3 bucket storing the CA bundle.
- A lab client certificate and private key.
- An IAM principal permitted to manage trust stores/listeners and read the required S3 object.

In production, use CAs managed by AWS Private CA or enterprise PKI. Never use self-signed lab root CAs as production trust anchors.

### 17.2. Creating the Trust Store and Enabling Verify Mode

1. Upload the CA bundle to the private S3 bucket.
2. Create the trust store using `aws elbv2 create-trust-store`.
3. Attach the trust store to the HTTPS listener with `Mode=verify`.
4. Select a TLS security policy meeting organizational standards and client compatibility.
5. Confirm listener and trust store are active.
6. Restrict target security groups to accept traffic only from the ALB.

Example command:

~~~bash
aws elbv2 describe-listeners --listener-arns arn:aws:elasticloadbalancing:ap-southeast-1:111122223333:listener/app/shop/abc/def
~~~

### 17.3. Positive Testing

Call the endpoint using a certificate issued by a trusted CA:

~~~bash
curl --verbose --cacert server-root-ca.pem --cert partner-client.pem --key partner-client.key https://partner-api.example.com/health
~~~

Expected result: TLS handshake completes and the request reaches the application. The application identifies the partner from ALB-verified certificate metadata and enforces appropriate authorization.

### 17.4. Negative Testing

Test each case sequentially:

- Omit the client certificate.
- Present a certificate issued by a CA outside the trust store.
- Present an expired certificate.
- Present a certificate lacking appropriate client authentication usage.
- Send a request with a hostname mismatched against the server certificate.

Expected result: cases violating trust policy are rejected at TLS or the corresponding verification layer. Record exact errors at the client, ALB, and application; do not infer which layer rejected solely from an HTTP status code.

### 17.5. Rotating the CA in the Lab

1. Prepare a new CA bundle containing both the old CA and the new CA.
2. Update the trust store following ALB procedures.
3. Issue new client certificates from the new CA.
4. Switch clients to the new certificates and confirm handshakes succeed.
5. Once all clients have migrated, remove the old CA from the bundle.
6. Verify old certificates are no longer accepted.

The lab succeeds when trusted certificates are accepted, untrusted certificates are rejected, and CA migration causes zero disruption to valid clients.

## 18. Choosing Architecture by Scenario

| Scenario | Recommended Choice | Rationale and Limitations |
|---|---|---|
| Public website needing HTTPS | ACM public certificate + ALB/CloudFront/API Gateway | Managed server certificates for public endpoints |
| Partner calling API via HTTP API | API Gateway Regional custom domain + mTLS | API Gateway validates client certificates; no revocation checks |
| Partner calling web app via ALB | ALB mTLS verify | ALB validates chain and supports CRLs per configuration |
| App needs custom chain handling | ALB passthrough | Backend must perform full validation itself |
| TCP service needing NLB and mTLS at NLB | NLB TLS listener with verify mode | NLB validates client certificates against trust store |
| Keep TLS handshake on backend behind NLB | NLB TCP listener | Target terminates TLS and handles mTLS itself |
| Two microservices calling each other | mTLS in app or sidecar/proxy | Each workload holds its own identity and policy |
| Internal PKI needed | AWS Private CA or enterprise PKI | Controls issuers, trust domains, and certificate lifecycles |

No single option fits every connection. Choose TLS termination points based on where identity must be verified, revocation requirements, certificate operations capability, and backend control needs.

## 19. Design Mistakes to Avoid

1. **Enabling HTTPS only at ingress and assuming the entire system is encrypted.** Trace every hop and specify the protocol on each leg.
2. **Using one CA across all environments.** Dev certificates could be accepted in production if sharing the same trust anchor.
3. **Sharing one client private key across multiple services.** Prevents isolating or revoking individual identities.
4. **Trusting Subject or HTTP headers without verifying certificates.** Identity must come from a trusted verification step.
5. **Confusing TLS with authorization.** A valid certificate does not automatically grant business permissions.
6. **Skipping hostname verification.** A certificate signed by a trusted CA can still belong to a different hostname.
7. **Swapping trust bundles and deleting the old CA immediately.** Unrotated clients will lose connectivity.
8. **Assuming ACM renewal means workloads have updated.** New certificates must be distributed and reloaded.
9. **Using API Gateway mTLS when gateway-level revocation checks are mandatory.** API Gateway does not check revocation status.
10. **Assuming ALB HTTPS target groups or NLB TLS target groups verify backend certificates.** Neither load balancer validates target certificates to authenticate backend identity.
11. **Disabling verification via `--insecure` or trust-all code.** Opens the door to spoofed connections.
12. **Failing to monitor CA expiry.** Leaf certificates can remain unexpired while their signing CA expires.
13. **Failing to audit certificate issuance permissions.** Attackers can request certificates for other identities if issuance permissions are too broad.
14. **Skipping negative certificate testing.** Testing only the happy path fails to prove trust policies reject invalid certs.

## 20. Self-Check Exercises

### Question 1

A public API runs HTTPS and validates its server certificate. What is missing if only partner systems should be allowed to call the API?

**Answer:** Client/partner authentication is needed, such as mTLS or another identity mechanism. After authentication, authorization is still required to restrict each partner to its allowed APIs and data.

### Question 2

Service A's trust store contains Service B's root CA. Does A need B's private key?

**Answer:** No. A only needs the CA certificate to verify B's server certificate. B's private key must stay on B. A needs its own key pair if B requires A to authenticate via mTLS.

### Question 3

Why can a valid certificate still fail hostname verification?

**Answer:** The certificate may be signed by a trusted CA while its SAN does not contain the hostname the client is connecting to.

### Question 4

How do ALB mTLS verify and passthrough modes differ?

**Answer:** Verify mode has ALB validate the client certificate against a trust store. Passthrough forwards the certificate chain to the target, and the target must validate it itself.

### Question 5

Is API Gateway mTLS suitable when an organization requires the gateway to check a CRL before every connection?

**Answer:** No, if that check must occur at API Gateway, because API Gateway mTLS does not check certificate revocation. Choose an endpoint supporting revocation or add appropriate verification controls.

### Question 6

Why should the old CA not be removed from the trust store immediately after creating a new CA?

**Answer:** Some clients/servers still hold certificates issued by the old CA. An overlap period is needed to migrate all workloads to the new CA before retiring the old CA.

### Question 7

Does an NLB TLS target group verify the target's certificate?

**Answer:** No. NLB establishes a TLS connection to targets without validating target certificates. If backend identity verification is required, implement it at the target/proxy or choose another architecture.

### Question 8

Does a certificate issued directly via the AWS Private CA `IssueCertificate` API automatically receive ACM managed renewal?

**Answer:** No. ACM managed renewal applies to private certificates requested through the ACM console or ACM `RequestCertificate` API under ACM eligibility rules.

### Question 9

If both client and server support TLS 1.3 yet the handshake fails after changing security policies, what should you inspect?

**Answer:** Inspect cipher suites, signature algorithms, key types, SNI, certificate chains, client implementation, and actual policies on both front-end and back-end. Supporting TLS 1.3 alone does not guarantee all other handshake parameters match.

### Question 10

Should any valid client certificate be allowed to call every Payment endpoint?

**Answer:** No. A certificate only authenticates identity. Payment must map that identity to an authorization policy and restrict allowed endpoints, actions, tenants, or resources.

## 21. Pre-Production Checklist

- [ ] TLS termination points are defined for every hop.
- [ ] TLS 1.2 is the compatibility minimum; TLS 1.3 is enabled where clients support it.
- [ ] Security policies align with security and compliance requirements.
- [ ] Server certificates have accurate hostname SANs and complete chains.
- [ ] Client certificates have appropriate identities, EKUs, and validity windows.
- [ ] Trust stores contain only approved CAs for the right trust domains.
- [ ] Private keys are absent from source code, images, and logs.
- [ ] Certificate issuance and revocation permissions are restricted and audited.
- [ ] Renewal, distribution, reload, and rollback procedures exist.
- [ ] Overlap windows are planned for CA rotations.
- [ ] Services that check revocation vs. those that do not are documented.
- [ ] Backends accept identity headers only from trusted proxies/load balancers.
- [ ] Authorization is enforced after certificate authentication.
- [ ] Alerts exist for both certificate expiry and CA expiry.
- [ ] Logs/metrics support investigating TLS handshakes and client identities.
- [ ] Positive, negative, expiry, unknown CA, and CA rotation tests have passed.
- [ ] Runbooks exist for private key compromise.

## 22. Official References

- [AWS: Configuring mutual TLS on an Application Load Balancer](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/configuring-mtls-with-elb.html)
- [AWS: Mutual authentication with TLS in Application Load Balancer](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/mutual-authentication.html)
- [AWS: Security policies for Application Load Balancer](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/describe-ssl-policies.html)
- [AWS: Authenticate clients using mutual TLS for Network Load Balancers](https://docs.aws.amazon.com/elasticloadbalancing/latest/network/mutual-authentication.html)
- [AWS: Security policies for Network Load Balancer](https://docs.aws.amazon.com/elasticloadbalancing/latest/network/describe-ssl-policies.html)
- [AWS: Mutual TLS for REST APIs in API Gateway](https://docs.aws.amazon.com/apigateway/latest/developerguide/rest-api-mutual-tls.html)
- [AWS: Mutual TLS for HTTP APIs in API Gateway](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-mutual-tls.html)
- [AWS: Certificate authorities in AWS Private CA](https://docs.aws.amazon.com/privateca/latest/userguide/creating-managing.html)
- [AWS: Manage the private CA lifecycle](https://docs.aws.amazon.com/privateca/latest/userguide/ca-lifecycle.html)
- [AWS: Private certificate renewal in ACM](https://docs.aws.amazon.com/acm/latest/userguide/renew-private-cert.html)
- [AWS: Export a private certificate from ACM](https://docs.aws.amazon.com/acm/latest/userguide/export-private.html)
- [AWS: Infrastructure security in Elastic Load Balancing](https://docs.aws.amazon.com/elasticloadbalancing/latest/userguide/infrastructure-security.html)

Policy names, quota limits, and integration capabilities can vary by service and Region. When deploying, cross-check current documentation for the specific AWS service and test with real clients.
