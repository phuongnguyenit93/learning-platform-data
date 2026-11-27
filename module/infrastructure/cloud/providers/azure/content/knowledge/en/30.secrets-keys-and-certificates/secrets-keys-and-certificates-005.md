# Certificate Management and the TLS Lifecycle

A Java application on Azure receives HTTPS traffic through Azure Front Door, forwards it to Application Gateway, and then to Pods on Azure Kubernetes Service (AKS). When the domain's TLS certificate expires, users see browser warnings even though the application and database are completely healthy. When a certificate has been renewed in Azure Key Vault yet the gateway still serves the old version, the fault lies in the sync or deployment mechanism. If an engineer works around this by disabling certificate verification in Java, the system may limp along temporarily, but it loses server identity verification.

**Certificate management and the TLS lifecycle** are therefore far more than buying or uploading a PFX file. It is an end-to-end process spanning **identity and domain definition**, generating/obtaining a **key pair**, requesting a **Certificate Authority (CA)** to issue the certificate, protecting the private key, deploying at the right TLS termination points, validating the trust chain, tracking expiration, renewing/rotating, verifying clients actually receive the new certificate, and revoking/replacing on incidents.

This lesson belongs to the **Secrets, Keys, and Certificates** chapter of the **CLOUD_PROVIDERS_AZURE** module. Along the Azure learning path from subscriptions, resource groups, and Microsoft Entra ID to virtual networking, compute, storage, and data, securing TLS is foundational for deploying, monitoring, operating, and controlling costs of an Azure application architecture.

> **Scope:** Uses modern TLS terminology and Azure products including **Key Vault, App Service, Azure Front Door, Application Gateway, and AKS**. Public certificate validity policies, auto-renewal capabilities, managed certificate types, SKUs/tiers, APIs, IAM, and sync schedules are subject to change. Never assume all Azure services share the exact same workflow. Hostname, vault, file, and path values are lab examples; no actions are executed against Azure merely by reading this lesson.

## Learning Objectives

After completing this lesson, you will be able to:

1. Explain **TLS, HTTPS, X.509 certificates, private keys, CAs, and certificate chains**.
2. Distinguish **server TLS**, **mutual TLS (mTLS)**, application authentication, and user authorization.
3. Understand **Subject Alternative Name (SAN)**, hostname verification, SNI, Extended Key Usage (EKU), validity, and trust stores.
4. Distinguish **certificates, keys, and secrets** in Azure Key Vault along with exportability and HSMs.
5. Choose between **Azure-managed certificates** and **bring your own certificate (BYOC)** for appropriate services.
6. Design TLS across **App Service, Azure Front Door, Application Gateway, AKS/Ingress**, and backend connections.
7. Plan issuance, validation, distribution, renewal, rotation, revocation, and recovery of certificates.
8. Diagnose TLS handshakes, chains, expiration, DNS/SNI, and Java truststores using read-only tools.
9. Build metrics, alerts, runbooks, and zero-downtime rotation tests.
10. Avoid mistakes like disabling certificate validation, leaking private keys, or believing **Private Endpoint = TLS**.

## 1. What Problem Does TLS Solve?

**Transport Layer Security (TLS)** establishes a secure communication channel between client and server, commonly used for HTTPS. Modern TLS targets:

- **Confidentiality:** encrypting transmitted contents.
- **Integrity:** detecting tampering in transit.
- **Server authentication:** the client verifies the server matches the identity issued the certificate.
- **Optional client authentication:** mTLS allows the server to verify a client's certificate when configured.

~~~text
Browser / Java client
          |
          | HTTPS (TLS)
          v
Azure Front Door / Application Gateway / App Service
          |
          | Optional second TLS session
          v
Backend Java API / AKS Pod
~~~

**TLS does not perform per-user authorization.** A website with a valid certificate can still have authorization bugs, leak data across tenants, or expose abusable API endpoints. HTTPS protects the transport channel and authenticates peers under a trust model, whereas **Entra ID, OAuth/OIDC, RBAC, and application authorization** handle separate layers.

## 2. Basic TLS/PKI Terminology

| Term | Meaning |
|---|---|
| **Public key** | Public cryptographic key bound to the certificate |
| **Private key** | Confidential key that must be protected; proves key ownership |
| **X.509 certificate** | Digital document signed by a CA containing the public key, identity, and attributes |
| **Certificate Authority (CA)** | Organization/system that signs and issues certificates |
| **Root CA** | Trust anchor, typically present in the client trust store |
| **Intermediate CA** | Intermediate CA that signs leaf/server certificates |
| **Leaf/server certificate** | Certificate bound to a specific HTTPS endpoint |
| **CSR** | Certificate Signing Request: request to a CA to issue a cert for a public key/identity |
| **SAN** | Subject Alternative Name: DNS names/IPs attested by the certificate |
| **SNI** | Server Name Indication: hostname sent by the client during TLS to select the right certificate |
| **TLS termination** | Point where a TLS session is decrypted/terminated |
| **mTLS** | Mutual authentication where both sides present certificates, per configuration |
| **Trust store** | Set of CAs/certs trusted by a client or server |
| **Key store** | Repository holding a party's private key and certificate, per keystore type |

**Never confuse a certificate with a private key.** Public certificates can be shared so clients can verify identity, but **private keys must never enter logs, repositories, or chat**.

## 3. How Does a Certificate Chain Work?

In public PKI, a server certificate is usually signed by an intermediate CA, which is certified by a root CA:

~~~text
Trusted Root CA (trust anchor on client)
           |
           | signs/delegates
           v
Intermediate CA
           |
           | signs
           v
Server certificate: api.example.com
           |
           | paired with corresponding private key
           v
Azure HTTPS endpoint
~~~

### What Must the Client Verify?

1. Signatures and the chain from the leaf up to a trusted root anchor.
2. The URL's **hostname** matches a SAN in the leaf certificate.
3. The current time falls within **Not Before/Not After** (accounting for clock skew).
4. The certificate is used for the intended purpose, such as serverAuth.
5. Cryptographic algorithms and parameters are accepted by the TLS stack.
6. Revocation/policy checks per client mechanism, configuration, and capability.

### Which Chain Should the Server Send?

Typically the server sends the leaf and required intermediates. The Root CA is usually already present on the client and **does not need to be sent** in the server certificate chain. Missing an intermediate can cause trust failures on some clients even while other browsers succeed via cached intermediates.

**Never fix trust failures by adding an unfamiliar site's leaf certificate to a production trust store** without verifying its identity, issuer, and trust process.

## 4. A TLS Handshake from an Operations Perspective

~~~text
Client                                   Server / Gateway
   |                                           |
   | ClientHello (TLS versions, ciphers, SNI)  |
   +------------------------------------------>|
   | ServerHello + certificate chain           |
   |<------------------------------------------+
   | Validate chain, hostname, dates, policy   |
   |                                           |
   | Key exchange + handshake verification     |
   |<=========================================>|
   |                                           |
   | Encrypted application data (HTTP)         |
   |<=========================================>|
~~~

This is a **conceptual** diagram, not the exact message sequence of TLS 1.2 or 1.3. TLS 1.3 has a different handshake and key schedule than TLS 1.2, and certificate/client-auth exchanges vary by mode.

### Why Does This Matter?

- **CertificateExpired** fails before any HTTP request is processed.
- **SNI/hostname** errors can cause a gateway to return another domain's certificate.
- A **handshake timeout** differs from an application HTTP 500.
- Even when TLS succeeds, the backend can still return HTTP 401/403/503 at the application layer.

## 5. TLS 1.2, TLS 1.3, and Protocol Configuration

In modern systems, prefer **TLS 1.3** when supported end to end, and retain **TLS 1.2** where required by approved clients. Disable deprecated protocol versions per security policy and service capabilities.

| Component | Decisions Needed |
|---|---|
| Front Door/App Gateway/App Service | Minimum TLS version and cipher policy support per SKU |
| Java Backend | JDK, JSSE/TLS protocols, and server library |
| Java HTTP Client | Truststore, hostname verification, TLS compatibility |
| Legacy Devices | Whether older TLS versions are required; isolate or upgrade them |
| Compliance | Approved FIPS/cipher/key-size policies |

Do not pick cipher suites from an outdated blog post; Azure managed services offer varying levels of cipher/policy control, and security standards evolve over time.

### TLS Termination Can Occur Multiple Times

Client → Front Door is one TLS session; Front Door → Application Gateway/Origin can be a second TLS session; gateway → backend can be a third TLS session. **Each session needs proper certificate validation and trust boundaries.**

## 6. SAN, CN, and Hostname Verification

An HTTPS certificate must contain the appropriate endpoint identity. In modern applications, **SAN DNS entries** are the primary mechanism for hostname verification; never rely on the Common Name (CN) alone.

Example:

~~~text
Certificate SAN:
  DNS:api.example.com
  DNS:catalog.example.com

Client connects:
  https://api.example.com      -> name present in SAN
  https://admin.example.com    -> does not match SAN
~~~

### Common Mistakes

- URL points to an **IP** while the certificate only lists DNS SANs.
- Using a different CNAME when the cert lacks the hostname the client actually connects to.
- Connecting to a Private Endpoint by raw private IP, bypassing FQDN/SNI.
- Using a wildcard at the wrong domain level.
- Admin or health endpoints using a domain name omitted from the SAN.

**Never disable hostname verification** to hide errors. Fix the certificate SAN, hostname, DNS, or client/gateway configuration.

## 7. Wildcard Certificates and Their Limits

A wildcard certificate like **\*.example.com** typically covers single-level subdomains such as **api.example.com** or **shop.example.com**, but does not by default cover **example.com** or **a.b.example.com**.

### Advantages

- One certificate covers multiple hostnames at the same level.
- Reduces the number of certificates to deploy in some architectures.
- Convenient when subdomain count is high and issuance supports it.

### Risks

- Sharing one private key across many endpoints increases the **blast radius** if leaked.
- A failed renewal impacts multiple services simultaneously.
- Not every managed certificate product supports wildcards.
- A wildcard certificate does not grant DNS authority or routing for all subdomains.

**Do not default to wildcards** if applications require private-key isolation. Per-domain leaf certificates are preferable when automated management is in place.

## 8. Validity, Expiration, and Certificate Lifetime

An X.509 certificate includes:

- **Not Before:** timestamp when validity begins.
- **Not After:** timestamp when validity ends.
- Key usage, EKU, SAN, and issuer attributes.

~~~text
Certificate timeline:
    Issue          Valid period                Expire
      |------------------------------------------|
      |                     |                    |
      |                Renewal window            |
      |                     |                    |
      +---------------------+--------------------+
~~~

### Why Not Wait Until the Expiration Date?

Renewal requires time for domain/CA validation, creating a new version, deploying through Azure gateways, cache propagation, rolling restarts, and testing. If both the cert and private key change, clients/backends holding pooled connections may need to reconnect.

**Maximum lifetimes for public certificates may be adjusted by the CA/browser ecosystem**; never hardcode a fixed 1-year or 90-day assumption in runbooks without verifying current rules and issuers.

## 9. Certificate Fingerprints, Serial Numbers, and Versions

Two certificates with the exact same SAN and CA can still differ in:

- **Serial number** of the certificate.
- Fingerprint/hash of the DER certificate.
- **Not After** and new validity dates.
- Public key and private key if rekeyed.
- Issuer/intermediate chain.
- Key Vault certificate version.

When verifying rotation, do not just check that a browser shows “green HTTPS”. Compare **fingerprint/serial/Not After** at the actual client-facing endpoint to prove the gateway is serving the new version.

### A Fingerprint Is Not a Secret

The SHA-256 fingerprint of a **public certificate** can safely be logged in runbooks for comparison, but never include the private key, password, or PFX in the same record.

## 10. How Do TLS and mTLS Differ?

**Standard TLS:** the client verifies the server's certificate. **mTLS:** the server also requires and verifies the client's certificate.

~~~text
Server TLS:
  Java client ------ verify server certificate ------> API

Mutual TLS:
  Java client <----- verify server certificate ------> API
  Java client ------ present client certificate -----> API
  API              ------ verify client certificate
~~~

### When to Use mTLS?

- Service-to-service authentication in controlled environments.
- B2B integrations requiring client certificate authentication.
- API gateways accepting client identities issued by a trusted CA.
- Service meshes or workload identity patterns.

### mTLS Does Not Replace OAuth/Entra ID

mTLS proves the **client possesses the private key matching its certificate** under an accepted trust policy. The API still must determine which resources, tenants, and actions that caller is authorized to access. Certificate authentication and OAuth can complement each other.

## 11. Three Commonly Confused Key/Certificate Types

| Type | Purpose | Example |
|---|---|---|
| **Server TLS certificate** | Client verifies HTTPS server | api.example.com |
| **Client mTLS certificate** | Server verifies client | partner-processor |
| **Code signing certificate** | Signs code/software | Signing release artifacts |
| **Document signing certificate** | Signs documents | Digital contracts/vouchers |
| **CA certificate** | Signs/verifies other certificates | Corporate root CA |

These types have distinct **Extended Key Usage (EKU), key usages, and trust policies**. Never use a clientAuth-only certificate in place of serverAuth when the TLS stack or CA policy forbids it.

### Risk of Reusing a Private Key

Using the same private key for a web server, code signing, and mTLS is risky and usually violates policy. Separate keys by purpose, identity, lifecycle, and trust boundary.

## 12. Certificate Lifecycle Management Is a State Machine

~~~text
Inventory & ownership
         |
         v
Policy: domain, CA, key type, validity, usage
         |
         v
Generate key / CSR / domain validation
         |
         v
Issue certificate / import to approved store
         |
         v
Validate chain, SAN, key pair, EKU and formats
         |
         v
Deploy to TLS endpoints
         |
         v
Monitor serving certificate & expiry
         |
         +---- Renew/rekey -> test -> rotate -> old-version cleanup
         |
         +---- Incident -> revoke/replace -> investigate
         |
         v
Retire certificate and key safely
~~~

### Every Step Needs an Owner

- **Domain owner:** maintains DNS/CA validation.
- **PKI/security team:** issuer, algorithms, policy, and private-key protection.
- **Platform team:** Key Vault, gateways, ingress, rotation.
- **Service owner:** endpoint behavior and client compatibility.
- **SRE/on-call:** alerting, runbooks, rollback, and incident response.

**Never let production certificates depend on a former engineer's personal email.** Ownership, renewal automation, and alert routing must belong to organizational operational processes.

## 13. Inventory: To Renew, You Must Know What You Are Running

Minimum inventory table:

| Field | Example |
|---|---|
| Domain/FQDN | api.example.com |
| Environment | production |
| TLS endpoint | Front Door custom domain |
| Upstream/backend TLS | Application Gateway → AKS ingress |
| Issuer | Public CA / corporate CA |
| Certificate SAN | api.example.com |
| Validity | Not Before/Not After from the actual cert |
| Store/reference | Key Vault certificate/secret version or managed cert |
| Owner | Platform/SRE team |
| Renewal mode | Managed automatic / automated BYOC / manual |
| Alert channel | On-call + security |
| Rotation test date | Last verified date |
| Blast radius | Hostnames/apps sharing the same certificate |

### Why Track Multiple Hops in Inventory?

An application may use one certificate at Front Door and a **different backend certificate** at Application Gateway/AKS. Probing from the public internet only inspects the edge cert; backend certificates can silently approach expiration unless every TLS hop is inventoried.

## 14. Azure-Managed or Self-Managed Certificates?

Two common strategy groups:

| Approach | Benefits | What to check |
|---|---|---|
| **Azure-managed certificate** | Azure handles issuance/renewal on supported endpoints | Domain eligibility, SKU, SAN/wildcard support, renewal dependencies, vendor behavior |
| **BYOC (bring your own certificate)** | Organization controls CA, domains, private key policy, and lifecycle | Key Vault, renewal, service sync, networking/IAM, PFX handling |
| **Internal/private CA** | Fits mTLS and internal PKI when clients are provisioned with trust | Trust anchors, distribution, CRL/OCSP, governance |

### Selection Rules

- For public custom domains on services with full managed TLS support, managed certificates usually reduce manual work.
- For specific issuers, mTLS, wildcards, or strict key-protection policies, BYOC may be required.
- For backend private FQDNs or internal clients, an internal CA and dedicated trust management may be needed.

**There is no single “Azure certificate” that works identically across every service.** Front Door, App Service, Application Gateway, and AKS each have distinct issuance, import, domain-binding, Key Vault integration, and renewal mechanisms.

## 15. Certificate Authorities and Domain Validation

To have a public CA issue a certificate for **api.example.com**, the requester must prove domain control via a CA-supported method, such as:

- **DNS validation:** creating required TXT or DNS records.
- **HTTP validation:** serving verification tokens at a standard path/host per product.
- **Email/domain-based method:** per CA and current policy.
- **ACME challenges:** HTTP-01 or DNS-01 per CA/integration.

### Process

~~~text
Domain owner
    |
    +-- Authorize issuance request
    +-- Prove DNS/HTTP control
    |
    v
CA issues signed certificate
    |
    v
Key Vault / managed TLS endpoint
    |
    v
HTTPS serving validation
~~~

Domain validation can fail due to missing CNAME/DNS TXT records, DNS propagation, broken DNS delegation, blocked web routes, CAA policies, or domain ownership changes.

### Wildcards and DNS-01

In standard ACME usage, **DNS-01** is required for wildcard certificates; never assume HTTP-01 satisfies wildcard validation. When automating DNS updates, restrict the updater identity to the required DNS zone rather than granting subscription Owner.

## 16. CSRs and Private Keys

A **CSR (Certificate Signing Request)** contains the public key and identity metadata evaluated by the CA; it is signed using the requester's private key.

~~~text
Generate private key  ---- never export carelessly ----+
       |                                               |
       v                                               |
Create CSR (public key + requested names)              |
       |                                               |
       v                                               |
CA validates & signs                                   |
       |                                               |
       v                                               |
Leaf certificate + chain                               |
       |                                               |
       +---- paired with same private key -------------+
       |
       v
TLS endpoint
~~~

### Questions When Generating Keys

1. Who generates the key: Azure Key Vault, HSM, CA, pipeline, or managed certificate service?
2. Is the key **exportable**, and does the target service require an exportable PFX?
3. Under what policy is the key protected/backed up?
4. Should we rekey on every renewal?
5. Which domain/workload/issuer does the key belong to?
6. If compromised, how quickly can all endpoints using this key be replaced?

**A CSR does not contain the private key**, whereas a PFX/PKCS#12 file usually **can contain the private key** and must be protected like a secret.

## 17. RSA, ECDSA, and Client Compatibility

Common public-key algorithms for TLS certificates include **RSA** and **ECDSA/EC**. The choice impacts compatibility, performance, and security policy.

| Criterion | RSA | ECDSA/EC |
|---|---|---|
| Client support | Broad, depending on key size/policy | Strong on modern clients; verify legacy clients |
| Key/signature size | Larger for equivalent security level | Smaller |
| Policy/CA | Both CA and endpoint must support | Both CA and endpoint must support |
| Azure gateway support | Per SKU/configuration | Per SKU/configuration |
| Rotation capability | Depends on platform and key management | Depends on platform and key management |

Never hardcode a key type requirement from one system before testing all clients. Choose algorithms, key sizes/curves, and hashes based on current policy and **CA + Azure TLS endpoint + client** support.

### Do Not Reuse Keys Indefinitely

Even if a certificate is renewed with the same key pair, a periodic **rekey** strategy limits exposure if a private key is leaked. However, changing keys can affect certificate pinning or private-key consumers, so test beforehand.

## 18. Certificate Formats: PEM, DER, PFX/PKCS#12

| Format | Typically contains | Notes |
|---|---|---|
| **PEM** | Base64-encoded cert/public key/private key with headers | Check whether a specific file contains a private key |
| **DER** | Binary ASN.1 encoding of cert/key | An encoding format; does not confer trust |
| **PFX/PKCS#12** | Container holding cert chain and private key | Password, access control, and protection as a secret |
| **JKS** | Java-specific keystore format | Can be converted to PKCS12 as needed |
| **PKCS#11/HSM** | Interface to a protected private key | Not exportable to PFX by default |

Example PEM certificate:

~~~text
-----BEGIN CERTIFICATE-----
... public certificate contents ...
-----END CERTIFICATE-----
~~~

Example PEM private key (never print real contents):

~~~text
-----BEGIN PRIVATE KEY-----
... confidential data, NEVER put in Git/logs ...
-----END PRIVATE KEY-----
~~~

**A `.pem` extension does not guarantee safety.** If it contains a private key, it is still confidential secret material.

## 19. Azure Key Vault: Certificates, Keys, and Secrets

**Azure Key Vault** provides distinct object types with different roles:

~~~text
Azure Key Vault
       |
       +-- Certificates
       |     Certificate metadata, X.509 public part,
       |     issuer/renewal policy and versions
       |
       +-- Keys
       |     Cryptographic key material/operations,
       |     optionally HSM-backed/non-exportable
       |
       +-- Secrets
             Arbitrary secret values; certificate
             backing secret may represent PFX/PEM
             depending on key/export policy
~~~

When creating/importing a **Key Vault certificate**, the service links corresponding **key** and **secret** objects sharing the certificate identity/version per Key Vault mechanics. **Never assume every certificate has an exportable private key in its backing secret**: exportability policy, key/HSM type, and creation method dictate this.

### Read Permissions Differ

- Permission to view **certificate metadata** does not automatically grant permission to fetch the private-key-bearing secret.
- A gateway referencing a **Key Vault secret** may require **get secret**, not just certificate read.
- Azure management **Reader** on a resource group does not inherently read Key Vault data-plane secrets.

Use Azure RBAC or Key Vault access policies according to the vault's configured model and organizational policy. Never grant Key Vault Administrator to a runtime just to read a certificate.

## 20. Certificate Policy in Key Vault

When managing certificates via Key Vault, policies can define:

- **Issuer** or self-signed/CA-integrated mode per service.
- Subject and **SANs** per supported capabilities.
- **Key type/size/curve**, exportability, and key reuse.
- Validity period per issuer/policy.
- **Lifetime actions**: notifications or auto-renew where issuer/integration supports it.
- Secret content type such as PFX/PEM per workflow.
- Enabled/disabled state, versions, and expiration metadata.

### Self-Signed vs. Public CA-Signed

Self-signed certificates generated in Key Vault **are not trusted automatically by public browsers**. They can be used for labs or internal PKI where trust is explicitly managed, but never attach a self-signed cert to a public website and tell users to disable validation.

### Conditional Auto-Renew

Key Vault can only auto-issue/renew when **issuer configuration and certificate policy** support that path. If a certificate is imported from an external CA without an integrated renewal workflow, Key Vault will not call the CA to fetch a new PFX simply because expiration approaches.

**A lifetime action sending an email/notification does not mean the certificate was renewed or deployed to Azure gateways.**

## 21. Key Vault Certificate Versions and Secret Versions

A certificate can progress through versions:

~~~text
Vault certificate: api-tls
    |
    +-- version V1: expires earlier
    |
    +-- version V2: issued/renewed
    |
    +-- version V3: rekeyed and renewed
~~~

When a service integrates with Key Vault, know how it references the certificate:

- **Versionless identifier**: can follow new versions per service integration mechanics.
- **Version-specific identifier**: pinned to one version; requires updating the reference on rotation.
- **Uploaded PFX**: gateway may retain an uploaded snapshot and never fetch new Key Vault versions automatically.

### Dangerous Trap

Key Vault showing valid certificate V2 does not mean Front Door/Application Gateway/Ingress is serving V2. **Verify the actually served certificate at the live TLS endpoint** after rollout and cache/propagation.

## 22. Exportable vs. Non-Exportable Keys

A **non-exportable key** fits cryptographic/HSM workflows where the private key must never leave the boundary. However, many TLS endpoints accept certificates as a **PFX containing the private key**, especially in traditional BYOC workflows.

### Design Principles

1. If the endpoint requires a PFX/private key, do not choose a non-exportable key expecting Key Vault to yield a PFX with key material.
2. If security policy mandates a non-exportable key, choose a service/integration supporting **remote signing/handshakes without key export**, or adjust the architecture.
3. When importing an exportable PFX, enforce tight permissions, auditing, and retention; avoid downloading files onto laptops.
4. Managed TLS at the edge can reduce the need for your organization to distribute private keys directly.

**You cannot make a non-exportable private key exportable by renaming a file extension.** Exportability is determined by key type and policy at creation/import time.

## 23. Managed Certificates on Azure App Service

**Azure App Service** provides TLS configuration paths for custom domains, including **App Service managed certificates** in eligible scenarios alongside imported/selected certificates.

~~~text
Public DNS custom domain
       |
       v
Azure App Service hostname binding
       |
       +-- App Service managed certificate (if eligible)
       |
       +-- Imported/BYOC certificate
       |
       v
HTTPS client traffic
~~~

### Advantages of Managed Certificates

- Eliminates manual issuance, renewal, and private-key file management in the app.
- Integrates with hostname bindings and platform TLS termination.
- Reduces risk of missed replacements while domains/bindings/platform remain eligible.

### Never Assume Universal Applicability

Check **SKU/plan, custom domain ownership/validation, wildcard support, hostname type, TLS bindings, and lifecycle** against current App Service documentation. Never treat an App Service managed certificate as a general-purpose cert you can export to AKS or a Java truststore.

### What to Monitor

- Hostname bindings have not changed unexpectedly.
- Domain validation/DNS remains valid.
- Live HTTPS on the custom domain presents the right chain and Not After.
- Managed renewal shows no warnings or pending states.

## 24. App Service BYOC and Key Vault

When using certificates from a custom CA/issuer, App Service provides import/management paths, including Key Vault integration flows per feature/plan.

~~~text
Approved CA
     |
     v
Certificate + private key (protected PFX)
     |
     v
Azure Key Vault or App Service certificate store
     |
     v
App Service custom hostname + TLS/SSL binding
     |
     v
Client receives server certificate
~~~

### Key Distinctions

- **Uploading/importing a certificate** may create a certificate resource in App Service; not every Key Vault change syncs instantaneously.
- **App Service Key Vault references for app settings** (for reading secrets) are not the same as **TLS certificate binding**. They are separate features.
- If using externally managed certificates, renewal automation must include **re-import/sync/binding** per supported workflow.

### Deployment Slots

Staging and production slots have separate hostname/certificate bindings and application settings. Before swapping, verify custom domains, TLS bindings, and sticky settings. Never assume a code swap automatically moves certificates onto the right hostnames in every topology.

## 25. Azure Front Door: TLS at the Edge

**Azure Front Door** handles global HTTP(S) ingress at the edge; custom domains can use **Front Door-managed certificates** or **BYOC** depending on SKU/feature support.

~~~text
Internet users
      |
      | TLS #1: public custom domain
      v
Azure Front Door (managed cert or BYOC)
      |
      | TLS #2 to origin if HTTPS is configured
      v
Application Gateway / App Service / AKS origin
~~~

### Two Certificates, Two Checks

1. **Client → Front Door:** certificate for the public hostname, e.g., **api.example.com**.
2. **Front Door → origin:** origin certificate and hostname validation per origin configuration.

A valid public certificate does not guarantee the origin certificate is valid. If the backend/origin certificate expires, Front Door can report origin TLS health failures even while clients see a valid edge cert.

### Managed Certificates

When Front Door issues and renews certs, your organization must still maintain DNS/domain validation and monitor custom domain status. **Managed does not mean dropping inventory or monitoring.**

### BYOC

When using Key Vault-backed certificates, ensure proper Key Vault integration, identity/permissions, certificate format, and rotation policy. Check SKU/docs for how new versions are picked up, polling intervals, and provisioning state changes.

## 26. Azure Application Gateway: Listeners and Backend TLS

**Application Gateway** typically uses HTTPS listeners for client connections, routing rules, and backend HTTP settings for backend pools.

~~~text
Client
   |
   | HTTPS #1
   v
Application Gateway HTTPS listener
   | certificate for public/internal host
   |
   +-- Optional WAF/routing
   |
   | HTTPS #2 / re-encryption if configured
   v
Backend server / AKS ingress / App Service
   | backend certificate & hostname validation
   v
Java app
~~~

### What Must Be Configured

- Listener hostname and certificate matching SAN/SNI.
- TLS policy/minimum version/cipher suite per SKU.
- Backend protocol **HTTP or HTTPS** per security requirement.
- Backend hostname/SNI matching the backend certificate.
- Trust settings/backend trusted root certificates when using a private CA.
- Health probe host/headers/path matching the backend.

**Configuring an HTTPS listener does not automatically encrypt App Gateway → backend traffic.** When end-to-end TLS is required, verify every hop.

## 27. Application Gateway Key Vault Integration

On supported configurations/SKUs, Application Gateway can reference a **certificate stored in Azure Key Vault** instead of relying solely on manual PFX uploads.

~~~text
Key Vault certificate
    |
    v
Key Vault backing secret (PFX with private key, if compatible)
    |
    | Key Vault secret ID/reference
    v
Application Gateway (user-assigned managed identity)
    |
    | authorized secret GET + approved network path
    v
HTTPS listener serves certificate
~~~

### Essential Prerequisites

1. Application Gateway SKU/version must support Key Vault integration.
2. A **user-assigned managed identity** is attached per supported workflow.
3. The identity has permission to access the **backing secret** via matching RBAC/access policy.
4. The certificate has an **exportable/usable PFX** private key per integration requirements.
5. Key Vault networking/firewall/Private Endpoint/DNS permit access from the service under a supported architecture.
6. The Key Vault resource/secret is not disabled, deleted, or expired.
7. If using a versionless secret ID, verify the actual mechanism and schedule for fetching new versions.

### Common Mistakes

- Granting only **Certificate Reader** when the gateway needs to fetch the backing secret.
- Choosing a **non-exportable** key while expecting a PFX containing the private key.
- Referencing a **version-specific secret ID**, renewing V2 while the gateway keeps serving V1.
- Vault networking blocking access from the gateway.
- Checking Key Vault V2 without verifying the actual certificate served on the listener.

**Never assume a fixed sync delay across all deployments.** Consult SKU/feature docs, check listener status, and actively verify via a real TLS handshake after rotation.

## 28. AKS and TLS Termination Points

A Java/Spring Boot app running in AKS can receive traffic in several ways:

- HTTPS terminates at **Azure Front Door/Application Gateway**, then forwards to Pods over HTTP or HTTPS.
- HTTPS terminates at an **Ingress controller** inside/attached to AKS.
- HTTPS terminates at a **Gateway API implementation** or supported application proxy.
- The Java Pod serves HTTPS directly, suitable for certain end-to-end or mTLS models.
- A **service mesh** provides internal TLS/mTLS per mesh configuration.

~~~text
                      Internet
                         |
                         v
                    Front Door
                         |
                 HTTPS / origin cert
                         v
                    App Gateway
                         |
                 HTTPS / internal cert
                         v
                     AKS Ingress
                         |
                 HTTP / HTTPS / mTLS
                         v
                    Spring Boot Pod
~~~

### Choosing Where to Terminate TLS

| Location | Pros | Key considerations |
|---|---|---|
| **Front Door** | Edge HTTPS, routing/WAF per SKU | Origin TLS and separate domain validation |
| **Application Gateway** | L7 ingress, Azure-integrated WAF/routing | Listener and backend TLS configuration |
| **AKS ingress** | Kubernetes-native cert/host control | Secret rotation and controller reloads |
| **Java Pod** | End-to-end TLS to app, direct trust control | Keystore distribution, CPU, cert hot reload |
| **Service mesh** | Workload-to-workload mTLS | CA/trust rotation, mesh policy, operational complexity |

Never deploy multiple TLS terminators without diagramming them clearly: each termination point is a **trust boundary** and may carry a different certificate.

## 29. Kubernetes TLS Secrets: Structure and Risks

For Ingress controllers supporting Kubernetes Secrets, a TLS Secret typically looks like:

~~~yaml
apiVersion: v1
kind: Secret
metadata:
  name: catalog-tls
  namespace: catalog-lab
type: kubernetes.io/tls
data:
  tls.crt: BASE64_LEAF_AND_CHAIN_PLACEHOLDER
  tls.key: BASE64_PRIVATE_KEY_PLACEHOLDER
~~~

**This is an illustrative manifest; the placeholders are not valid deployable Base64.** In labs, use an approved cert tool/controller to generate the Secret and never commit private keys to Git.

### Key Points

- **tls.crt** typically needs the leaf certificate and intermediates in the order expected by the ingress controller.
- **tls.key** holds the private key matching the leaf.
- Ingress resources reference Secrets within the same namespace per controller rules.
- Namespace/RBAC governs Secret read access; not everyone who can view Deployments should read Secrets.
- Base64 is **encoding**, not security or encryption.
- Encryption at rest for Kubernetes Secrets and etcd access must be controlled.

### Updating the Secret

Do not assume every controller version reloads at the right time. Some controllers watch Secrets and update certificates dynamically; other setups require a reload/rollout. **Testing the certificate served by the endpoint** is the acceptance test, not merely seeing the Secret change.

## 30. cert-manager: Automating Certificates in Kubernetes

**cert-manager** is a popular Kubernetes controller for managing certificate issuance and renewal via **Issuer/ClusterIssuer** configurations and issuers (ACME, CA, Vault, and supported integrations).

~~~text
Kubernetes Certificate resource
           |
           v
cert-manager controller
           |
           +--> Issuer / ClusterIssuer
           |        |
           |        +--> ACME/public CA
           |        +--> Internal/private CA
           |
           v
TLS Secret containing issued certificate/key
           |
           v
Ingress/Gateway controller uses Secret
~~~

### What cert-manager Handles

- Tracks certificate requests and expiration.
- Automates CSR/challenge orchestration per issuer.
- Renews ahead of expiration per configuration.
- Updates the Kubernetes Secret when a new version is issued.
- Emits status/events to monitor issuance failures.

### What Still Needs Design

- DNS solver permissions and protecting API tokens for DNS-01.
- Issuer config, allowed domains, CAA/validation.
- Whether the ingress controller actually reloads the new cert.
- Private-key rotation policy, certificate chains, and CA trust.
- Controller HA, ACME quotas/rate limits, and disaster recovery.
- Version compatibility across Kubernetes, ingress, cert-manager, and issuers.

**cert-manager is not a universal Azure-managed TLS certificate service for all endpoints**; it manages resources within Kubernetes and the external issuers configured on the cluster.

## 31. AKS Key Vault Secrets Store CSI Driver

In AKS, the **Secrets Store CSI Driver** with the Azure Key Vault provider can mount secrets/certificates/keys into Pods as supported.

~~~text
Azure Key Vault certificate/secret
           |
           | Workload identity / managed identity
           v
AKS Key Vault CSI provider
           |
           +--> Pod-mounted files
           |
           +--> Optional synced Kubernetes Secret
           |    if configured/supported
           v
Ingress or Java application
~~~

### Questions When Using It for TLS Certificates

1. Is the Key Vault certificate in the right format with a usable private key?
2. Which identity does the CSI provider use to access Key Vault?
3. Which files are mounted in the Pod: **certificate, private key, PFX**?
4. If ingress only reads a Kubernetes Secret, is **secret sync** needed?
5. Is the synced Secret created only when a Pod mounts it, and what is its lifecycle?
6. Is auto-rotation enabled, and what are its interval/semantics?
7. When mounted files change, does Java/ingress actually reload the certificate?
8. Do Key Vault private networking and DNS work from the nodes/pods?

### The Refresh Crucial Point

CSI rotation can update volume contents or synced Secrets per supported behavior, **but Spring Boot/Tomcat/Netty do not automatically reload a keystore just because a file changed on disk**. You need reload logic or a controlled restart. Never assume “Key Vault has V2” is enough.

## 32. AGIC, Gateway Controllers, and Ingress Ownership

When using **Application Gateway Ingress Controller (AGIC)** or an Azure Gateway integration, TLS configuration may be co-managed by the gateway, controller, and Ingress resources.

### Avoid Conflicting Ownership Models

~~~text
Team A updates Application Gateway certificate directly
        |
        v
Controller reconciles gateway from Kubernetes desired state
        |
        v
Manual changes may be overwritten or cause drift
~~~

Choose a single **source of truth** for listener/certificate bindings:

- IaC/Bicep/Terraform with clear controller boundaries.
- Ingress/Gateway resources if the controller truly owns them.
- Key Vault certificate/secret versions per supported integration.

Never edit both the Azure Portal and Kubernetes annotations for the same listener without understanding precedence and reconciliation. Verify integration version and ownership before rolling out rotation.

## 33. Is HTTPS at the Edge Alone Enough?

An architecture might look like:

~~~text
Browser --HTTPS--> Front Door --HTTP--> Backend
~~~

or:

~~~text
Browser --HTTPS--> Front Door --HTTPS--> Application Gateway
        --HTTPS--> AKS ingress --HTTP/mTLS--> Java Pod
~~~

**There is no one-size-fits-all answer for every environment.** Analyze:

- Does compliance mandate per-hop encryption?
- Do hops traverse public networks, private VNets, or cross-region links?
- Who manages origin certificates and trust chains?
- Does backend TLS termination strip client authentication context?
- Can client-identity headers be spoofed if the backend is reachable directly?

### Never Trust Self-Reported Client Headers Blindly

If the edge authenticates mTLS and forwards a header like **X-Client-Cert**, the backend should only trust that header when the path to the edge is locked down and direct client-supplied headers are stripped. **An HTTP header alone does not prove the client presented a valid certificate.**

## 34. Java TLS: Truststores and Keystores

Java applications use **JSSE** or HTTP libraries/frameworks layered over the JVM TLS stack (implementation-dependent). Two key concepts:

| Component | Contents | Purpose |
|---|---|---|
| **Truststore** | Trusted root/intermediate CAs or trust anchors | Verifies server/client certificates |
| **Keystore** | Local party's private key and certificate chain | Presents a certificate for server TLS or mTLS |

### Example Flow

~~~text
Spring Boot Java client
       |
       +-- Truststore: corporate CA to verify api.internal
       |
       +-- Keystore: client private key + cert if using mTLS
       |
       v
HTTPS API
~~~

### Default JDK Truststore

Many public HTTPS endpoints verify against root CAs built into the JDK truststore. Avoid importing leaf certificates of every Azure service into your truststore without clear justification. For internal/private CAs, configure the proper trust anchors per policy.

**Never use a trust-all TrustManager/HostnameVerifier** or “insecureSkipVerify” settings in production to bypass TLS errors.

## 35. Spring Boot HTTPS Server and Keystores

A Spring Boot application can serve HTTPS directly via SSL bundles or server SSL properties supported by your Spring Boot version.

Example **server.ssl** configuration with a PKCS12 file provisioned on the container filesystem (only when the Java endpoint terminates TLS directly):

~~~yaml
server:
  port: 8443
  ssl:
    enabled: true
    key-store: "file:/run/tls/server-keystore.p12"
    key-store-type: PKCS12
    key-store-password: "${TLS_KEYSTORE_PASSWORD}"
~~~

### Prerequisites

- **server-keystore.p12** must contain a valid key pair + certificate chain.
- **TLS_KEYSTORE_PASSWORD** must be supplied via secret injection/Key Vault integration, never committed.
- Configure key alias/key password if required by the keystore.
- Ingress/Service/probes must target the right port and protocol.
- Verify hostname, cert validity, trust, and Spring Boot version.
- Manage restarts/hot reloads when the file updates; **server.ssl** does not guarantee automatic hot-reload across all runtimes/versions.

If TLS already terminates at Application Gateway and backend HTTP meets policy, every Java Pod may not need direct HTTPS. However, if compliance requires end-to-end TLS, design full backend trust.

## 36. Spring Boot SSL Bundles

Modern Spring Boot versions offer **SSL bundles** to group trust material/keystores/PEMs under a named configuration reusable across supported components.

~~~text
Spring Boot SSL bundle: partner-api-client
        |
        +-- Trust material (trusted CA)
        +-- Client key/cert (for mTLS, if needed)
        |
        v
RestClient / WebClient / service connection
   (only if the client integration supports bundles)
~~~

### Benefits

- Separates TLS settings from business logic.
- Reusable across supported clients and servers.
- Reduces reliance on mutating the global JVM truststore for all outbound calls.

### Limitations

- Not every Azure SDK, JDBC driver, gRPC client, or Redis client natively understands Spring SSL bundles.
- Spring Boot SSL bundle properties **do not automatically reconfigure Azure service client HTTP transports** unless the integration wires the bundle.
- Bundle hot-reload/swap behavior and PEM/PKCS12 support vary by Spring Boot version.

When using an Azure SDK client builder, verify whether the SDK's **HttpClient/SSL context** supports explicit trust configuration rather than setting a Spring property and assuming it took effect.

## 37. Java TLS Clients: Never Replace HTTPS with HTTP

In a Java SDK or HTTP client, server certificate verification requires:

1. Using **https://** URLs/endpoints.
2. Keeping hostnames/FQDNs matching certificate SANs.
3. Trusting CA chains via managed JDK/system/custom truststores.
4. Never disabling peer or hostname verification.
5. Sending mTLS client certificates only when required by the service.

### A Dangerous Mistake

An app hits **javax.net.ssl.SSLHandshakeException** against a Key Vault private endpoint, and an engineer switches the URL to HTTP or configures a “trust-all” HTTP client. The Azure Key Vault data plane requires HTTPS; doing so neither fixes the real fault nor preserves the security model.

### Pairing with Entra ID

Entra tokens and TLS solve different problems: TLS protects the transport and authenticates the server; tokens authenticate client identity and API permissions. Never treat **having an access token** as an excuse to skip hostname verification.

## 38. Private Endpoint, DNS, and SNI

Azure Private Endpoint creates a private network path to a supported Azure service. However, **clients should continue connecting using the official FQDN** per service documentation:

~~~text
Java client:
  https://vault-name.vault.azure.net
         |
         | DNS resolves via approved private DNS path
         v
  Private Endpoint IP
         |
         | TLS SNI/hostname = vault-name.vault.azure.net
         v
  Azure Key Vault service
~~~

### Why Never Hardcode Private IPs?

- Certificate SANs match FQDNs, not private IPs.
- SNI tells the service which certificate/route to select.
- Private IPs can change when endpoints are recreated.
- It breaks failover and complicates auditing.

**A Private Endpoint is not a VPN, TLS certificate, or IAM role.** It is strictly a networking component. Private DNS, NSGs/UDRs/firewalls, and identity must still be configured properly.

## 39. Inspecting with OpenSSL: Public Handshake (Read-Only)

Run these commands **against hosts/endpoints you are authorized to test**; they only perform a TLS handshake and read certificates without modifying Azure resources.

~~~bash
HOST="api.example.com"

openssl s_client \
  -connect "$HOST:443" \
  -servername "$HOST" \
  -verify_return_error \
  -showcerts < /dev/null
~~~

### What Should You Observe?

- Leaf certificate for the real hostname.
- Issuer and intermediate certificates.
- Negotiated TLS version and cipher.
- Chain verification errors (if any).
- Which certificate version the server is currently serving.

### Limitations

- Specifying one `-servername` tests only one hostname/SNI from one network vantage point.
- Load balancers span multiple nodes/regions; a single connection does not represent every node.
- A “verify OK” certificate chain does not prove application authorization.
- Do not infer wildcards or other bindings are healthy from a single host check.

## 40. Checking Expiration and SANs with OpenSSL

Once you have a **public PEM certificate** extracted/saved per lab procedure:

~~~bash
openssl x509 -in leaf.pem \
  -noout -subject -issuer -dates -serial

openssl x509 -in leaf.pem \
  -noout -ext subjectAltName

openssl x509 -in leaf.pem \
  -noout -fingerprint -sha256
~~~

### Checking Remaining Validity Window

OpenSSL offers **`-checkend`**, checking whether a certificate expires within a given number of seconds:

~~~bash
# 30 days, read-only on public certificate:
openssl x509 -in leaf.pem -noout -checkend 2592000
~~~

Its exit code can feed an alert check, but production monitoring should inspect the **actual certificate served on the HTTPS endpoint**, not merely a PEM file in a local directory.

### Chain Validation

When you have a verified set of trusted CA files:

~~~bash
openssl verify \
  -CAfile approved-root-ca.pem \
  -untrusted intermediate-ca.pem \
  leaf.pem
~~~

**Never grab an arbitrary CA from the internet and mark it as a trusted root** just because a verify command failed. Check issuer, policy, trust store, and chain per security procedure.

## 41. SNI and Certificates Returned for the Wrong Hostname

A shared listener can serve multiple domains:

~~~text
api.example.com       -> cert A
admin.example.com     -> cert B
shop.example.com      -> cert C
          |
          v
       Same edge IP
          |
          v
 SNI selects certificate
~~~

### Diagnosis

Connecting directly to an IP or omitting SNI may return a different default certificate. Use:

~~~bash
openssl s_client \
  -connect "edge.example.com:443" \
  -servername "api.example.com" \
  -showcerts < /dev/null
~~~

Use this only when **edge.example.com** is an authorized endpoint address routing to that same listener; never treat the example as valid for arbitrary CDNs. The critical point is that **`-servername` must match the hostname under test**.

### DNS Cannot Substitute for a Certificate

Pointing a CNAME alias to Front Door/App Service does not automatically issue a certificate for that alias. You must add the custom domain binding/validation and ensure the SAN/managed cert covers it per service rules.

## 42. Java keytool: Truststore and Certificate Inspection

In the Java ecosystem, **keytool** inspects certificates and truststores. On supported Java runtimes:

~~~bash
# Read-only on a public certificate file:
keytool -printcert -file leaf.pem

# List lab keystore info with appropriate permissions:
keytool -list -v \
  -keystore truststore-lab.p12 \
  -storetype PKCS12
~~~

### Important Cautions

- Never pass keystore passwords on command lines where process listings or shell history can expose them.
- Never print PKCS12/private key dumps.
- Never directly edit the production JDK global **cacerts** to paper over an error.
- Use truststores with clear owners, CA policies, and rotation plans.

### Lab-Only Root CA Import Command

~~~bash
# WRITE to lab truststore, NEVER run against JDK system cacerts:
keytool -importcert \
  -alias approved-lab-root \
  -file approved-lab-root.pem \
  -keystore truststore-lab.p12 \
  -storetype PKCS12
~~~

Before importing, verify the root CA's fingerprint and issuer via a trusted channel. If an attacker supplies a rogue root CA, importing it puts every connection using that truststore at risk of spoofing.

## 43. TLS Handshake Errors in Java

| Symptom | Likely Cause | What to Check |
|---|---|---|
| **PKIX path building failed** | Untrusted CA chain or missing intermediate | Truststore, issuer, chain |
| **No subject alternative names matching** | Hostname missing from SAN | URL/FQDN/SNI, certificate SAN |
| **CertificateExpiredException** | Leaf/intermediate expired | Not After on every cert in chain |
| **CertificateNotYetValidException** | Not Before in the future or wrong system clock | UTC clock/NTP, validity |
| **handshake_failure** | TLS policy/cipher/clientAuth mismatch | Versions, suites, mTLS |
| **bad_certificate** | Client certificate/key/trust mismatch | Client keystore, CA, EKU |
| **UnknownHostException** | DNS or wrong hostname | Private DNS, resolver |
| **ConnectTimeoutException** | Route/port/firewall blocked | TCP, NSGs/UDRs, egress |
| **HTTP 401/403** | TLS succeeded; auth/app policy failed | Entra token, IAM, API permissions |

### Debugging TLS Without Leaking Secrets

JSSE supports diagnostics via **`javax.net.debug`** in some situations, but verbose handshake logs can include sensitive metadata and huge log volumes. Enable only in controlled environments, never publish logs carelessly, and disable it once investigation ends.

**Never lump every `SSLHandshakeException` under “import the cert into cacerts”.** Many errors stem from SAN/SNI/ciphers/mTLS rather than a missing trusted root.

## 44. Read-Only Azure CLI: Key Vault Certificate Inventory

With metadata read access to a lab Key Vault, you can run:

~~~bash
az account show \
  --query "{subscription:id,tenant:tenantId}" \
  -o json

az keyvault certificate list \
  --vault-name "<LAB_VAULT>" \
  --query "[].{id:id,enabled:attributes.enabled,expires:attributes.expires}" \
  -o table

az keyvault certificate show \
  --vault-name "<LAB_VAULT>" \
  --name "<LAB_CERT_NAME>" \
  --query "{id:id,enabled:attributes.enabled,expires:attributes.expires}" \
  -o json
~~~

### Security Notes

- These commands display **certificate metadata** without exporting the backing PFX/private key.
- Never run **`az keyvault secret show`** to fetch/download a certificate's private-key-bearing secret when you only need to check expiration.
- If the vault uses private networking, the machine running CLI needs a valid network path and DNS.
- The certificate list reflects the **vault** inventory; it does not prove the gateway is serving that version.

If the CLI returns **Forbidden**, check tenant, data-plane role/access policy, firewall, and service state. Never escalate permissions subscription-wide to bypass errors.

## 45. Read-Only Azure CLI: TLS Binding Metadata

For a lab Application Gateway with management-plane read permissions:

~~~bash
az network application-gateway ssl-cert list \
  --gateway-name "<LAB_GATEWAY>" \
  --resource-group "<LAB_RESOURCE_GROUP>" \
  --query "[].{name:name,secretId:keyVaultSecretId,state:provisioningState}" \
  -o table
~~~

This reveals listener certificate references as supported by your API/CLI version, but:

- It does not show the exact certificate being served across every frontend IP/node.
- It does not guarantee the gateway has refreshed a newly issued backing secret.
- Some attributes vary by gateway SKU/CLI version.
- You still must inspect listener/hostname/rule mappings.

### Full Verification Workflow

1. Check Key Vault certificate/secret version metadata.
2. Check gateway TLS certificate references and provisioning state.
3. Connect over HTTPS to the live frontend hostname with OpenSSL/curl.
4. Compare SAN, chain, fingerprint, and Not After.
5. Check backend/origin TLS health if applicable.

**Reading Azure metadata never replaces an end-to-end TLS handshake test.**

## 46. Java: Reading Expiration of a PEM Certificate (Without Private Key)

To inspect a **public X.509 certificate file** in Java, use standard JDK APIs:

~~~java
import java.io.FileInputStream;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;
import java.time.Duration;
import java.time.Instant;
import java.util.Date;

public final class CertificateExpiryLab {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "Usage: CertificateExpiryLab <public-cert.pem>");
        }

        CertificateFactory factory =
            CertificateFactory.getInstance("X.509");

        X509Certificate certificate;
        try (FileInputStream in = new FileInputStream(args[0])) {
            certificate = (X509Certificate) factory.generateCertificate(in);
        }

        Date now = new Date();
        certificate.checkValidity(now);

        Instant expiration = certificate.getNotAfter().toInstant();
        long daysRemaining = Duration.between(
            Instant.now(), expiration).toDays();

        System.out.println("Subject: " +
            certificate.getSubjectX500Principal().getName());
        System.out.println("Issuer: " +
            certificate.getIssuerX500Principal().getName());
        System.out.println("Not After: " + expiration);
        System.out.println("Days remaining (whole days): " + daysRemaining);
    }
}
~~~

### Important Limitations of This Example

- **`checkValidity()` only checks dates** on the leaf certificate; it does not verify chain, SAN, EKU, revocation, or private key validity.
- It neither requires nor reads a private key.
- It can throw `CertificateExpiredException`/`CertificateNotYetValidException`.
- `Duration.toDays()` truncates to whole days; production alerts should compute precise durations using UTC/NTP.
- If the file is a multi-certificate PEM bundle, **`generateCertificate`** as written reads only the first certificate and does not validate the whole chain.
- This inspects a **local file**, not whether an Azure endpoint is actually serving that certificate.

## 47. Renewal: Schedules and Alert Thresholds

Illustrative timeline ahead of expiration:

~~~text
T - 60 days: early alert / owner checks CA + domain validation
T - 30 days: renew/rekey and deploy to staging
T - 14 days: verify production listeners/origins
T -  7 days: escalate to on-call if new cert is still missing
T -  1 day : incident/contingency if expiration risk persists
T = 0      : endpoint must never serve an expired cert
~~~

**These milestones are operational examples**, not an Azure/CA SLA. For shorter certificate lifetimes, automate renewal and validation with proportional thresholds. For complex domain validations or long change windows, start earlier.

### Two Types of Expiry to Monitor

1. **Certificate inventory expiry:** Key Vault / CA / certificate manager reporting Not After of the stored version.
2. **Serving certificate expiry:** Not After actually presented by the public/internal endpoint during a client handshake.

Divergence between these two is a classic source of TLS outages.

## 48. Zero-Downtime Renewal Workflow

A safe workflow:

1. **Scope:** SANs, hosts, gateways, mTLS clients/backends, current fingerprint.
2. **Verify issuer/domain validation:** DNS/CAA, CA integration, owner.
3. **Generate new certificate:** follow key reuse vs. rekey policy.
4. **Store in approved location:** Key Vault certificate/secret or managed TLS service.
5. **Pre-deployment checks:** chain, hostname/SAN, EKU, Not Before/After, key pair, and format.
6. **Deploy to staging:** use authorized test hostname/traffic and test real clients.
7. **Update references/bindings:** versionless or pinned version per integration.
8. **Staged rollout:** gateway nodes/regions, ingress/controllers, or Pods.
9. **Verify serving fingerprint** across live endpoints, backend health, and metrics.
10. **Keep a valid rollback** option within the transition window.
11. **Retire old versions** once dependencies clear and retention/incident policies are met.

### A New Certificate Does Not Necessarily Break Existing Services

If a new cert keeps the same domain with a different public key, most public HTTPS clients keep working seamlessly when the chain is valid and no pinning is enforced. However, clients using certificate pinning, restricted CA trust, or explicit mTLS trust mappings may need updates first.

**Never delete V1 before confirming every consumer has moved off V1**; yet do not retain expired private keys indefinitely without purpose either.

## 49. Distinguishing Renewal, Reissue, Rekey, and Rotation

| Term | Meaning |
|---|---|
| **Renewal** | Obtaining a new certificate with fresh validity for the same or corresponding identity |
| **Reissue** | Re-issuing a certificate in cases like metadata corrections or issuer-driven updates |
| **Rekey** | Generating a new public/private key pair |
| **Rotation** | Switching workloads/endpoints to actively serve the new certificate/key |
| **Revocation** | CA marking a certificate untrusted via revocation mechanisms |
| **Retirement** | Decommissioning certificates, keys, and permissions once no longer needed |

### Key Takeaway

Renewing to create V2 in Key Vault is not yet **rotation** if the listener still serves V1. **Rekeying** differs from renewal because the private key changes; key changes can require separate keystore distribution and reloads.

## 50. CA Root/Intermediate Rotation: Harder Than Leaf Rotation

Replacing a **leaf certificate** usually needs no root trust store updates if the new CA chain remains trusted by clients. Replacing a **root or intermediate CA**, however, can break all clients that pin trust anchors or rely on private PKI.

~~~text
Old trust:
  Root A -> Intermediate A -> Server V1

New trust:
  Root B -> Intermediate B -> Server V2

Migration:
  Trust Root A + Root B temporarily on clients
       |
       v
  Deploy server V2/new chain
       |
       v
  Verify all clients
       |
       v
  Retire Root A trust after cutover
~~~

### CA Rollover Runbook

1. Inventory clients: JVMs, IoT, legacy OSes, partners, service meshes.
2. Distribute the **new trust anchor** before changing the server's CA chain.
3. Verify clients can validate the new chain.
4. Cut over the server certificate/issuer with a reasonable overlap window.
5. Watch handshake errors and auth failures.
6. Remove old trust anchors per risk assessment and approval schedule.

**Never remove the old root CA from all truststores at once before migration finishes**, nor keep a compromised root just to avoid errors.

## 51. Certificate Pinning and Rotation Risks

Some mobile apps, IoT devices, or B2B integrations use **certificate/public key pinning**. Pinning can cause clients to reject a new certificate even when the public CA and chain are completely valid.

### Common Failure Case

~~~text
Client pins fingerprint of leaf V1
        |
        v
Server renews + rekeys -> leaf V2
        |
        v
Client rejects V2 despite trusted CA
~~~

### Principles

- Use pinning only when security requirements and operational maturity justify it.
- Always include backup pins or a safe pin-rotation mechanism.
- Never pin a soon-to-expire leaf certificate without an app update mechanism.
- Test older app versions and offline clients before rekeying.
- Never degrade security by disabling all TLS verification when a pin mismatches.

Pinning is not mandatory for HTTPS; deploying it without a rotation plan can cause self-inflicted outages on hard-to-update devices.

## 52. Revoking a Certificate When a Private Key Is Compromised

When a private key appears compromised, routine renewal is **insufficient**. Execute an incident process:

1. **Trigger incident response** and identify affected certificates/private keys.
2. **Block unauthorized access** to PFXs, Key Vault secrets, CI artifacts, and storage.
3. **Generate a new key pair** in an approved system.
4. **Request a new certificate from the CA** with the proper domain/SANs.
5. **Deploy and verify** the new cert/key across all TLS endpoints.
6. **Request the CA to revoke the compromised certificate** per issuer procedure.
7. **Revoke related permissions/credentials**, inspect logs/audits, and trace the leak source.
8. Handle copies/backups containing the old key per retention/security policy.
9. Close the incident after confirming clients trust the new cert and the risk is contained.

### Does Revocation Replace Rotation?

**No.** Clients handle revocation states inconsistently due to OCSP/CRL/caching/soft-fail policies. When a key is exposed, you must **replace the certificate/key on endpoints** and manage trust explicitly—never just submit a revocation request while continuing to serve the compromised cert.

## 53. OCSP, CRL, and Revocation Checking

**Certificate Revocation Lists (CRL)** and **Online Certificate Status Protocol (OCSP)** are mechanisms used in the CA/client ecosystem to signal or verify revocation status under specific configurations.

### Things to Understand Accurately

- Not all clients, browsers, or JVMs handle revocation checks identically.
- OCSP stapling and OCSP/CRL availability depend on endpoint, issuer, and client.
- Systems may soft-fail when revocation status is unreachable, depending on policy.
- Revocation propagation and caching are not instantaneous everywhere.
- Private PKI environments must design CRL/OCSP hosting and reachability themselves.

Never describe **revocation as a guarantee that every client immediately rejects a compromised cert**. Private key compromise requires key replacement, server rollout, client trust policy, and incident management together.

## 54. TLS Expiry Alerts and Signal Management

A multi-layered monitoring strategy:

~~~text
Key Vault certificate expiration metadata
          |
          +--> Azure monitoring/event/alert path
          |
Public HTTPS endpoints
          |
          +--> External HTTPS certificate probes
          |
Internal origin/AKS endpoints
          |
          +--> Internal TLS certificate probes
          |
          v
SRE alerting + ticket + on-call + escalation
~~~

### Signals to Track

| Signal | Why it is needed |
|---|---|
| **Days until expiry** | Renew ahead of deadline |
| **Serving cert fingerprint** | Proves rotation reached the live endpoint |
| **SAN/hostname mismatch** | Detects wrong certificate bindings |
| **Chain validation failures** | Catches missing intermediates/CA trust |
| **TLS handshake error rate** | Detects protocol/trust/clientAuth errors |
| **Key Vault certificate operation status** | Catches renewal/import failures |
| **Key Vault/Managed Identity access errors** | Gateway failing to fetch secret |
| **Gateway/ingress reload state** | Confirms certificate V2 was loaded |
| **Backend origin TLS health** | Catches expired certs on internal hops |
| **Domain validation/DNS status** | Renewal automation depends on DNS |

### Do Not Rely Only on “30 Days Remaining” Alerts

Key Vault may have auto-renewed V2 while the endpoint is still serving V1. In that case, Key Vault alerts stay quiet while internet clients are about to fail. **Maintain at least one independent probe against every live HTTPS endpoint**, plus internal probes for backend hops where security boundaries permit.

## 55. Using Azure Monitor / Event Grid Effectively

Azure Key Vault offers event/monitoring integrations for certificate lifecycles depending on vault/resource/feature type. You can wire **Event Grid → Azure Function/Logic App → Teams/on-call/ticketing** or Azure Monitor alerts.

~~~text
Key Vault certificate lifecycle event
           |
           v
Event Grid subscription
           |
           v
Function / Logic App
           |
           +--> Ticket + assigned owner
           +--> On-call notification
           +--> Optional approved renewal automation
~~~

### Alert Resilience

- Verify actual supported **event types** on your Key Vault/resource.
- Include retries and DLQ/error handling where supported.
- Attach certificate resource ID, version, event timestamp, and owner.
- Avoid routing alerts solely to an unmonitored personal inbox.
- Automated renew/deploy is an **impactful write operation**, requiring protected identities and idempotency checks.
- Pair events with scheduled endpoint probes in case an event subscription fails.

Never assume a “near expiry” event means the CA automatically issued a new certificate. Often the event is just a signal for the owner to act.

## 56. Costs and Operational Risks of TLS

| Component | Cost / Risk Driver |
|---|---|
| **Public CA certificates** | CA/validation fees per issuance model |
| **Managed TLS services** | SKUs/tiers/request/gateway charges per product |
| **Azure Key Vault** | Operations, vault/key/HSM types, and networking |
| **Private Endpoints** | Endpoint/network/data-processing charges per pricing |
| **Application Gateway/Front Door** | Gateway/edge processing and egress per pricing |
| **AKS cert-manager/CSI** | Controllers/Pods, secrets, DNS challenges, operations |
| **Azure Monitor/Log Analytics** | Monitoring ingestion/retention/probes |
| **Incident downtime** | SLO breaches, customer support, lost revenue |

### Why Is Automation Worth Investing In?

A single outage from an expired cert typically costs far more than automating inventory, renewal, and deployment. However, buggy automation can issue certs for wrong domains, delete secret versions, or misconfigure listeners; therefore **idempotency, least privilege, staged rollouts, and verification** are essential design requirements.

### Do Not Cite Fixed Prices

Azure Key Vault operation fees, gateway tiers, and public CA certificate prices vary by purchasing channel, region, and time. Estimate via the **Azure Pricing Calculator** and current CA contracts instead of relying on an invented USD table.

## 57. Protecting Private Keys and Supply Chain Safety

### Common Places Where PFX/Private Keys Leak

- Git repositories or commit history.
- Docker image layers.
- Kubernetes Secret manifests in source control, even when Base64-encoded.
- CI logs, deployment variables, IaC state/plans.
- Personal file shares or email attachments.
- Debug dumps, heap dumps, or application logs.
- Developer laptops or unencrypted backups.

### Practices

1. Prefer managed certificates/Key Vault/HSM where requirements and integrations support them.
2. When PFX export is unavoidable, minimize frequency/scope, require approval/audits, and securely wipe intermediate copies.
3. Grant **get secret** only to the right gateway identity, not all developers.
4. Separate dev/staging/prod key material and Key Vaults.
5. Maintain a key rotation/compromise runbook.
6. Restrict exec/log/backup access on components storing private keys.
7. Run secret scanning in CI, without feeding real private keys into public scanning tools.

**Never share the same production certificate/private key across all environments** just because DNS SANs look similar; blast radius and permissions must remain isolated.

## 58. CI/CD and IaC for Certificates

A system can manage endpoint configurations via **Bicep, ARM, Terraform, Helm, Kubernetes manifests, or GitOps**.

~~~text
Git (contains NO private keys)
       |
       +-- Hostname and TLS policy
       +-- Key Vault secret identifier (no secret value)
       +-- Identity/RBAC references
       +-- Ingress/Gateway listener config
       |
       v
CI validation + approval
       |
       v
Deploy TLS binding to staging
       |
       v
OpenSSL/health validation
       |
       v
Controlled production rollout
~~~

### Never Store Private Keys in IaC

A template reading a password/PFX from an input file can accidentally persist it into **plans/state/deployment logs**. Isolate private key material in secret management, pass approved references, and ensure CI tools never echo sensitive inputs.

### Desired State and Drift

If an engineer swaps a certificate in the Portal, a controller/IaC pipeline may overwrite it on reconciliation. After an emergency hotfix, update desired state or execute a deliberate rollback so production never has two conflicting configuration sources.

### Validation Pipeline

- Lint/validate IaC/Ingress resources.
- Check expected hostnames/SANs and CA/issuer.
- Verify the certificate is unexpired and the key pair is valid.
- Verify Key Vault reference identity and format.
- Test staging endpoints and backend origins.
- Ensure rollback artifacts/references remain functional.

## 59. Disaster Recovery: Certificates Are Part of DR

When rebuilding in another Azure region, a gateway or cluster may need certificates before it can serve HTTPS. Good DR plans answer:

1. Where are certificates/keys stored, and who has permission to use them?
2. If Key Vault is unavailable during failover, is there an approved fallback path?
3. Are managed certificates automatically provisioned in the new region/gateway?
4. Does DNS/domain validation allow the DR endpoint?
5. Are Key Vault soft delete/purge protection/backup/recovery policies aligned?
6. Does IaC recreate Ingress/Gateway listeners with the right secret references?
7. Do client truststores already contain required CAs/chains?
8. How are backend mTLS client certificates rotated or reissued?

### Do Not Mistake Public Certificate Backups for Full TLS DR

Public PEMs may exist in many places, but the **private key is the sensitive asset needed to serve traffic**. If the private key is a non-exportable HSM key, DR must rely on supported service replication/recovery mechanisms rather than assuming you can copy a PFX.

## 60. Runbook: Expired Certificate at the Gateway

Scenario: users report **NET::ERR_CERT_DATE_INVALID** when visiting **api.example.com**.

### Step 1: Verify

~~~bash
HOST="api.example.com"
openssl s_client \
  -connect "$HOST:443" \
  -servername "$HOST" \
  -verify_return_error \
  -showcerts < /dev/null
~~~

Check **Not After**, leaf SAN/chain, and whether you are hitting Front Door or Application Gateway. Verify current DNS, region/client network, and server clock.

### Step 2: Analyze Inventory

- Is the expired cert at the edge or the backend?
- Does the gateway use a managed certificate or Key Vault BYOC?
- Does Key Vault already have a new version?
- Is the reference versionless or version-pinned?
- Did the gateway/ingress reload?

### Step 3: Remediate Within Authorized Scope

- If a new cert already exists, update/restore the approved binding/refresh per service documentation.
- If not, trigger emergency issuer renewal/reissue through approved channels.
- If SNI is misconfigured, fix the listener/hostname binding rather than unnecessarily issuing a new cert.
- Never downgrade to plaintext HTTP or disable certificate verification to hide the error.

### Step 4: Verify

- HTTPS handshake passes with valid hostname and chain.
- Fingerprint/Not After updated as expected.
- Checks across regions/clients show no remaining errors.
- Backend health, p95 latency, and 5xx rates stabilize.
- Document timeline, owner, root cause, and alerting improvements.

## 61. Lab A: Verifying a Public HTTPS Endpoint

**Objective:** inspect a public certificate over the network without modifying Azure resources.

### Prerequisites

- A lab HTTPS endpoint or organization-authorized test domain.
- OpenSSL installed on an approved machine.
- Never run load scans against third-party domains.

### Steps

1. Pick hostname **tls-lab.example.com** configured in your lab; names in this guide are placeholders, not real endpoints.
2. Run **openssl s_client** with **`-servername`** and **`-verify_return_error`**.
3. Record issuer, Not Before, Not After, SAN, and TLS version.
4. Extract/save the public leaf cert via lab procedure without downloading any private key.
5. Run **`openssl x509 -noout -dates -ext subjectAltName`**.
6. Check **`-checkend`** for 30 days.
7. Compare the server certificate fingerprint against inventory.
8. Record only necessary public metadata in your report; never print secrets.

### Acceptance Criteria

| Check | PASS when |
|---|---|
| Hostname | SAN includes the target FQDN |
| Trust | Chain up to a trusted root verifies cleanly |
| Validity | Certificate is valid at test time |
| Protocol | TLS version meets policy |
| SNI | Client receives the right leaf for the hostname |
| Fingerprint | Matches the serving inventory/version |
| Secrets | Zero private keys/passwords in outputs |

## 62. Lab B: Key Vault Certificate Metadata and Lifecycle

**Objective:** inspect Key Vault certificate policy, versions, and expiry **using read permissions**.

### Preparation

- A lab Key Vault containing a lab-dedicated public/self-signed certificate.
- Azure CLI and an identity granted appropriate **certificate metadata read** access.
- Valid networking/vault firewall rules.
- Never use a production vault just for exploration.

### Steps

1. Run **`az account show`** to verify subscription/tenant.
2. Run **`az keyvault certificate list`** to list names and expiration metadata.
3. Run **`az keyvault certificate show`** for a lab certificate.
4. Inspect **policy/issuer/validity** per CLI/Portal support.
5. Check how many versions the certificate has.
6. Explain the differences between certificate metadata, backing secret, and cryptographic key.
7. Check whether the lifetime action is notification or auto-renew.
8. Do not fetch/download the PFX/private-key secret.
9. Record owner/expiry/renewal mode in a sample inventory.

### Question

If certificate V2 appears in the vault yet Application Gateway still serves V1, which two areas should you inspect next?

**Guided answer:** Inspect the gateway's Key Vault secret reference (versionless vs. pinned), identity/networking, and refresh mechanism; then verify the live certificate via the HTTPS listener.

## 63. Lab C: AKS Certificate Rotation in a Test Namespace

**Objective:** understand **Kubernetes TLS Secrets/Ingress** and separate Secret state from the certificate actually being served.

### Prerequisites

- A lab AKS/Kubernetes namespace, scoped RBAC permissions, and a compatible ingress controller.
- An authorized public test domain or lab internal hostname.
- Certificate issued by an approved test CA/ACME staging/issuer.
- Never use production private keys.

### Steps

1. Create a Certificate/Issuer with cert-manager or load a lab certificate via an approved workflow.
2. Confirm the **`kubernetes.io/tls`** Secret and that Ingress/Gateway references it properly.
3. Use OpenSSL from a lab client to check leaf fingerprint/expiry.
4. Renew or reissue in the test environment via issuer/automation.
5. Observe Secret version/data updates.
6. Confirm the ingress/controller reloaded; if not, run the approved reconciliation/restart workflow.
7. Run OpenSSL from multiple Pods/clients/paths to confirm the new serving fingerprint.
8. Watch ingress 4xx/5xx, handshake failures, and readiness.
9. Confirm private keys never appear in Git/CI/logs.
10. Clean up test resources and document rotation lessons in a runbook.

### Do Not Do in Practice Labs

- Never **revoke** a production certificate to simulate an incident.
- Never delete a production service's Kubernetes Secret.
- Never reset a production Key Vault access policy.
- Never open public network access or disable TLS verification for convenience.

## 64. Lab D: Java Client Truststore and CA Errors

**Objective:** test why a Java client can fail to trust an internal CA even though TCP connectivity succeeds.

### Preparation

- Lab Java 17+, **verified public certificates of the lab CA**.
- A lab TLS service using an internal CA.
- Dedicated keystore/truststore for the exercise.

### Steps

1. Run **`keytool -printcert`** to inspect the leaf public certificate.
2. Use OpenSSL to check SAN, issuer, and chain.
3. Run the lab Java HTTPS client with the default truststore (expected trust failure if the root CA is absent).
4. Verify the lab CA fingerprint over a trusted channel.
5. Import **only the approved lab CA** into `truststore-lab.p12`, without modifying global `cacerts`.
6. Configure the lab app to use the new truststore per exact JSSE/HTTP client settings.
7. Re-run the HTTPS request and observe the result.
8. Test a hostname absent from the SAN to prove importing the CA **does not bypass hostname verification**.
9. Clean up/revert lab configuration and save the report.

### Lesson Learned

Trusting the right root CA enables chain validation, but **hostname, validity, EKU, algorithms, and revocation policy** remain part of TLS validation. Never treat importing a certificate as a cure-all.

## 65. Case Study: Multi-Tier Retail API on Azure

An enterprise runs:

- **Azure Front Door** serving **api.shop.example.com**.
- **Application Gateway** routing to AKS.
- **AKS ingress** using an internal certificate for HTTPS traffic.
- **Spring Boot** calling Azure Key Vault and Azure SQL over Private Endpoints.
- A B2B partner using **mTLS** on a dedicated API.
- Public certificates issued by a public CA via Key Vault BYOC for some endpoints, and Azure-managed TLS for the rest.
- A team using cert-manager for internal AKS certificates.
- SREs operating under uptime SLOs requiring zero-downtime rotation.

### Hypothetical Incident

On renewal day, Key Vault shows certificate V3 with a new Not After, yet some users still receive expiring certificate V2. Simultaneously, Java Pods report **PKIX path building failed** when calling a backend whose intermediate CA recently changed.

### Design Tasks

1. Diagram every TLS hop from browser to Pod and to Key Vault/SQL APIs.
2. Identify where public CA certs are used vs. internal CA certs.
3. Distinguish Front Door's edge certificate from its origin certificate.
4. Check App Gateway listener Key Vault secret reference, managed identity, and vault networking.
5. Explain why cert V3 in the vault does not guarantee the listener serves V3.
6. Design probes verifying fingerprints at every TLS endpoint/region.
7. Diagnose the Java PKIX failure when the intermediate chain changed.
8. Design truststore CA rollover without disabling SSL checks.
9. Plan renewal/rotation separating public certificates and mTLS clients.
10. Structure Key Vault/CSI/cert-manager governance to avoid ownership conflicts.
11. Propose expiry alerts for both Key Vault and live serving endpoints.
12. Design blast-radius isolation for wildcards and private keys.
13. Define when certificate revocation and rekeying are mandatory.
14. Design CI/CD/IaC and rollback when a listener/new cert fails.
15. Account for all cost drivers, not just certificate purchase fees.

### Reference Solution Approach

~~~text
Browser
  |
  | Public HTTPS certificate for api.shop.example.com
  v
Azure Front Door
  |
  | HTTPS to origin / origin hostname validation
  v
Application Gateway
  |
  | Internal HTTPS certificate/trusted root as configured
  v
AKS ingress
  |
  | HTTP/HTTPS/mTLS per policy
  v
Spring Boot API
  |
  +--> Key Vault private DNS + TLS + Entra token
  +--> Azure SQL FQDN + JDBC TLS + database auth
~~~

**Two parallel diagnostic tracks:**

- **Key Vault V3 but edge serves V2:** check Key Vault secret ID/format, gateway integration, identity/networking, refresh/rollout, and live TLS probes.
- **Java PKIX:** check the new issuer/intermediate chain, JDK truststore, CA rollover, SAN/SNI, and hostname; never enable trust-all.

**Target outcome:** endpoints serve valid certificates with matching hosts, chains, and Not After; mTLS clients keep authenticating; Java code never disables certificate checks; SREs hold a complete inventory and runbook for the next renewal cycle.

## 66. Production Checklist

| Area | Pass Criteria |
|---|---|
| Inventory | All public/internal TLS endpoints, owners, and certificate IDs documented |
| Domain/SAN | Hostnames/SNI, DNS/CAA, and ownership verified |
| PKI | Public/internal CA policies, trust chains, and EKUs valid |
| Key material | No private keys in Git/logs; exportability/HSM matches design |
| Key Vault | Certificate/key/secret permissions and policies configured |
| IAM | Managed identities and least-privilege RBAC/access policies |
| Networking | Private DNS, TLS, firewall/Private Endpoints aligned |
| Managed TLS | Eligibility, auto-renew, and domain validation monitored |
| BYOC | Issuance/renewal/import/deploy automated or covered by runbook |
| App Service | Hostname bindings, TLS policies, and slot semantics verified |
| Front Door | Edge certs and origin TLS verified separately |
| Application Gateway | Listener certs, Key Vault secret refs, and backend trust verified |
| AKS | Ingress/controller/CSI/cert-manager ownership and reload tests pass |
| Java | Truststores/keystores, hostname verification, and JDK support verified |
| mTLS | Client identity, CA trust, auth mapping, and rotation tested |
| Monitoring | Expiry, fingerprints, SANs, handshake failures, and origin health tracked |
| Alerts | Owners/on-call, escalation paths, and independent probes active |
| Rotation | Staging, rollout, serving fingerprint checks, and rollback ready |
| Revocation | Key compromise runbook, CA revocation, and key replacement ready |
| CA rollover | Old/new trust overlap and client compatibility validated |
| CI/CD | Zero PFX/private keys in builds, state, or logs |
| DR | Certificate/key recovery or reissue strategy tested |
| Costs | CA, Key Vault, gateways, networking, and monitoring/incident costs budgeted |
| Compliance | TLS versions/algorithms/data residency meet current policy |

## 67. Self-Check Questions

1. Which security problems does TLS solve, and which does it not solve?
2. How does an X.509 certificate differ from a private key?
3. How do leaf, intermediate, and root CAs relate?
4. Why must clients verify SANs rather than just the CN?
5. How does SNI help when multiple domains share one edge IP?
6. Why shouldn't you connect to a Private Endpoint by direct IP?
7. On what criteria should TLS 1.2 and 1.3 be chosen?
8. Does mTLS replace application-level authorization?
9. Does a wildcard certificate cover subdomains at every depth?
10. How do Not Before and Not After differ?
11. Is a certificate fingerprint confidential private information?
12. How do renewal, rekey, rotation, and revocation differ?
13. Why might a V2 certificate in Key Vault not yet be deployed live?
14. How do operational responsibilities differ between Azure-managed certs and BYOC?
15. How do public CAs verify domain ownership?
16. Why is ACME DNS-01 usually required for wildcard certificates?
17. Does a CSR contain the private key?
18. How do PEM, DER, and PKCS#12 differ?
19. Why can a Key Vault certificate's backing secret contain a PFX?
20. How can Key Vault certificate, key, and secret permissions differ?
21. Can a non-exportable HSM key be used by a gateway expecting a PFX by default?
22. Are self-signed certificates in Key Vault automatically trusted by public browsers?
23. Can an App Service managed certificate be exported to AKS?
24. How does an App Service Key Vault app-setting reference differ from TLS hostname binding?
25. Must Front Door edge TLS and origin TLS use the exact same certificate?
26. Does an App Gateway HTTPS listener automatically encrypt backend connections?
27. What conditions must be met for App Gateway to read a Key Vault-backed TLS certificate?
28. When using a Key Vault versionless reference, what verification step is still required?
29. Which data keys does a Kubernetes TLS Secret typically contain?
30. Is Base64 in a Kubernetes Secret encryption?
31. What parts does cert-manager automate, and what does it not handle on its own?
32. Does a CSI Driver updating a file cause Spring Boot to automatically reload its keystore?
33. How do a Java truststore and keystore differ?
34. Why does importing a CA not fix a hostname mismatch?
35. Which **`openssl s_client`** flag sends SNI?
36. What does **`openssl x509 -checkend`** check?
37. Why might a public internet certificate probe miss an origin cert error?
38. During CA rollover, what must happen on clients before changing the server chain?
39. How can certificate pinning cause rotation failures?
40. Does revocation guarantee every browser immediately rejects a compromised cert?
41. When a private key is exposed, what steps are mandatory beyond renewal?
42. Why do you need both Key Vault expiry alerts and live endpoint probes?
43. How do TLS handshake errors differ from HTTP 403?
44. Why must a trust-all TrustManager never be used in production?
45. Which TLS data and configurations does a DR system need to resume serving?

## References

- Microsoft Learn — *Azure Key Vault certificates overview*: https://learn.microsoft.com/azure/key-vault/certificates/about-certificates
- Microsoft Learn — *Renew Azure Key Vault certificates*: https://learn.microsoft.com/azure/key-vault/certificates/overview-renew-certificate
- Microsoft Learn — *Import a certificate into Key Vault*: https://learn.microsoft.com/azure/key-vault/certificates/tutorial-import-certificate
- Microsoft Learn — *Azure Key Vault RBAC*: https://learn.microsoft.com/azure/key-vault/general/rbac-guide
- Microsoft Learn — *Key Vault Event Grid overview*: https://learn.microsoft.com/azure/key-vault/general/event-grid-overview
- Microsoft Learn — *App Service TLS/SSL certificates*: https://learn.microsoft.com/azure/app-service/configure-ssl-certificate
- Microsoft Learn — *App Service TLS/SSL bindings*: https://learn.microsoft.com/azure/app-service/configure-ssl-bindings
- Microsoft Learn — *Azure Front Door custom-domain HTTPS*: https://learn.microsoft.com/azure/frontdoor/standard-premium/how-to-configure-https-custom-domain
- Microsoft Learn — *Application Gateway TLS termination*: https://learn.microsoft.com/azure/application-gateway/ssl-overview
- Microsoft Learn — *Application Gateway and Key Vault certificates*: https://learn.microsoft.com/azure/application-gateway/key-vault-certs
- Microsoft Learn — *Application Gateway end-to-end TLS*: https://learn.microsoft.com/azure/application-gateway/ssl-overview
- Microsoft Learn — *AKS Key Vault CSI Driver*: https://learn.microsoft.com/azure/aks/csi-secrets-store-driver
- Microsoft Learn — *AKS CSI secret rotation*: https://learn.microsoft.com/azure/aks/csi-secrets-store-configuration-options
- cert-manager documentation: https://cert-manager.io/docs/
- Kubernetes — *TLS Secrets*: https://kubernetes.io/docs/concepts/configuration/secret/#tls-secrets
- Kubernetes — *Ingress*: https://kubernetes.io/docs/concepts/services-networking/ingress/
- Spring Boot — *SSL bundles*: https://docs.spring.io/spring-boot/reference/features/ssl.html
- RFC 5280 — *X.509 Public Key Infrastructure*: https://www.rfc-editor.org/rfc/rfc5280
- RFC 8446 — *TLS 1.3*: https://www.rfc-editor.org/rfc/rfc8446
- Let's Encrypt — *Challenge types*: https://letsencrypt.org/docs/challenge-types/
- OWASP — *Transport Layer Security Cheat Sheet*: https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html
- Oracle — *keytool documentation*: https://docs.oracle.com/en/java/javase/17/docs/specs/man/keytool.html
- Azure Pricing Calculator: https://azure.microsoft.com/pricing/calculator/
