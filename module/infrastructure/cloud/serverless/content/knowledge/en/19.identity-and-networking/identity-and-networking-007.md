# DNS, TLS, and Certificates for Serverless Endpoints

Serverless applications often expose APIs under a hostname like `api.example.com`, receive webhooks from partners, or call external services. For endpoints to operate reliably and securely, DNS, TLS, and digital certificates must be configured properly. DNS helps clients locate the service address; TLS protects the transport channel and authenticates the server; certificates provide cryptographic proof for clients to verify the hostname they are connecting to.

These three layers are related, yet do not replace one another. DNS pointing to the right address does not prove an endpoint is trustworthy. A valid TLS certificate does not automatically grant API access permissions. TLS encryption does not replace authorization, webhook signature verification, encryption at rest, or service-to-service workload identity authentication.

In Java serverless architectures, public TLS is typically terminated at an API gateway, load balancer, CDN, or cloud-provider-managed ingress. The function receives events behind that layer. When the function calls a database, partner API, or internal service, the Java client must in turn verify the target endpoint's certificate. Therefore, both inbound and outbound paths must be designed, certificate lifecycles managed, DNS controlled, and procedures established for DNS or TLS failures.

## 1. What Problems Do DNS, TLS, and Certificates Solve?

| Component | Role | Does NOT Solve |
|---|---|---|
| DNS | Maps hostnames to addresses or service targets | Server identity authentication, traffic encryption, authorization |
| TLS | Encrypts data in transit, protects integrity, and authenticates peers per TLS mode | Business access permissions, encryption at rest |
| Server certificate | Binds a public key to a hostname or organization identity per PKI | Confirming a user is authorized to call an API |
| Client certificate | Provides cryptographic identity for a client in mutual TLS | Replacing all authorization checks |
| IAM / managed identity | Grants workloads permission to call cloud resources | Protecting all network connections outside TLS |
| API authorization | Checks which operations a caller is allowed to perform | Replacing certificate verification and channel protection |

For example, a client calls `https://api.example.com`. DNS resolves the hostname to the API gateway. During the TLS handshake, the gateway presents a certificate whose SAN covers `api.example.com` and proves possession of the corresponding private key. After TLS succeeds, the API gateway or function must still validate tokens, check scopes, and verify resource permissions.

For webhooks, HTTPS protects the transport channel but is insufficient to prove a payload was sent by the right partner. You must verify the webhook signature or a dedicated authentication mechanism per the integration contract.

## 2. Request Path to a Serverless Endpoint

A public endpoint architecture typically looks like:

~~~mermaid
flowchart LR
    C["Browser / mobile / partner"] --> R["DNS resolver"]
    R -->|"Hostname -> endpoint"| E["CDN / API Gateway / ingress"]
    E -->|"TLS termination"| T["Managed certificate"]
    E -->|"Authenticated integration"| F["Java function"]
    F --> D[("Database / queue / storage")]
    F -->|"Outbound HTTPS; function verifies peer certificate"| P["Partner API"]
~~~

DNS usually points to the target of the ingress layer. The function does not necessarily have its own public IP or hostname. An API gateway can route by path, method, stage, or API mapping and then invoke the function via an internal integration.

This creates two TLS paths to consider:

- **Inbound TLS:** clients or partners connect to the public endpoint. Certificates are typically attached at the gateway, load balancer, CDN, or platform ingress.
- **Outbound TLS:** the function connects to external dependencies or internal services. The Java HTTP client, database driver, or SDK verifies the target endpoint's certificate.

If the architecture involves proxies or multiple hops, determine where TLS terminates and whether the next hop is re-encrypted. Never assume that TLS from client to gateway means all traffic from gateway to backend is encrypted the same way.

## 3. Domains, Hostnames, and DNS Records

Domains are registered at a registrar; authoritative DNS zones are managed by a DNS provider. Both services may belong to the same provider or different ones. Delegation via NS records determines which nameservers are authoritative for a zone.

Common DNS records:

| Record | Purpose | Example |
|---|---|---|
| A | Maps a hostname to IPv4 | `api.example.com` → `203.0.113.10` |
| AAAA | Maps a hostname to IPv6 | `api.example.com` → `2001:db8::10` |
| CNAME | Aliases one hostname to another hostname | `api.example.com` → `gateway.provider.example` |
| ALIAS / ANAME / flattening | Provides alias at the apex domain per DNS provider feature | `example.com` → service target |
| TXT | Domain verification, policy configuration, or other metadata | domain verification token |
| CAA | Restricts which CAs are allowed to issue certificates for the domain | Allow only CAs chosen by the organization |
| NS | Zone delegation to nameservers | `ns1.dns-provider.example` |
| SOA | Zone metadata and administrative information | Primary NS, serial, timers |

Not all DNS providers support ALIAS or ANAME. Standard DNS forbids CNAMEs at the zone apex (e.g., `example.com`) because the apex already carries mandatory records such as SOA and NS. If you need to point the apex to a hostname target, use your DNS provider's ALIAS/ANAME or CNAME flattening feature, or place the endpoint on a subdomain.

Do not create an A record using a transient IP observed from a serverless service if the provider requires aliasing to a managed hostname/target. IPs can change as the platform scales or performs maintenance. Use custom domain integration and the record target supplied by the service.

## 4. TTL, Caching, and DNS Propagation

TTL (time to live) is how long a resolver is allowed to cache a DNS answer. A low TTL lets record changes become visible sooner, but increases queries to authoritative DNS. A high TTL reduces query load, yet extends how long some clients continue using an old address after cutover.

DNS propagation is often described as if there were a single uniform global delay, whereas in reality many resolvers cache answers independently. Observed propagation time depends on the previous TTL, negative caching, resolvers, clients, and the DNS provider.

When switching endpoints:

1. Check the current record and published TTL.
2. If needed, lower the TTL ahead of the switch with enough lead time for old caches to expire.
3. Prepare the new endpoint, certificate, and routing before changing DNS.
4. Test the new endpoint with the right hostname and TLS.
5. Update the record.
6. Monitor requests on both old and new endpoints during transition.
7. Keep the old endpoint running long enough for resolvers still holding cached answers to be served.

Lowering TTL right before cutover does not purge answers already cached by resolvers under the old TTL. Plan ahead accordingly. TTL also does not control certificate expiration or browser HSTS cache duration.

Resolvers can also cache negative answers (negative caching) when a hostname does not yet exist. If you create a record after a client has already received NXDOMAIN, some clients may continue seeing errors for a period. Check both authoritative answers and recursive resolvers.

In Java, DNS can be cached by the OS, JVM runtime, and HTTP client/connection pool. An open keep-alive connection can continue using an old IP even after the DNS record changes. For endpoints requiring failover, manage connection lifetimes and DNS caching according to the actual runtime/client; do not arbitrarily set the JVM TTL to 0, as that can increase DNS traffic and latency.

## 5. DNS Routing for Serverless and Multi-Region

DNS can route clients to endpoints under several policies:

- **Simple routing:** one hostname points to one target.
- **Weighted routing:** splits traffic across multiple targets by weight.
- **Latency-based routing:** selects the target with lower expected network latency based on resolver location.
- **Geolocation / geoproximity:** routes by geographic location or regional rules.
- **Failover routing:** switches to a backup target when health checks and policy permit.

These policies are useful for multi-region deployments or blue/green endpoints. However, DNS failover is not instantaneous cutover. Resolver caches may continue serving old answers; health checks have lag; client connections may stay open; application retries may resend requests.

For multi-region serverless APIs, align data strategy, idempotency, and event processing. If DNS shifts clients from Region A to Region B while the database exists only in A, the new endpoint may still depend on a distant or unavailable network path.

Do not rely on DNS weighted routing as the sole canary mechanism if you need per-user/session or per-request traffic control. DNS generally routes at the hostname level, and resolver caching can skew actual distribution away from configured weights. API gateways, CDNs, or application-level routing may fit better.

## 6. DNSSEC, CAA, and Domain Control

DNSSEC enables resolvers to verify the integrity and origin of DNS data via zone digital signatures. It mitigates spoofing or tampering of DNS responses along the resolution path. DNSSEC does not encrypt DNS queries, authenticate API callers, or replace TLS.

CAA records allow domain owners to specify which certificate authorities are permitted to issue certificates for the domain. CAA reduces the risk of unapproved CAs issuing certificates, provided the CA and required issuer parameters are configured accurately. If CAA does not authorize the CA in use, certificate issuance or renewal can fail.

Domain governance practices:

- Enable MFA and protect registrar/DNS provider accounts.
- Use dedicated roles and least privilege for DNS changes.
- Enable registry lock or domain lock if supported by the registrar.
- Maintain audit trails for changes to NS, A/AAAA, CNAME, TXT, and CAA records.
- Protect DNS API tokens as secrets; scope zones and actions.
- Enable DNSSEC when supported by the architecture and provider, with planned key rollovers.
- Verify CAA records before requesting certificates.
- Maintain domain ownership and registrar account recovery procedures.

DNS records are high-impact infrastructure configuration. A bad change can divert traffic to an unowned endpoint, disrupt APIs, or cause certificate validation failures.

## 7. TLS Handshake and the Role of Certificates

TLS (Transport Layer Security) establishes an encrypted channel between two peers. In HTTPS, TLS typically authenticates the server to the client using a certificate. Once the handshake succeeds, application data is protected for confidentiality and integrity over that connection.

Conceptually, the handshake performs:

1. Client and server negotiate a compatible TLS version and cipher suite.
2. The client sends the hostname in Server Name Indication (SNI) when connecting to multi-domain servers.
3. The server presents a certificate chain matching the hostname.
4. The client validates the chain, validity period, hostname, and trust anchor.
5. Both sides perform key exchange and establish session keys.
6. Application traffic is encrypted and integrity-checked using TLS algorithms.

TLS 1.2 and TLS 1.3 are the versions commonly used today. Prefer TLS 1.3 when both sides support it; when compatibility is needed, use TLS 1.2 with secure cipher suites. Do not enable TLS 1.0/1.1 on new public endpoints unless there is an approved, controlled compatibility exception.

TLS protects the connection to the peer the client verified. If the client skips hostname verification or trusts all certificates, the channel may be encrypted yet still connect to an attacker. Never resolve certificate errors by disabling certificate verification in production.

## 8. Certificate Chain, SAN, Wildcard, and SNI

A server certificate contains a public key, subject/issuer metadata, validity period, and extensions such as Subject Alternative Name (SAN). Clients verify that the target hostname is present in the SAN and build a chain from the leaf certificate through intermediate CAs to a trusted root anchor.

Key concepts:

- **Leaf certificate:** the certificate bound to the endpoint or hostname.
- **Intermediate CA:** the intermediate authority signing the endpoint's certificate.
- **Root CA:** the trust anchor trusted by the client.
- **SAN:** the list of hostnames or identities covered by the certificate.
- **Wildcard certificate:** a certificate covering wildcard hostnames, e.g., `*.example.com`.
- **SNI:** the hostname sent by the client during the TLS handshake so the server selects the matching certificate when one IP serves multiple hostnames.

A wildcard `*.example.com` typically covers `api.example.com` but does not cover `example.com` or `v2.api.example.com`. If both the apex domain and subdomains are needed, the certificate must include the corresponding SANs or use a separate certificate.

The certificate chain must include full intermediate certificates as required by clients. If the server sends only the leaf certificate without intermediates, some clients may fail to build a trust chain even though the certificate was validly issued by a CA.

SNI enables gateways or ingress controllers to select the right certificate when multiple custom domains share one address. Legacy clients that do not send SNI may be incompatible with modern virtual-hosted endpoints; factor this in when supporting legacy devices.

## 9. Certificate Types and Choosing the Right One

| Type | Characteristics | Use Case |
|---|---|---|
| Domain Validated (DV) | CA verifies domain control | Public APIs, websites, webhooks |
| Organization Validated (OV) | Adds organization verification | Endpoints requiring organizational metadata per policy |
| Extended Validation (EV) | Stricter organization verification process | Specific organizational/compliance mandates |
| Wildcard | Covers subdomains via wildcard | Multiple endpoints under one domain |
| SAN / multi-domain | Single certificate covers multiple specific hostnames | Gateways serving multiple domains |
| Private CA certificate | Signed by an internal CA | Internal services, private endpoints, mTLS |
| Self-signed | Self-signed, no default public trust chain | Labs or test setups with custom trust distribution |

Do not choose EV thinking it makes an API more secure on its own. TLS security depends on certificate verification, private keys, protocols, ciphers, endpoints, and authorization; validation class does not replace application controls.

Public certificates are commonly issued via ACME or a cloud/CDN managed certificate service. Private CAs suit internal systems where the organization manages trust distribution, issuance, and revocation. Never use arbitrary self-signed certificates for public endpoints, as clients will not trust them by default.

## 10. Custom Domain Certificate Issuance Workflow

A typical workflow:

1. Choose a hostname, such as `api.example.com`.
2. Determine where TLS terminates: API gateway, CDN, load balancer, or ingress.
3. Request a certificate from a managed certificate service or CA.
4. Prove domain control via DNS validation or an appropriate challenge.
5. Wait for the certificate to become issued/active.
6. Bind the certificate to the custom domain at the ingress/gateway.
7. Create DNS records pointing the hostname to the provider-supplied target.
8. Configure API mappings, base paths, or routes to the right backend.
9. Verify TLS chain, hostname, HTTP routes, and authorization.
10. Monitor renewals and expiration.

With DNS validation, CAs typically require creating a CNAME or TXT record containing a token. Retain the validation record per CA instructions; some services require the record to remain present for automatic renewal. Deleting the record after issuance can cause the next renewal to fail.

With HTTP-01 challenges, the CA must reach a verification path on the endpoint. Ensure gateways, redirects, and firewalls do not block the challenge. Wildcard certificates typically require DNS-01 challenges because HTTP-01 cannot prove wildcard control the same way.

Do not point production DNS to a gateway before the custom domain and certificate are ready if doing so exposes clients to TLS errors or missing routes. Verify the endpoint using a staging hostname or test environment before cutover.

## 11. TLS Termination at API Gateway or Ingress

In serverless, the gateway is typically where HTTPS connections arrive and where the certificate's private key is held. The gateway validates SNI/hostname, terminates TLS, and forwards requests to the function over an integration.

Example:

~~~text
Client
  |
  | HTTPS + certificate for api.example.com
  v
API Gateway / CDN / Ingress
  |
  | Authenticated integration
  v
Java Function
~~~

Managed certificates let the provider handle private keys, renewals, and binding certificates to custom domains. The public endpoint's private key does not need to be copied into the function's JAR or environment variables.

If the gateway and backend communicate over a public network or across another trust boundary, evaluate re-encryption on the next hop and backend authentication. For private integrations, verify network boundaries, security groups/firewalls, and identity. Do not rely on headers such as `X-Forwarded-Proto` or `X-Forwarded-Host` from clients unless the gateway strips and overwrites client-supplied values.

If a function receives client certificate details or identity via gateway-forwarded headers, trust only metadata authenticated and protected by the gateway. Block clients from injecting headers with the same name; the gateway must strip incoming headers and emit fresh ones after verification.

## 12. Custom Domains Across Serverless Platforms

Different platforms have distinct custom domain models. Although resource names differ, the general workflow remains: issue certificate, verify domain, bind hostname to ingress/API, and configure DNS.

| Platform | Common TLS Termination Point | Key Configuration Details |
|---|---|---|
| AWS API Gateway + Lambda | API Gateway custom domain or CloudFront | Certificate matching endpoint type/Region, API mapping, DNS alias |
| Azure Functions | App Service front end/custom domain or hosting-model ingress | Custom domain, managed certificate or certificate binding, DNS validation |
| Google Cloud Functions / Cloud Run functions | Platform-managed HTTPS endpoint or custom domain via ingress layer | Domain mapping or load balancer, managed certificate, DNS records |
| Container-based serverless | Managed ingress/load balancer | Certificate binding, hostname routing, and revision traffic |

Some constraints are provider-specific. For example, a service may require the certificate in a specific Region, a specific endpoint type, or an intermediate resource in front of the function to support custom domains. Check documentation for the exact API gateway, Region, and hosting plan before issuing certificates.

Do not assume a platform's Function URL or default hostname accepts custom domains directly. In many architectures, you must place an API gateway, CDN, or load balancer in front to manage domains, certificates, WAF, and routing.

## 13. Certificate Renewal, Rotation, and Revocation

Certificates have expiration dates. Once expired, TLS-compliant clients reject connections or display warnings. Treat renewal as a critical operational process on par with code deployment.

For managed certificates:

- Keep DNS validation records intact per provider instructions.
- Ensure the domain still resolves and meets the service's renewal conditions.
- Monitor renewal status and expiration.
- Alert sufficiently far ahead of expiration to handle failures.
- Verify the new certificate is bound to the right domain/slot/region.
- Verify the certificate chain after renewal.

For self-managed certificates:

1. Request a new certificate before the old one expires.
2. Install the new certificate and private key into the secret store or ingress.
3. Verify SAN, chain, and key pair match.
4. Switch the endpoint to the new certificate.
5. Test with real clients.
6. Retain the old certificate for a reasonable rollback window.
7. Revoke the old certificate if compromised or no longer authorized.
8. Delete the old private key per key management procedures.

Rotation should include an overlap period so clients and servers do not lose trust alignment. With mTLS, update the trust bundle to accept both old and new certificates during transition, then remove the old CA or client certificate once all clients have rotated.

Never wait until the expiration date to begin renewal. Track certificate expiration using service metrics, inventories, or approved scanners. Alerts should specify hostname, resource, issuer, expiry date, and owner.

## 14. Protecting Private Keys and Certificate Material

Public certificates are not secrets, but private keys must be strictly protected. If a private key is leaked, an attacker can impersonate the endpoint until the certificate is revoked or expires and clients update trust.

Principles:

- Prefer provider-managed certificates and private key management when appropriate.
- Never commit private keys, PFX passwords, or truststore passwords to repositories.
- Never bundle private keys into Lambda/Function packages or images.
- Use Key Vault, Secrets Manager, HSMs, or managed certificate stores per architecture.
- Restrict read/export permissions on private keys; enable auditing and alerts.
- Encrypt secrets at rest and limit in-process caching duration.
- Use dedicated permissions for certificate issuance/renewal automation.
- Never send private keys over chat, logs, artifacts, or pipeline outputs.

If a platform requires uploading PFX/PEM files, verify the file contains the exact private key, certificate chain, and password. Grant upload permissions only to the pipeline or deployment identity needing that action. If a managed service can keep keys non-exportable, prefer that option to reduce key exposure.

## 15. Mutual TLS (mTLS) for APIs and Webhooks

Standard TLS authenticates the server to the client. **Mutual TLS** requires both client and server to present certificates for mutual authentication during the handshake.

mTLS can be appropriate when:

- Only partners or devices with issued certificates may connect.
- B2B APIs require machine identity at the connection layer.
- Service-to-service communication occurs in environments with managed PKI and trust distribution.
- Gateways must reject clients outside a trust bundle before forwarding requests to functions.

mTLS does not determine user or business permissions on its own. After validating a client certificate, the gateway/function must still map the subject/SAN or certificate identity to a partner/client record, check revocation status, and authorize per API/resource.

Managing mTLS requires:

- A controlled CA or trust bundle.
- Processes for issuing, renewing, rotating, and revoking client certificates.
- Mapping certificate identities to clients/tenants.
- Enforcing algorithm and key-size policies.
- Monitoring expiring certificates and rejected clients.
- A way to update trust bundles without disrupting all partners.

If using API gateway managed mTLS, verify the exact headers/context the gateway passes to the backend and how spoofed client headers are blocked. If the gateway terminates mTLS, TLS client identity must be forwarded to the function over a trusted channel.

## 16. TLS for Outbound Requests from Java Functions

When a Java function calls a public HTTPS endpoint, the JDK typically uses the default truststore to verify certificate chains and hostnames. If the endpoint uses a certificate from a public CA trusted by the JVM, custom `SSLContext` configuration is usually unnecessary.

For internal endpoints using a private CA, place the CA certificate in a managed truststore and configure the HTTP client to use it. Avoid pinning temporary leaf certificates when you can trust the private root/intermediate CA per PKI policy; doing so makes leaf certificate rotation easier.

Example creating an `HttpClient` with a PKCS12 truststore:

~~~java
char[] password = System.getenv("TLS_TRUSTSTORE_PASSWORD")
        .toCharArray();

KeyStore trustStore = KeyStore.getInstance("PKCS12");

try (InputStream input = Files.newInputStream(
        Path.of("/mnt/secrets/partner-truststore.p12"))) {
    trustStore.load(input, password);
}

TrustManagerFactory trustManagerFactory =
        TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm()
        );
trustManagerFactory.init(trustStore);

SSLContext sslContext = SSLContext.getInstance("TLS");
sslContext.init(
        null,
        trustManagerFactory.getTrustManagers(),
        new SecureRandom()
);

HttpClient client = HttpClient.newBuilder()
        .sslContext(sslContext)
        .connectTimeout(Duration.ofSeconds(3))
        .build();

HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://partner.internal.example"))
        .timeout(Duration.ofSeconds(5))
        .GET()
        .build();

HttpResponse<String> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofString()
);
~~~

This example assumes the truststore file is mounted or loaded securely from a secret/configuration store, with imports and exception handling added. This truststore must contain all CAs the client must trust. If it contains only a private CA while the app also calls public endpoints, use an appropriately combined truststore or configure separate clients per endpoint group; do not inadvertently drop required public trust roots.

JDK `HttpClient` performs hostname verification by default. Never disable hostname verification and never create a `TrustManager` that accepts all certificates as a "quick fix" for PKIX errors. If a certificate fails validation, fix the chain, hostname, truststore, or DNS target.

## 17. Java Client Certificates and Outbound mTLS

If a partner requires a client certificate, the Java client needs a keystore holding the client certificate and private key. The truststore still verifies the server's certificate; the keystore proves the client's identity. These are two distinct roles.

Example initializing `SSLContext` with both `KeyManager` and `TrustManager`:

~~~java
KeyStore clientKeyStore = KeyStore.getInstance("PKCS12");
try (InputStream input = Files.newInputStream(
        Path.of("/mnt/secrets/client-identity.p12"))) {
    clientKeyStore.load(input, keyPassword);
}

KeyManagerFactory keyManagerFactory =
        KeyManagerFactory.getInstance(
                KeyManagerFactory.getDefaultAlgorithm()
        );
keyManagerFactory.init(clientKeyStore, keyPassword);

KeyStore serverTrustStore = KeyStore.getInstance("PKCS12");
try (InputStream input = Files.newInputStream(
        Path.of("/mnt/secrets/server-truststore.p12"))) {
    serverTrustStore.load(input, trustPassword);
}

TrustManagerFactory trustManagerFactory =
        TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm()
        );
trustManagerFactory.init(serverTrustStore);

SSLContext sslContext = SSLContext.getInstance("TLS");
sslContext.init(
        keyManagerFactory.getKeyManagers(),
        trustManagerFactory.getTrustManagers(),
        new SecureRandom()
);
~~~

This covers TLS initialization; use that `SSLContext` in `HttpClient` as in the previous example. Private key passwords and truststore passwords must come from a secret manager, never hardcoded. Never log keystore contents or private keys.

When integrating with multiple partners having different certificates, consider per-partner clients or explicit policy-based identity selection. Never automatically send the same client certificate to arbitrary hosts; doing so can expose machine identity to unrelated parties.

## 18. Java Truststores, Keystores, and Common Errors

| Component | Contains | Used For |
|---|---|---|
| Truststore | CA certificates or trusted certificates | Verifying server/peer certificates |
| Keystore | Private key and certificate chain of client/server | Presenting identity in TLS, signing, or decrypting as intended |
| PEM | Text format for certificates/keys | Exchanging certificates and keys in supported formats |
| PKCS12 (`.p12`/`.pfx`) | Container holding certificates, chains, and private keys | Storing password-protected identity or trust material |
| JKS | Java KeyStore format | Storing keys/certificates in the Java ecosystem |

Common errors:

- **PKIX path building failed:** the client cannot build a chain to a trust root; an intermediate may be missing or the CA is not in the truststore.
- **No subject alternative DNS name matching:** the URL hostname is missing from the certificate's SAN.
- **Certificate expired / not yet valid:** certificate validity period is invalid or the environment clock is skewed.
- **Received fatal alert: handshake_failure:** incompatible protocol, cipher, client certificate, or handshake configuration.
- **unknown_ca:** peer does not trust the other side's CA, common in mTLS.
- **bad_certificate:** malformed, expired certificate, missing key usage, or policy violation.
- **Connection timed out:** can be DNS, routing, firewalls, security groups, proxies, or an unresponsive endpoint; not necessarily a certificate issue.

Never resolve these errors by trusting everything. Identify which peer sent the error and inspect hostname, chain, truststore, system clock, protocol, and network routes.

## 19. DNS and TLS in Private Networking

Not every serverless endpoint is public. A function may call private databases, internal APIs, services inside a VPC/VNet, or private endpoints of cloud services.

Private DNS zones resolve internal hostnames to private addresses inside associated networks. Split-horizon DNS can return different answers for the same hostname depending on whether the resolver is on a public or private network.

When configuring private DNS:

- Associate the zone with the right VPC/VNet or network needing access.
- Verify the function's resolver can query the zone.
- Check DNS forwarding if using custom DNS servers.
- Avoid colliding hostnames or record shadowing between public and private zones.
- Use hostnames included in the certificate's SAN, even when DNS returns a private IP.
- Do not use raw IPs if the certificate was issued for a hostname.
- Verify routes, security groups, firewalls, NACLs, and private endpoint policies.

Private DNS is not an authorization mechanism. A workload resolving a hostname does not mean it is permitted to call the service. You still need IAM/managed identity, tokens, or mTLS alongside appropriate network policies.

With a private CA, the Java client must trust that CA. Private DNS and private certificates must be managed together: a hostname can resolve properly yet TLS will still fail if SANs or trust chains mismatch.

## 20. DNS Caching, Connection Reuse, and Serverless Runtime

Serverless execution environments can be reused. Java functions often reuse HTTP clients and connection pools to reduce handshake, DNS lookup, and TCP setup overhead. This helps latency, yet requires handling endpoint changes or closed idle connections.

Scenarios:

- DNS records change while the JVM or resolver still caches the old answer.
- Keep-alive connections remain open to the old IP.
- Gateways close idle connections; the next call receives a reset.
- Certificates rotate while clients hold long-lived TLS connections.
- Private DNS zones update while fresh runtimes have not resolved the new record yet.

Principles:

- Reuse thread-safe HTTP clients across invocations where appropriate.
- Configure connection idle timeouts and maximum lifetimes per dependency.
- Safely retry connection reset errors, but only for idempotent operations or with an idempotency key.
- Allow clients to establish new connections after DNS or certificate rotation.
- Configure connect, read, and overall timeouts.
- Never cache IPs permanently in application code.
- Monitor DNS failures, connection pool exhaustion, and TLS handshake errors.

Do not set DNS cache TTLs to extremes to fix every issue. First determine which resolver caches answers, whether connection pools hold stale sockets, and whether the provider supplies stable hostname targets.

## 21. HSTS, Redirects, and Security Headers for Public Endpoints

HTTP Strict Transport Security (HSTS) lets servers instruct browsers to access a domain exclusively over HTTPS for a specified duration. HSTS reduces downgrade risks or unintended HTTP access, though it applies only to supporting user agents and only after receiving a valid header.

Header example:

~~~text
Strict-Transport-Security: max-age=31536000; includeSubDomains
~~~

Use `includeSubDomains` only when every related subdomain reliably supports HTTPS. Do not enable preload or long durations without auditing the entire domain tree; misconfiguration can make subdomains unreachable.

Other practices:

- Redirect HTTP to HTTPS at the gateway/ingress.
- Prevent backends from generating absolute HTTP URLs based on spoofed forwarded headers.
- Configure `Secure`, `HttpOnly`, and `SameSite` cookie attributes appropriately if endpoints use cookies.
- Configure CORS for required origins; CORS is not authorization.
- Use WAF/rate limiting when public endpoints require abuse protection.
- Enable only organization-approved TLS protocols and cipher suites.
- Do not allow certificate mismatches or mixed content in client browsers.

Redirecting HTTP to HTTPS does not encrypt the initial request if a client sends sensitive data over HTTP. For sensitive APIs, require clients to use HTTPS from the outset and consider HSTS for browser traffic.

## 22. Testing DNS, TLS, and Certificates Before Release

Useful verification tools:

### Checking DNS

~~~bash
dig api.example.com A
dig api.example.com AAAA
dig api.example.com CNAME
dig +trace api.example.com
nslookup api.example.com
~~~

Check authoritative nameservers and recursive resolvers when results diverge. For CAA:

~~~bash
dig example.com CAA
~~~

For private DNS, run queries from the exact VPC/VNet or an environment sharing the same resolver path; testing from a public laptop does not prove a private zone works.

### Checking TLS Handshake and Certificate Chain

~~~bash
openssl s_client \
  -connect api.example.com:443 \
  -servername api.example.com \
  -showcerts \
  -verify_return_error
~~~

`-servername` sends SNI. Inspect subject/SAN, issuer, validity dates, chain, and verification output. To check the HTTP response:

~~~bash
curl -Iv https://api.example.com/health
~~~

Never use `curl -k` as production verification; that flag bypasses certificate verification and can mask errors.

### Checking Java Keystores

~~~bash
keytool -list -v \
  -keystore partner-truststore.p12 \
  -storetype PKCS12
~~~

Never put passwords on the command line or in shell history. Use prompts or proper secret handling. Never print private keys to the terminal or logs.

### Required Test Scenarios

1. Matching hostname and valid certificate.
2. Hostname absent from SAN must fail.
3. Expired or not-yet-valid certificates must be rejected.
4. Chains missing intermediates must be caught.
5. Untrusted CAs must be rejected.
6. Missing or invalid mTLS client certificates must be rejected.
7. Old and new DNS records verified during cutover.
8. Private DNS tested from the right network.
9. Certificate rotation does not disrupt clients.
10. Endpoints still enforce authorization after TLS succeeds.

## 23. Troubleshooting DNS and TLS Incidents

| Symptom | Possible Cause | How to Check |
|---|---|---|
| NXDOMAIN | Missing record, wrong zone/delegation, or negative cache | Check NS, authoritative answer, records, and resolver cache |
| SERVFAIL | DNSSEC validation, authoritative DNS, or upstream error | Check DNSSEC chain, nameservers, and SOA |
| DNS returns old target | TTL/cache not expired or connection pool holding sockets | Check previous TTL, resolvers, and connection lifetime |
| Certificate mismatch | SAN does not cover hostname or wrong SNI | Check URL hostname, SNI, and certificate binding |
| Certificate expired | Renewal failed or old certificate not replaced | Check expiry, validation records, and deployment binding |
| PKIX path building failed | Untrusted CA or missing intermediate | Check chain and Java truststore |
| mTLS unknown_ca | Client/server does not trust the peer's CA | Check trust bundle and certificate chain |
| Handshake timeout | Network, proxy, protocol, or slow peer | Check routes, firewalls, TLS version, and endpoint |
| API returns 403 after TLS | Authorization, WAF, or policy denial | Check tokens, scopes, resource policies, and gateway logs |
| Renewal not running | DNS validation record deleted or CAA blocks CA | Check CNAME/TXT validation, CAA, and issuer |

Distinguish DNS resolution errors, TCP connection errors, TLS handshake errors, and HTTP authorization errors. They occur at different layers; reading the right logs and metrics avoids swapping certificates when the actual cause is routing or IAM.

## 24. Production DNS and TLS Checklist

Before exposing a serverless endpoint publicly, verify:

1. Is the domain controlled by the organization and is the registrar account protected?
2. Are the authoritative DNS zone, NS delegation, and record targets accurate?
3. Do A/AAAA/CNAME/ALIAS records match the endpoint type and apex/subdomain?
4. Do TTLs align with cutover and failover plans?
5. Are DNSSEC and CAA configured per policy?
6. Do certificate SANs cover all required hostnames?
7. Does the certificate chain include full intermediates and matching trust anchors?
8. Are TLS 1.2/1.3 and cipher suites configured per baseline?
9. Is the TLS termination point clearly defined?
10. Do gateway-to-backend hops require TLS or dedicated private networking?
11. Do managed certificates auto-renew and are validation records still intact?
12. Do certificate expirations have metrics/alerts and an assigned owner?
13. Are private keys held in managed certificate services or secret stores?
14. Does mTLS have a trust bundle, identity mapping, rotation, and revocation process?
15. Do Java clients verify chains and hostnames without using trust-all?
16. Are private CAs distributed via managed truststores?
17. Have private DNS, resolvers, VPC/VNet links, and egress routes been tested?
18. Are HTTP client connection pools and DNS caches tuned for failover/rotation?
19. Are HSTS, redirects, cookies, and security headers properly configured for browser clients?
20. Have DNS, TLS, certificate rotation, mTLS, authorization, and cutover been tested?

## Conclusion

DNS helps clients locate endpoints; TLS establishes encrypted channels and authenticates peers; certificates provide cryptographic identities for hostnames or clients. In serverless, public TLS typically terminates at provider-managed gateways, CDNs, or ingress layers, while Java functions must still verify TLS when calling external dependencies or internal services.

Manage custom domains, DNS records, TTLs, CAA, and DNSSEC as infrastructure resources; issue certificates for exact hostnames, keep chains complete, automate renewals, and protect private keys. In Java, use truststores and keystores in their proper roles, preserve hostname verification, set timeouts, and manage connection reuse. Finally, combine TLS with IAM/managed identities, authorization, and webhook signature verification to protect the entire request from domain resolution through business execution.
