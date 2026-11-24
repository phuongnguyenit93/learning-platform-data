# mTLS between proxy and application and transport protection boundaries

> **Topic:** Spring Security – federation. **Group:** Proxy Authentication. This Knowledge article guides designing, implementing, and testing **mutual TLS (mTLS) between a reverse proxy/ingress/API gateway and a Spring Security application**. The focus is distinguishing **trust in the proxy → application connection** from **end-user identity**, security boundaries after TLS termination, X.509/PKIX/SAN/EKU verification, NGINX + Spring Boot Java 17+ configuration, and conditions for using pre-authentication headers or verified tokens without creating bypass paths.

## 1. Learning objectives

After completing this article, you will be able to:

1. Identify **which hop mTLS protects** in browser → proxy → app → database and why browser HTTPS does not protect proxy → app automatically.
2. Distinguish TLS server authentication, mTLS client authentication, **service/workload identity**, **end-user authentication**, and **tenant/resource authorization**.
3. Configure a reverse proxy as a TLS **client** to the Spring app, while Spring's embedded server requires a certificate from the proxy.
4. Read, verify, and properly define **server certificates**, **client certificates**, CAs/truststores, certificate chains, SANs, EKUs, lifetimes, SNI, and revocation policies.
5. Understand the difference between **mTLS to the Spring app** and **user X.509 authentication at the edge**; never confuse a proxy certificate with a user certificate.
6. Block direct backend access, spoofed `X-Forwarded-*`/`X-Authenticated-User`, health/management port bypasses, wrong TLS peer identities, or unapproved proxies.
7. Build an **mTLS + OAuth2 Resource Server JWT** flow: the proxy is verified at the TLS layer, while user/token `issuer`, `audience`, and `scope` are still verified by Spring.
8. Know when `RequestHeaderAuthenticationFilter` can be used in a trusted pre-auth model, along with mandatory prerequisites before accepting user headers.
9. Explain in Java 17 the role of connection checks and authorization using a console demo with deterministic stdout; never treat a simulation as real cryptographic mTLS validation.
10. Build a negative-case test matrix, verify fail-closed behavior, certificate rotation, HA, observability, and cross-team incident investigation.

**Foundational rule:** **mTLS on the proxy → app hop proves "who is the workload peer in front of the app, and is transport on this hop protected?"**. It **does not prove on its own "who the end user is, whether they authenticated at an IdP, or whether they may read tenant X's data?"**.

## 2. Network model and TLS termination points

Example of a SaaS application running behind NGINX or Envoy:

```text
              INTERNET / CLIENT NETWORK
  +---------------------+
  | Browser / API client|
  | TLS client          |
  +----------+----------+
             |
             | HOP 1: HTTPS (TLS)
             | Client checks proxy's public server certificate
             v
  +---------------------+
  | Edge Proxy / LB     |
  | TLS server for HOP 1|
  | TLS client for HOP 2|
  | Auth gateway, WAF   |
  +----------+----------+
             |
             | HOP 2: HTTPS + mTLS
             | Proxy verifies Spring backend server certificate
             | Spring backend verifies PROXY client certificate
             v
  +---------------------+
  | Spring Boot Service |
  | HTTPS :8443         |
  | server.ssl.client-  |
  | auth: need          |
  +----------+----------+
             |
             | HOP 3: DB / message broker / other API
             | Has independent transport & identity policy
             v
  +---------------------+
  | Database / Service B|
  +---------------------+
```

**HOP 1 and HOP 2 are two separate TLS sessions.** NGINX decrypts HTTP requests at the proxy (where WAF, cookie policies, or authorization token inspection can run), then re-encrypts requests for the backend hop when configured with `proxy_pass https://...`. The backend sees connections coming from the proxy, and **does not see the browser's TLS client certificate** on HOP 1 once the edge terminates TLS.

### 2.1. Common architectures

| Model | Browser → proxy | Proxy → application | Security implication |
| --- | --- | --- | --- |
| **A. TLS termination + internal HTTP** | HTTPS | HTTP | Plaintext on hop 2; fits only when security risk assessment permits a tightly trusted network; not mTLS |
| **B. TLS termination + upstream HTTPS (one-way)** | HTTPS | HTTPS, proxy verifies app server cert | Secures hop 2 and authenticates app; backend **does not** verify proxy client via cert |
| **C. TLS termination + upstream mTLS** | HTTPS | HTTPS, both sides verify certificates | Protects hop 2 and authenticates proxy/app workloads; still must verify user |
| **D. TLS passthrough** | HTTPS passes through TCP proxy | Client TLS session terminates directly at app | App can see browser client cert if presented; edge cannot inspect HTTP easily; this is **not** proxy → app mTLS in the proxy-as-TLS-client sense |
| **E. Edge authenticates client via mTLS** | Client presents certificate to edge | May be HTTP, HTTPS, or mTLS per config | Edge knows client identity on hop 1; app knows only via a trusted propagation mechanism; hop 2 must still be protected separately |
| **F. Service mesh mTLS** | Per ingress config | Sidecars/mesh verify workloads across nodes | mTLS may terminate at sidecar rather than JVM; app still needs separate identity/header/user policies |

**Do not call model B mTLS.** Model B uses HTTPS with backend server certificate validation, yet the app requires no certificate from the proxy. Conversely, if the backend has `client-auth=need` while the proxy skips server certificate verification (`proxy_ssl_verify off`), the two sides **have not established safe assurance**: the proxy could be redirected to a rogue backend.

### 2.2. What does "end-to-end encryption" mean in these models?

When the proxy terminates TLS, data is decrypted **at the proxy** for processing. Two HTTPS hops provide **transport encryption between each peer pair**, but **not** a single unbroken TLS session from browser to app. Therefore:

- Proxy operators can inspect/process HTTP payloads after TLS termination; protect proxy configs, memory, logs, admin access, and auditing.
- If the proxy **must never read application payloads**, use TLS passthrough or **application-layer end-to-end encryption** for sensitive data per policy; never label hop-by-hop mTLS an end-to-end TLS session.
- HOP 2 TLS does not automatically protect data sent from the app to a DB or queue on HOP 3; each connection needs its own TLS/mTLS or protection.
- Traces at the proxy can see requests/bodies prior to re-encryption; never write secrets/cookies/tokens into access logs merely because the network connection is encrypted.

## 3. Who does mTLS authenticate? Distinguishing proxy identity from user identity

In proxy→app mTLS:

- **App backend is the TLS server**: presents an X.509 certificate for `backend.internal.example.org`; the proxy verifies CA, SAN/hostname, validity, algorithms, and policy.
- **Proxy is the TLS client**: presents a certificate representing the proxy workload itself, e.g. SAN `URI:spiffe://corp.example/edge/proxy-a` or `DNS:edge-proxy.internal.example.org`; the app verifies CA/chain, validity, and **authorized identity**.
- **End user** may be authenticated at the edge via SAML/OIDC/CAS, or supply a Bearer access token for the backend to verify itself. The user is not by default the CN or SAN on the **proxy client certificate**.
- **Tenant** is an application data/permission boundary; never infer it from internal hostnames or the fact that a proxy holds a valid certificate.

### 3.1. Three-layer formula

```text
Transport/workload authentication
    mTLS:   trusted proxy workload <--> trusted app workload
                       |
                       v
End-user authentication
    JWT/OIDC/SAML/CAS/verified pre-auth evidence
                       |
                       v
Authorization
    account + tenant + operation + resource + policy
                       |
                       v
Only then return or mutate business data
```

**Example:** The proxy holds a cert issued by the Enterprise Proxy CA. Its connection to Spring TLS 8443 succeeds. Meanwhile, the browser sends a forged `X-Authenticated-User: ceo`. If the edge forwards the header untouched and Spring trusts it, **mTLS still succeeds** while the user is impersonated. The flaw is the **identity header's trust boundary**, not broken TLS.

### 3.2. What does an mTLS certificate NOT guarantee?

Proxy mTLS **does not** prove:

- That the browser logged into an IdP successfully.
- That an `X-User`/`X-Email` header was verified by the proxy rather than supplied by the client.
- That a Bearer token has a valid signature/audience.
- That the user belongs to the requested tenant.
- That the proxy enforced up-to-date roles/permissions.
- That the app has no other directly reachable endpoint or listener.
- That all backend/service-mesh traffic is encrypted.
- That logs/caches/in-memory bodies or stored data are protected.
- That the proxy certificate's private key has not leaked since issuance.
- That a trusted CA issued certs **exclusively** to that single proxy — many workloads may share the same CA.

**Key takeaway:** `client-auth=need` normally requires the client to present **a certificate trusted by the truststore**. If the truststore contains a CA authorized to issue certs to hundreds of workloads, successful mTLS only proves the cert came from that trusted CA, **not that the peer is an authorized proxy**. You need SAN/URI identity policies, dedicated CAs, mTLS ingress allowlists, and workload-bound policies.

## 4. Reading TLS, certificates, PKIX, and truststores properly

| Term | Why does it matter? | What must be checked? |
| --- | --- | --- |
| **CA / trust anchor** | Authority permitted to issue certificates | Trust only governed CAs; never trust-all |
| **Certificate chain** | From leaf → intermediate → root CA | Signatures, Basic Constraints, validity, and trust chain |
| **SAN** | Confirms peer's DNS/IP/URI identity | Proxy checks server SAN matches backend hostname; app checks proxy workload identity via policy |
| **Extended Key Usage (EKU)** | Intended certificate usage | Server cert suits `serverAuth`, client cert suits `clientAuth` when required by profile |
| **Key Usage** | Permitted private-key operations | Matches TLS signing/handshake and PKI policy |
| **SNI** | Selects certificate/virtual host during TLS connect | Proxy sends SNI matching backend hostname when needed |
| **Hostname verification** | Prevents rogue backends using certs for other hosts | Never disable; never check CA alone without SAN |
| **Expiration** | Certificates are valid only within a window | Monitor NotBefore/NotAfter and alert before expiry |
| **Revocation** | Cert revoked due to key compromise/untrusting | CRL/OCSP/short-lived cert rotation per org; verify operational support |
| **Truststore** | Holds CAs/certs trusted to verify peers | Spring backend trusts proxy client CA; NGINX trusts backend server CA |
| **Keystore** | Holds **this side's own** certificate and private key | Spring backend stores server key; NGINX holds proxy client key |
| **mTLS handshake** | Both peers verify each other's cert before HTTP app | Untrusted/wrong identity must fail at the TLS layer |
| **Certificate rotation** | Key/CA rollover without downtime | Controlled overlap, canary, audit, rollback |

Never confuse the Spring backend's **TLS server certificate** with a SAML IdP signing certificate, an OAuth2 JWK, or a CAS service ticket. They operate at different verification layers; **one certificate type never substitutes for another**.

### 4.1. Two truststores are normally distinct

```text
Proxy NGINX TLS client:
  private key /etc/nginx/certs/proxy-client.key
  certificate /etc/nginx/certs/proxy-client.crt
  trusted CA /etc/nginx/certs/backend-server-ca.pem
                |
                | HTTPS + mTLS
                v
Spring Boot TLS server:
  private key /run/secrets/backend-server.p12
  trusted CA /run/secrets/approved-proxy-client-ca.p12
```

**Two trust directions:**

1. NGINX must **trust the right backend**. Beyond TLS, set `proxy_ssl_verify on` and the right `proxy_ssl_name`/SNI; in many NGINX builds `proxy_ssl_verify` defaults to **off** unless enabled.
2. Spring must **trust the right proxy client**. `server.ssl.client-auth=need` requires a certificate, `server.ssl.trust-store` holds the CA verifying the proxy's cert, and workload identity policies must prevent trusting arbitrary clients issued by the same CA.

Importing only the backend CA into Spring's truststore without the proxy CA leaves Spring unable to verify the proxy. Adding only the proxy CA into NGINX's trust bundle meant to verify the **backend server** likewise configures the wrong trust direction.

### 4.2. Holding a certificate is not enough if peer identity is too broad

Dangerous scenario:

```text
Spring trusts "Corp-PKI-Root-CA"
This CA issues certs for:
  - edge-proxy-a
  - unrelated-batch-service
  - developer-workstation
Backend does not distinguish SAN/proxy workload
=> all workloads holding a valid clientAuth cert from this CA
   can pass TLS client-auth if network allows.
```

Improvements:

- Use a dedicated CA for **proxy-to-backend** or strict per-workload certificate issuance policies.
- Backend or inbound gateway enforces **allowed proxy identities** based on SAN/URI, lifecycle-managed leaf thumbprints/pinning, or service-mesh policies.
- Never treat source IP alone as strong identity; pair network ACLs **with** mTLS identity.
- Avoid sharing one private key across all proxies when per-workload identities are feasible; rotate/revoke per node.
- Verify whether listeners/liveness/admin endpoints enforce the same mTLS policy.

**SAN identity mapping can occur at the TLS terminator**, not necessarily inside Spring Security MVC. When mTLS terminates at an Envoy sidecar, the JVM does not receive the original peer certificate directly; the sidecar/gateway must enforce the workload policy and the backend must accept traffic only from the trusted sidecar. If the app needs peer identity, design an authenticated propagation channel rather than trusting self-asserted HTTP headers.

## 5. End-user authentication through the proxy: two main models

### 5.1. Model A — Backend verifies OAuth2/JWT itself, mTLS protects only the network hop

```text
Browser -- Bearer access token --> NGINX
  NGINX:
    TLS from browser; WAF/routing;
    strip browser-supplied identity headers;
    mTLS + forward Authorization to backend
                             |
                             v
  Spring Boot:
    TLS engine verifies NGINX client certificate
    Spring Security validates JWT signature + iss + aud + exp + scopes
    app checks account/tenant/resource authorization
```

**Advantage:** No need to trust HTTP `X-User` as identity; both transport peer and user token are verified independently. This is a transparent choice for APIs using OAuth2 access tokens, easy to test and separate responsibilities.

**Limitation:** When web login uses a proxy-managed session cookie and the backend lacks a token, another solution is needed (trusted pre-auth, token exchange, backend session/BFF). Never convert a login ID Token into an API Access Token automatically; a Resource Server must validate an **access token** intended for the API.

### 5.2. Model B — Proxy authenticates user, Spring trusts a protected header (pre-auth)

```text
Browser -> Edge IdP login / SAML / OIDC / CAS / session
                     |
               proxy validates
                     |
        overwrite canonical X-Verified-User
        canonical identity, issuer, expiry,
        signed assertion or request context
                     |
                mTLS to Spring
                     |
     backend trusts header only from approved
     proxy workload on isolated mTLS listener
                     |
      local user mapping + authorizations
```

Spring provides `RequestHeaderAuthenticationFilter` and `PreAuthenticatedAuthenticationProvider` to load user details from a **pre-authenticated source**. Yet these conditions must hold **simultaneously**:

1. The proxy actually completed user verification using a trusted IdP protocol/method and validated session/expiry/revocation per policy.
2. The proxy **strips all** untrusted user, group, role, issuer, audience, and forwarded headers from the browser at the outer boundary; it **sets anew** the exact identity header.
3. The Spring backend **cannot be reached directly** from the Internet/side-channels/other pods lacking an approved mTLS identity.
4. Backend TLS requires a cert and confirms it belongs to the **actual proxy workload**, not merely a broad enterprise CA.
5. No alternate routes exist via management ports, actuator, h2c, plain HTTP listeners, or gRPC listeners.
6. Headers carry stable identity keys, issuer/tenant scope, and clear provenance. Never use email/display name/raw `X-Role: ADMIN` as system-wide privileges.
7. Edge user/session state is bound to each request, with expiry/revocation and anti-replay across context switches.
8. Backend maps verified external identities to local accounts and tenant permissions itself.
9. Monitoring and negative tests cover spoofing `X-Verified-User` from browsers or direct callers.
10. If end-to-end user evidence is needed across multiple intermediaries, use a token with backend-specific **signature + audience + expiry**; carrying a token over mTLS does not make the token trustworthy by itself.

**Very common mistake:** calling `RequestHeaderAuthenticationFilter.setPrincipalRequestHeader("X-User")` while leaving backend HTTP open to the whole VPC. Any internal caller setting `X-User: admin` can impersonate; edge HTTPS/mTLS on another route will not save a bypassed route.

### 5.3. `X-Forwarded-For` and `X-Authenticated-User` do not mean the same thing

- `Forwarded`, `X-Forwarded-For`, `X-Forwarded-Proto`, and `X-Forwarded-Host` describe routing/original URLs; they are **not verified end-user identity claims**.
- `X-Authenticated-User` and `X-Verified-User` are safe only when a trusted auth proxy created the header after login, stripped client spoofs, and protected the backend hop.
- `X-Forwarded-Client-Cert` (XFCC) can hold certificate details sent by the edge. To the backend it is **merely an HTTP header** once TLS terminated at the edge. It must be stripped/overwritten and bound to peer trust; never treat a base64 certificate string from a client as client-certificate proof.
- `X-SSL-Client-Cert` or `X-Client-Cert` from an edge are not automatically treated by Spring Security as container-verified TLS client certs; it depends on the proxy contract and trust boundary.

**Technical point:** Spring's `ForwardedHeaderFilter` can normalize URL/scheme/host metadata on requests, yet **does not replace** edge stripping of user-supplied forwarded headers and **does not** verify the mTLS peer. When the edge is the trust boundary, it must strip both `Forwarded` and `X-Forwarded-*` from clients and rewrite them per topology.

## 6. NGINX → Spring Boot: practical hop-by-hop mTLS configuration

### 6.1. Testable set of assumptions

```text
Public URL (browser -> NGINX):
  https://portal.example.org/api/reports

NGINX edge TLS listener:
  443; public certificate for portal.example.org

Backend Spring Boot TLS listener:
  https://backend.internal.example.org:8443

Backend X.509 server certificate:
  SAN DNS:backend.internal.example.org

NGINX X.509 client certificate:
  SAN DNS:edge-proxy.internal.example.org
  EKU clientAuth

Spring accepts proxy certificates:
  issued by dedicated Proxy-Client-CA
  plus allowed proxy workload identity

User token audience:
  api://reports (example only)

User token issuer:
  https://idp.example.org/realms/work
```

All domains/paths/keys here are for learning only; they **do not exist as a working deployment** until DNS, TLS, CAs, IdP, and networking are properly configured. Every certificate/private key file must be provisioned/mounted by a secrets manager, **never** committed to a repository.

### 6.2. NGINX acting as TLS client to upstream

File **fragment** `/etc/nginx/conf.d/portal.conf`, merged into a real NGINX `http` configuration with governed files:

```nginx
server {
    listen 443 ssl;
    server_name portal.example.org;

    # HOP 1: browser --> edge (server TLS)
    ssl_certificate     /etc/nginx/tls/public-fullchain.pem;
    ssl_certificate_key /etc/nginx/tls/public-private.key;
    ssl_protocols TLSv1.2 TLSv1.3;

    # HOP 2: edge --> backend (mTLS)
    location /api/ {
        proxy_pass https://backend.internal.example.org:8443;

        # Backend TLS server identity verification:
        proxy_ssl_server_name on;
        proxy_ssl_name backend.internal.example.org;
        proxy_ssl_verify on;
        proxy_ssl_verify_depth 3;
        proxy_ssl_trusted_certificate
            /etc/nginx/tls/backend-server-ca.pem;

        # NGINX client certificate sent to backend:
        proxy_ssl_certificate
            /etc/nginx/tls/edge-proxy-client.crt;
        proxy_ssl_certificate_key
            /etc/nginx/tls/edge-proxy-client.key;

        proxy_ssl_protocols TLSv1.2 TLSv1.3;

        # External clients may not claim these identities.
        proxy_set_header X-Verified-User "";
        proxy_set_header X-Authenticated-User "";
        proxy_set_header X-Forwarded-Client-Cert "";
        proxy_set_header X-SSL-Client-Cert "";

        # Recreate canonical forwarded metadata at trusted edge.
        proxy_set_header Host portal.example.org;
        proxy_set_header X-Forwarded-Host portal.example.org;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header Forwarded "";

        # For MODEL A only: pass user Access Token to Spring.
        proxy_set_header Authorization $http_authorization;
        proxy_pass_request_headers on;

        proxy_connect_timeout 5s;
        proxy_read_timeout 30s;
    }
}
```

**mTLS explanation:**

- `proxy_pass https://...` enables TLS on NGINX when connecting to the backend. Using `http://...` here is **not** upstream TLS.
- `proxy_ssl_verify on` is critical; NGINX's `ngx_http_proxy_module` defaults to `proxy_ssl_verify off`. Never omit it when backend authentication is required.
- `proxy_ssl_trusted_certificate` is the CA NGINX uses to verify the **backend server certificate**. Do not confuse it with the CA that issued the proxy's client cert.
- `proxy_ssl_name` and `proxy_ssl_server_name on` make NGINX send SNI and verify the exact backend hostname; never set host to a browser-chosen string.
- `proxy_ssl_certificate` and `proxy_ssl_certificate_key` supply **NGINX's client identity** when the Spring backend requires a cert.
- `X-Verified-User ""` and similar directives **prevent forwarding browser identity headers** in model A; the app does not take user identity from those headers.
- `Authorization $http_authorization` makes sense only because the Spring API **verifies the JWT itself**. Never forward browser cookies/tokens indiscriminately to unrelated backends.
- `X-Forwarded-For $remote_addr` at the trusted edge sets the IP NGINX directly observes; if a trusted LB sits in front of NGINX, configure `real_ip`/hops properly instead of copying a client-spoofed IP chain.
- `proxy_pass_request_headers on` is the default; this example highlights that **header stripping** covers only a few common headers. In production, use an allowlist/normalized headers or add policies stripping other abusable header names (`X-User`, `X-Role`, `X-Forwarded-Email`, ...). **Never treat the four sample headers as exhaustive for every system.**
- `proxy_pass` without a URI suffix (host:port only) preserves `/api/...` per standard routing; adding `/` or a prefix changes NGINX path matching, requiring regression tests.
- Edge configuration should also bound HTTP methods, request/body sizes, rate limits, timeouts, cipher suites, key permissions, and log redaction per policy.

**Warning:** putting `ssl_verify_client on` in the `server` block of **NGINX's public listener** only asks the **HOP 1** browser/client for a certificate. It **does not** make the Spring backend demand NGINX's client cert and **does not** replace `proxy_ssl_certificate` on HOP 2. Those are two different mTLS directions.

### 6.3. NGINX must verify the server certificate, not merely send a client certificate

A configuration that looks like "mTLS" yet is incomplete:

```nginx
location /api/ {
  proxy_pass https://backend.internal.example.org:8443;
  proxy_ssl_certificate /etc/nginx/tls/edge-proxy-client.crt;
  proxy_ssl_certificate_key /etc/nginx/tls/edge-proxy-client.key;
  # proxy_ssl_verify remains OFF by default => backend is NOT verified!
}
```

What is missing is **server verification**: `proxy_ssl_verify on`, a trusted CA, and expected SNI/SAN. If the NGINX client does not verify the server, an attacker on the network/DNS/ingress can present an untrusted cert and capture requests/tokens, even though the proxy holds a client certificate.

Practice: `nginx -t` checks syntax before reload, yet **does not prove** handshake/PKIX validation actually works. Run negative tests with wrong SANs, unknown CAs, expired certs, and rogue backends, accepting the route only when NGINX verifies properly.

## 7. Spring Boot: embedded TLS server requiring the proxy's client certificate

Example **Spring Boot 3.x/Java 17+** listening directly on HTTPS port `8443`, accepting requests from edge NGINX. File `src/main/resources/application.yml`:

```yaml
server:
  address: 0.0.0.0
  port: 8443
  ssl:
    enabled: true
    key-store: "file:/run/secrets/backend-server.p12"
    key-store-type: PKCS12
    key-store-password: "${BACKEND_KEYSTORE_PASSWORD}"
    key-alias: "backend"
    trust-store: "file:/run/secrets/proxy-client-cas.p12"
    trust-store-type: PKCS12
    trust-store-password: "${PROXY_TRUSTSTORE_PASSWORD}"
    client-auth: need
    enabled-protocols: TLSv1.2,TLSv1.3
  forward-headers-strategy: framework

app:
  auth:
    issuer-uri: "https://idp.example.org/realms/work"
    audience: "api://reports"
```

**Points to understand:**

- `key-store` holds the Spring backend's **server certificate + private key**, whose SAN must match `backend.internal.example.org` verified by NGINX.
- `trust-store` holds the **CAs/trust anchors trusting NGINX's client certificate**, not the backend's own public cert. Restrict to CAs dedicated to proxy workloads wherever possible.
- `client-auth: need` requires TLS clients to present a valid certificate. `want` is optional and not equivalent: requests can complete the handshake **without a cert**, making it unsuitable when mTLS is mandatory for every request.
- `enabled-protocols` constrains TLS versions; check what Tomcat/Jetty/Undertow and the Java runtime actually support.
- Password values come from environment/secret managers, **never committed in plaintext** to YAML. The app process needs read access to keystore/truststore, never world-readable.
- `forward-headers-strategy: framework` governs only how forwarded headers are processed after a trusted edge; it **does not** require client certs or validate issuers/tokens. The edge must strip/set headers accurately.
- If the backend should listen only on a private interface rather than `0.0.0.0`, configure `server.address` accordingly; `0.0.0.0` binds all interfaces and **does not replace** firewalls/Kubernetes NetworkPolicy. In Kubernetes clusters, expose Services/Ingress only at the edge and block backend 8443 from unauthorized callers.
- `/actuator/health` or other management listeners must not be exempted from mTLS when doing so creates security risk; if probes cannot present certs, consider sidecar/localhost probes or an isolated, dedicated management interface.

**Limitation:** Property keys follow Spring Boot server SSL config and may vary by version. When using Spring Boot SSL Bundles, `server.ssl.bundle` and bundle definitions can replace key-store/trust-store, yet do not mix both styles without verifying behavior. The snippet above is a **Spring Boot application fragment** and cannot start cleanly by copying without real certificates.

### 7.1. Why is `client-auth=need` not the entire identity policy?

If `proxy-client-cas.p12` trusts a CA that issues certs to **many service accounts**, TLS handshakes from a non-edge service will also be accepted. In production you need **additional proxy peer identity policies**, such as:

- A CA restricted solely to the edge-proxy workload with strict issuance rules;
- Exact proxy SAN URI/DNS allowlists paired with cert expiry/revocation;
- Controlled certificate identity enforcement at ingress/sidecar or app container;
- Network allowlists preventing non-proxy callers from reaching the backend TLS port;
- mTLS workload registries/service-mesh policies scoped by service account;
- Fast automated cert rotation, issuance auditing, and private-key access controls.

Never treat client-supplied `X-Forwarded-Host`, `X-Proxy-Identity`, or `X-Client-Cert` as primary proof that the TLS engine verified a **peer certificate**. They are supplementary only when minted, signed/bound by a genuinely trusted gateway.

## 8. Spring Security application: keep user authentication separate from mTLS

This section picks **Model A**: the backend API enforces TLS client authentication at the web server, while Spring Security validates **OAuth2 JWT access tokens** issued by the IdP for the API. `RequestHeaderAuthenticationFilter` is not used for users in this example to avoid identity-header spoofing risks.

### 8.1. Maven dependencies

In a Spring Boot app with a compatible parent/BOM, add this `pom.xml` **fragment**:

```xml
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
  </dependency>
</dependencies>
```

The project needs matching build plugins, Java version, IdP/JWK endpoint, and real CAs/certs. `spring-boot-starter-oauth2-resource-server` handles user access tokens only; it **does not enable TLS or issue proxy certificates**.

### 8.2. SecurityFilterChain and JWT audience validator

File `src/main/java/com/example/proxysecurity/ApiSecurityConfig.java`:

```java
package com.example.proxysecurity;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    JwtDecoder jwtDecoder(
        @Value("${app.auth.issuer-uri}") String issuer,
        @Value("${app.auth.audience}") String audience) {

        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withIssuerLocation(issuer).build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
            JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
            if (jwt.getAudience().contains(audience)) {
                return OAuth2TokenValidatorResult.success();
            }
            OAuth2Error error = new OAuth2Error(
                "invalid_token",
                "Access token audience is not this API",
                null);
            return OAuth2TokenValidatorResult.failure(error);
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                issuerAndTime, audienceValidator));

        return decoder;
    }

    @Bean
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/health").permitAll()
                .anyRequest().authenticated())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .oauth2ResourceServer(oauth -> oauth
                .jwt(Customizer.withDefaults()))
            .build();
    }
}
```

**Read both verification paths carefully:**

1. Before an HTTP request reaches Spring's filter chain, the embedded server/Tomcat must accept NGINX's **TLS client certificate** because `client-auth=need`. If the cert is wrong or missing, HTTP controllers are never invoked.
2. For non-public `/api/**` routes, `oauth2ResourceServer` verifies JWT signature/JWK, issuer, `exp/nbf`, and audience before creating a Spring `Authentication`. A token not meant for this API is rejected even when proxy mTLS passes.
3. `JwtValidators.createDefaultWithIssuer` applies issuer/time checks, while `audienceValidator` requires the exact resource audience. Both must pass.
4. `.anyRequest().authenticated()` proves only JWT authentication; the application must **add tenant/role/resource authorization** in the service/data layer rather than returning business data to every logged-in user.
5. `/api/health` being `permitAll` in Spring means only that it requires no JWT. **TLS mTLS still runs first**, so a probe without a client cert fails the handshake. Design health probes accordingly.
6. This `SecurityFilterChain` matches only `/api/**`; production needs chains covering all other URLs or dedicated deny-by-default/actuator policies. Never leave `/admin/**` outside all filter chains by oversight.
7. `sessionCreationPolicy(STATELESS)` fits REST bearer tokens; never convert browser SAML/OIDC sessions into API tokens automatically.
8. Spring Security/Boot versions must be built and tested against a matching BOM. This is a **Spring class** needing dependencies, not runnable directly via `javac`.
9. If an OIDC browser login ID Token is sent instead of an access token, the app must reject it whenever Resource Server policy expects an **access token for the API audience**. An ID Token carries the login client's audience rather than the API audience, so the validator catches it.
10. If your organization uses **opaque** access tokens, configure introspection and validate resource audience/scopes differently from JWTs; never fake-decode them.

### 8.3. Controller verifying authentication rather than trusting proxy cert as role

File `src/main/java/com/example/proxysecurity/ProxySecurityApplication.java`:

```java
package com.example.proxysecurity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ProxySecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(ProxySecurityApplication.class, args);
    }
}
```

File `src/main/java/com/example/proxysecurity/ApiController.java`:

```java
package com.example.proxysecurity;

import java.util.Map;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {

    @GetMapping("/api/health")
    public Map<String, String> health() {
        return Map.of("status", "ready");
    }

    @GetMapping("/api/me")
    public Map<String, String> me(JwtAuthenticationToken token) {
        return Map.of(
            "authentication", "JWT_VALIDATED",
            "subject", token.getToken().getSubject());
    }
}
```

In a staging environment with an IdP, HTTPS backend keypair, NGINX client cert, and truststore, `GET /api/me` with a valid issuer/audience token succeeds. If NGINX has a valid client cert yet omits the Authorization header, Spring returns `401`; **this is the right behavior** for a user-authenticated API. If a caller supplies a forged or wrong-audience token, Spring rejects it even after mTLS passes.

**This is not a complete sensitive resource endpoint.** Production should not expose subjects indiscriminately; enforce tenant authorization, scopes, auditing, replay/revocation, WAF/rate limiting, key protection, and sessions/cookies (if any) per business rules.

## 9. Why should you not enable `x509()` treating the proxy certificate as user identity?

Spring Security provides:

```java
// Example solely for connections where the TLS client cert actually
// represents the account/actor to authenticate.
http.x509(Customizer.withDefaults());
```

This mechanism extracts the client certificate from servlet TLS attributes and maps principal and authorities (per profile/bean config). When the **client certificate on the proxy → app hop belongs to NGINX**, enabling `x509()` can make Spring authenticate **NGINX as the principal**, not the browser user.

Depending on what the application wants to authenticate:

- **Proxy workload:** use backend `client-auth=need` paired with allowed proxy workload identities in TLS/mesh/gateway;
- **Direct end-user mTLS:** the real user client certificate must reach Spring's TLS endpoint (e.g. TLS passthrough), or a protected propagation contract from the edge must carry verified user cert data;
- **End user logged in at proxy:** use protected pre-auth headers or signed downstream tokens bound to audience/session;
- **API caller via Bearer access token:** use OAuth2 Resource Server as in section 8.

**No Spring Security annotation or method call automatically carries a browser TLS session's user identity across a TLS-terminating proxy without a trusted identity-propagation protocol.**

## 10. Trusted pre-authentication headers: when are they allowed?

Spring Security supports `RequestHeaderAuthenticationFilter` (pre-auth) and `PreAuthenticatedAuthenticationProvider`. They assume an **external system already finished authentication** and the app merely **receives the principal** via a header produced by that system.

In this model, **mTLS is a vital transport barrier** between proxy and app, yet additional conditions must hold.

### 10.1. Mandatory steps before trusting a header

```text
Client sends:
  X-Verified-User: admin       (UNTRUSTED)
  X-Forwarded-For: 127.0.0.1  (UNTRUSTED)
  Authorization: (optional)
                    |
                    v
At trusted edge:
  1. Strip ALL identity/assertion/forwarded headers from client
  2. Verify user login with OIDC/SAML/CAS, account/session/expiry
  3. Canonicalize issuer+subject and verified tenant intent
  4. Create canonical X-Verified-User (or signed internal token)
  5. Enforce HTTPS+mTLS to backend; verify backend SAN
                    |
                    v
At Spring backend:
  6. Require accepted proxy client cert (TLS)
  7. Enforce proxy certificate SAN/workload allowlist and network policy
  8. Reject direct/non-proxy paths or missing verified identity
  9. Map identity to local account; check role/tenant/resource
 10. Record audit decision (not raw credentials)
```

Missing step **(1)** or **(6–8)** lets a user send `X-Verified-User: admin` directly from a browser or internal service and become admin. Missing step **(2)** turns the proxy into a mere HTTP router rather than an auth proxy. Missing step **(9)** lets an identity from one IdP read another tenant's data.

### 10.2. Header-based auth and Spring authorization

Even when verified via a trusted proxy, `X-Verified-User: alice` is still only an **identifier**, not a role. The application must load `UserDetails`/authorities from local data or use an issuer-scoped policy mapping approved ahead of time.

Avoid:

```java
// WRONG: blindly trusting any X-Role the user might supply
String role = request.getHeader("X-Role");
grantRole(role);
```

Prefer:

```text
Verified external identity = (source issuer, stable subject)
Local mapping               = accountId
Tenant membership           = (accountId, tenantId, status)
Authorization               = (accountId, tenantId, action, resource)
```

If the proxy verifies user `alice` while the app has no account or the user is disabled, **fail closed**; never auto-provision `ROLE_ADMIN`. When supporting multiple IdPs, identity keys **must include the issuer**, not just email.

### 10.3. When both user and proxy use client certificates

An edge sometimes requires **browser/client mTLS** on HOP 1 and uses **proxy mTLS** on HOP 2. Two **different certificates** are involved:

- `ClientUserCert`: user or machine client → edge, presented in HOP 1 TLS.
- `ProxyWorkloadCert`: edge → Spring, presented in HOP 2 TLS.

When the backend reads `jakarta.servlet.request.X509Certificate` from HOP 2 TLS, it normally receives **`ProxyWorkloadCert`**, not `ClientUserCert`. The edge may pass verified user-cert metadata in a dedicated header, provided the header, tenant mapping, expiry, revocation, and injection defenses are enforced. **A raw header containing a PEM certificate does not prove the client possesses the private key**; trust either the client-cert verification **performed by the edge** or a strongly bound signed assertion.

## 11. Network controls: no bypassing the proxy

A severe deployment mistake occurs when edge NGINX enforces OIDC/mTLS/headers properly, yet a Kubernetes `NodePort` or Spring port `8080` stays reachable directly by other pods.

```text
Intended:
  Browser -> NGINX (identity verified) -> mTLS -> Spring

Attacker route:
  Other Pod -> http://spring-service:8080
               Header: X-Verified-User: admin
               -> Spring trusts header (INCORRECT)
```

The system can be bypassed even with valid edge certificates because the request **never went through the edge**. To prevent this:

1. Spring binds only the protected TLS port, with no extra public HTTP listener running.
2. Kubernetes NetworkPolicy/SGs/firewalls restrict inbound traffic to **edge proxy/sidecar identities** and required ports.
3. Cluster routes/Ingress rules block external access directly to backend Services/NodePorts/LoadBalancers.
4. Any separate admin/actuator/management listener has its own network/mTLS/authorization policy creating zero bypasses.
5. No "internal VIP" is implicitly accepted as a trusted proxy without an mTLS certificate.
6. Container/pod network interfaces and loopback debug endpoints are audited.
7. Each network segment enforces **deny-by-default** with tested exceptions, never an overly broad "allowed CIDR" table.
8. When TLS terminates at an Envoy sidecar, the JVM may listen on localhost HTTP only if the sidecar → app path is strictly isolated (loopback namespace, policy, iptables/mesh config); verify no other pod can reach the app listener.
9. Load balancers/health checks needing unauthenticated checks define explicit paths and transport trust rather than a "health bypass all".
10. Keep egress policies: a compromised internal workload could attempt SSRF or reach the backend across a gateway-less hop.

**mTLS proves which peer connected over a TLS path**, yet does not ensure **every request to the app must travel that path**. A bypass path is an architectural flaw, not a weak TLS cipher.

## 12. TLS in a service mesh: know exactly where the proxy stands

With an Envoy/Istio/Linkerd sidecar in Kubernetes:

```text
Incoming request
  -> ingress gateway
  -> [mTLS] sidecar of pod Spring
  -> [often localhost/plain HTTP] Spring JVM
```

In this setup, **mTLS may terminate at the sidecar**, not Spring's embedded Tomcat. Consequently:

- `server.ssl.client-auth=need` in Spring might **not apply** to sidecar→JVM traffic if the sidecar sends localhost HTTP.
- Peer workload certificates are verified by Envoy/Istio, not servlet certificate attributes.
- NetworkPolicy/sidecar interception rules must prevent direct pod-IP/port access bypassing the mTLS sidecar.
- Clearly define mesh-issued **certificate SAN URIs/workload identities**, trust domains, workload selectors, and authorization policies.
- A mesh running `PERMISSIVE` mTLS during migration still allows plaintext traffic; **never report "mTLS enforced"** while plaintext paths remain open.
- Service-to-service JWT/user authorization is still needed at the app or ext-authz gateway, beyond workload mTLS alone.

**Do not stack mTLS at every layer simultaneously without understanding who terminates and who verifies certificates.** Double-layered TLS can work, yet complicates truststores, SNI, hostnames, and debugging. Diagram every TLS handshake from origin to termination before enabling policies.

### 12.1. When Envoy performs upstream mTLS

Envoy uses `UpstreamTlsContext` to supply a client certificate upstream and `validation_context.trusted_ca` plus SAN matchers/auto SNI validation to verify server identity. Likewise, the backend/sidecar uses `DownstreamTlsContext.require_client_certificate` and trusted CAs/policies to require the Envoy peer's identity.

Configure explicit CA + SAN validation; Envoy docs warn that **upstream server certificate validation is not enabled automatically** without a validation context. Never assume that naming a transport socket `tls` means Envoy verifies backend certs, or that a cert from a trusted CA alone maps to the right workload.

## 13. Certificate errors and diagnostic clues

| Symptom | Suspected hop/layer | How to check |
| --- | --- | --- |
| Browser reports invalid certificate | HOP 1 browser→proxy | Public cert, SAN `portal.example.org`, chain/expiry |
| NGINX returns 502 calling backend | HOP 2 proxy→Spring | Upstream TLS handshake, client cert, `proxy_ssl_verify`, backend logs |
| NGINX logs `upstream SSL certificate verify error` | Proxy verifying backend cert | `proxy_ssl_trusted_certificate`, CA chain, SAN, SNI, expiry |
| Spring/Tomcat reports client cert required | Backend TLS handshake | `client-auth=need`, NGINX `proxy_ssl_certificate` and private key |
| Spring logs `PKIX path building failed` | Backend untrusting proxy cert | Proxy CA, truststore chain, EKU/validity |
| NGINX handshake sends no client cert | Proxy config | Missing `proxy_ssl_certificate`/key or cert/key mismatch |
| SAN mismatches `backend.internal.example.org` | Backend TLS certificate | Issue cert with right hostname; set accurate `proxy_ssl_name`/SNI |
| TLS OK yet user gets `401` | End-user authentication | Missing/invalid token issuer/audience/expiry or pre-auth principal |
| TLS OK, user gets `403` | Authorization | Tenant/roles/object ownership, allowed proxy identity policy |
| Single backend node fails | HA cert/secret/truststore drift | Compare versions, keystore alias/SAN, CA, rollout |
| Proxy accepts any backend cert | `proxy_ssl_verify` disabled | Enable verify and test unknown CA; never disable TLS |
| Proxy trusts CA yet hits wrong backend | Unchecked hostname/SAN | Verify expected SAN/SNI, DNS/routing/mesh policy |
| mTLS succeeds from unexpected service | Overly broad trust CA or missing SAN allowlist | Workload identity matching/NetworkPolicy/CA scope |
| Valid JWT rejected by API | Wrong `aud` or missing scope/tenant policy | Inspect **verified** token issuer/audience/scopes |
| Client sending `X-Verified-User=admin` logs in | Header spoofing/missing edge strip | Edge strips/rewrites headers; backend trusts mTLS only |
| Stripped `X-Forwarded-*` yet forgot `Forwarded` | RFC header bypass | Strip both header families at the edge |
| OAuth2/SAML callback URL switches to HTTP | Wrong forwarded proto/host | Trusted proxy forwarding/canonical app URL, Secure cookies |
| Health check fails | Probe lacks client cert | Design dedicated TLS probe/sidecar/local management path |
| Failures after certificate rotation | Out-of-sync truststore/cert versions | Controlled dual trust, canary, rollback |
| Handshake CPU/latency spike | Connection pooling/rotation/protocol | Monitor TLS handshakes, session reuse, timeouts/limits |
| Revoked client cert still accepted | Revocation policy inactive | CA/CRL/OCSP or short-lived certs and workload policy |
| Browser logs out yet backend returns 200 | Local session/token unrevoked | Session expiry, token revocation, authz policy; mTLS never logs users out |

**Troubleshooting requires knowing "who is the TLS client on the failing hop"**. If NGINX distrusts Spring's cert, fix **NGINX trust** and Spring's server cert. If Spring distrusts the proxy's cert, fix **Spring trust** and NGINX's client cert. Never dump every CA into both systems blindly.

## 14. Safe TLS/mTLS testing commands

**Run only in staging/lab environments you are authorized to administer.** Filenames assume provisioning via secret distribution, not instructions to mint certificates without an approved CA.

### 14.1. Inspecting server certificate and chain from NGINX's side

```bash
openssl s_client \
  -connect backend.internal.example.org:8443 \
  -servername backend.internal.example.org \
  -CAfile backend-server-ca.pem \
  -verify_return_error </dev/null
```

When the backend requires a client certificate, running **without a cert** can fail the handshake even when the server CA/SAN is valid. For a full test, run:

```bash
openssl s_client \
  -connect backend.internal.example.org:8443 \
  -servername backend.internal.example.org \
  -cert edge-proxy-client.crt \
  -key edge-proxy-client.key \
  -CAfile backend-server-ca.pem \
  -verify_return_error </dev/null
```

This checks the TLS handshake and certificate chain/verify return code without printing private keys. `openssl s_client` does not test application JWT/tenant authorization, and depending on OpenSSL version hostname checking requires `-verify_hostname backend.internal.example.org`; include it when testing:

```bash
openssl s_client \
  -connect backend.internal.example.org:8443 \
  -servername backend.internal.example.org \
  -verify_hostname backend.internal.example.org \
  -cert edge-proxy-client.crt \
  -key edge-proxy-client.key \
  -CAfile backend-server-ca.pem \
  -verify_return_error </dev/null
```

If OpenSSL reports `Verify return code: 0 (ok)` while NGINX still returns 502, do not assume mTLS is wholly fine: check application HTTP, client identity policies, reverse proxy routing, network MTU/timeouts, and JWTs. OpenSSL uses its own truststore rather than NGINX's or the JVM's unless pointed at the exact same CA bundle.

### 14.2. Calling the backend with curl, with and without a client cert

```bash
# Positive transport: trusted proxy certificate in test.
curl -i \
  --cacert backend-server-ca.pem \
  --cert edge-proxy-client.crt \
  --key edge-proxy-client.key \
  https://backend.internal.example.org:8443/api/health

# Negative transport: NO client certificate.
curl -i \
  --cacert backend-server-ca.pem \
  https://backend.internal.example.org:8443/api/health
```

Expected: the first command can return HTTP 200 when backend health is `permitAll` in Spring **and the cert is valid**; the second must fail the client-cert requirement. Depending on TLS 1.2/1.3, curl may report handshake failure, connection closed, TLS alert, or container HTTP 400; **the essential point is that the request is never processed as authenticated/authorized**.

Run separate tests with a cert signed by another CA (even with a matching SAN) and a cert from the trusted CA whose identity is not on the allowed proxy list; both must be rejected by trust policy, not merely missing-cert errors.

### 14.3. Testing that user authentication remains independent

```bash
curl -i \
  --cacert backend-server-ca.pem \
  --cert edge-proxy-client.crt \
  --key edge-proxy-client.key \
  https://backend.internal.example.org:8443/api/me
```

Expected: TLS mTLS passes, yet `/api/me` requires a JWT and returns `401 Unauthorized` without a Bearer access token.

With a **validly issued test access token**:

```bash
curl -i \
  --cacert backend-server-ca.pem \
  --cert edge-proxy-client.crt \
  --key edge-proxy-client.key \
  -H "Authorization: Bearer TEST_ACCESS_TOKEN" \
  https://backend.internal.example.org:8443/api/me
```

`TEST_ACCESS_TOKEN` is an illustrative placeholder, **not a real token**; the command will return 401 unless replaced with a valid token from the test IdP carrying the right issuer/audience. In real scripts, load secrets securely, keeping tokens out of shell history, process lists, CI logs, and screenshots.

**Never use `curl -k`/`--insecure` or a trust-all `TrustManager` to make a test return 200.** That disables server-identity verification in the TLS client, defeating what you are testing.

### 14.4. NGINX syntax, logs, and depth of testing

```bash
nginx -t
```

This checks syntax/conventions, **not** whether private keys/certs/truststores are actually readable at runtime or whether backend SAN verification succeeds. After an approved config reload, test via staging edge requests and inspect NGINX upstream TLS status, backend peer cert policies, redacted Spring logs, and authz decisions.

**Never log raw `Authorization`, cookies, certificate private keys, or PII in audit logs.** Log approved cert IDs/SHA-256 fingerprints, SAN identities, TLS versions, policy decisions, correlation/trace IDs, and HTTP statuses — per retention and sensitivity policies.

## 15. Standalone Java 17 demo: proving mTLS does not replace user authentication

The console demo below **does not implement TLS, PKIX, JWT decoding, or real networking**. It simulates **decision logic given verified outcomes from trusted security components**, demonstrating that **mTLS peer**, **user token**, and **tenant authorization** are checked independently. All `verified` booleans are **test fixtures** only; never read such booleans from HTTP headers/browsers.

File `ProxyMtlsBoundaryDemo.java`:

```java
import java.util.Map;
import java.util.Set;

public final class ProxyMtlsBoundaryDemo {

    enum Decision {
        ALLOW,
        DENY_TRANSPORT,
        DENY_PROXY_IDENTITY,
        DENY_USER_AUTHENTICATION,
        DENY_TENANT
    }

    record Evidence(
        boolean tlsPeerValidated,
        String proxyWorkloadIdentity,
        boolean userTokenValidated,
        String localAccountId,
        String requestedTenantId
    ) { }

    private static final Set<String> ALLOWED_PROXIES =
        Set.of("spiffe://corp.example/edge/portal-proxy");

    private static final Map<String, Set<String>> MEMBERSHIPS =
        Map.of("acct-42", Set.of("org-red"));

    static Decision decide(Evidence evidence) {
        if (evidence == null || !evidence.tlsPeerValidated()) {
            return Decision.DENY_TRANSPORT;
        }

        if (!ALLOWED_PROXIES.contains(
                evidence.proxyWorkloadIdentity())) {
            return Decision.DENY_PROXY_IDENTITY;
        }

        if (!evidence.userTokenValidated()
                || evidence.localAccountId() == null) {
            return Decision.DENY_USER_AUTHENTICATION;
        }

        Set<String> tenants = MEMBERSHIPS.getOrDefault(
            evidence.localAccountId(), Set.of());

        if (!tenants.contains(evidence.requestedTenantId())) {
            return Decision.DENY_TENANT;
        }

        return Decision.ALLOW;
    }

    public static void main(String[] args) {
        Evidence good = new Evidence(
            true,
            "spiffe://corp.example/edge/portal-proxy",
            true, "acct-42", "org-red");

        Evidence noMtls = new Evidence(
            false,
            "spiffe://corp.example/edge/portal-proxy",
            true, "acct-42", "org-red");

        Evidence rogueProxy = new Evidence(
            true,
            "spiffe://corp.example/other-workload",
            true, "acct-42", "org-red");

        Evidence noUserToken = new Evidence(
            true,
            "spiffe://corp.example/edge/portal-proxy",
            false, "acct-42", "org-red");

        Evidence wrongTenant = new Evidence(
            true,
            "spiffe://corp.example/edge/portal-proxy",
            true, "acct-42", "org-blue");

        System.out.println("good=" + decide(good));
        System.out.println("noMtls=" + decide(noMtls));
        System.out.println("rogueProxy=" + decide(rogueProxy));
        System.out.println("noUserToken=" + decide(noUserToken));
        System.out.println("wrongTenant=" + decide(wrongTenant));
        System.out.println("null=" + decide(null));
    }
}
```

Run with JDK 17+, no Spring required:

```bash
javac --release 17 ProxyMtlsBoundaryDemo.java
java ProxyMtlsBoundaryDemo
```

**Deterministic** stdout:

```text
good=ALLOW
noMtls=DENY_TRANSPORT
rogueProxy=DENY_PROXY_IDENTITY
noUserToken=DENY_USER_AUTHENTICATION
wrongTenant=DENY_TENANT
null=DENY_TRANSPORT
```

**Explanation:**

- `good` succeeds only when **all three layers**—transport/workload, user authentication, and tenant membership—pass.
- `noMtls` is rejected even when the user holds a token, because the security contract requires traversing trusted proxy TLS.
- `rogueProxy` may hold a client cert signed by a trusted CA, yet its **workload identity is unauthorized**.
- `noUserToken` demonstrates mTLS does not turn an unauthenticated browser into an authenticated user.
- `wrongTenant` shows valid identity at both layers still grants zero access to an organization the user does not belong to.
- `null` lacks evidence and fails closed.

**Never use this class as a real mTLS/JWT implementation.** `tlsPeerValidated` must come from a TLS/PKIX engine; proxy identity must have its SAN verified by the TLS terminator/service mesh; `userTokenValidated` from Spring OAuth2 Resource Server/IdP validation; membership from an authoritative database/service. Any browser-sent boolean must **never** be used as evidence.

## 16. Comprehensive integration test matrix

Negative cases require a staging environment with test CAs/certificates, network policies, and a real backend TLS listener. Never use production certs/keys to intentionally craft negative tests.

| Test case | Input or configuration | Expected result |
| --- | --- | --- |
| **Happy path** | Browser HTTPS edge, NGINX mTLS backend with valid SAN/CA and valid user access token/tenant | 200 with right resource/role |
| **HOP 1 HTTPS only** | Backend configured with HTTP, no mTLS | Fails requirements; fail security acceptance |
| **HOP 2 one-way TLS** | Backend HTTPS with `client-auth: none` | Fails to verify proxy client; fail mTLS requirement |
| **No client certificate** | Connect to TLS 8443 without presenting cert | TLS handshake/connection rejected; never reaches app |
| **Untrusted client CA** | Proxy cert issued by unknown CA | Rejected |
| **Expired proxy cert** | Client cert past expiration | Rejected per PKIX/time policy |
| **Not-yet-valid client cert** | Future NotBefore | Rejected |
| **Wrong client EKU** | Client cert lacks clientAuth profile | Rejected per TLS/PKI policy |
| **Trusted CA, wrong proxy SAN** | Other service holds cert from same CA | Rejected by allowed proxy identity policy |
| **Wrong backend server SAN** | NGINX connects to hostname A, sees cert for B | NGINX rejects; never disable `proxy_ssl_verify` |
| **Untrusted backend server CA** | Backend cert CA absent from NGINX trust bundle | NGINX rejects/502 |
| **NGINX `proxy_ssl_verify` off** | Sends client cert without verifying backend | Fails configuration/security acceptance |
| **SNI mismatch** | Upstream proxy sends wrong SNI | TLS verify fails or misroutes; fix SNI |
| **Proxy cert/key mismatch** | NGINX key does not match cert | Handshake/config failure |
| **Client spoofs identity header** | Browser sends `X-Verified-User=admin` | Edge strips; app does not elevate identity |
| **Forwarded header spoof** | Browser sends `Forwarded: host=evil...` or XFH | Edge strips/overwrites; callback/host/authz unaffected |
| **Direct backend API** | Bypass NGINX from unauthorized pod/host | Network/TLS peer deny; never reaches controller |
| **Internal workload with cert from same CA** | Service not on proxy allowlist | Rejected by peer identity |
| **mTLS succeeds, no access token** | Valid proxy cert, no Bearer JWT | Spring returns 401 for `/api/me` |
| **mTLS succeeds, invalid JWT signature** | Forged token or signed by wrong key | 401 |
| **mTLS succeeds, wrong JWT issuer** | Signed token from unapproved issuer | 401 |
| **mTLS succeeds, wrong JWT audience** | Token `aud` targets another API | 401 |
| **mTLS succeeds, expired JWT** | `exp` in the past | 401 |
| **mTLS succeeds, wrong tenant** | Authenticated user lacks resource tenant membership | 403/404 without leaking data |
| **mTLS succeeds, privilege collision** | Client sends `X-Role=ADMIN` header | Does not escalate; app uses verified policies |
| **Actuator/management alternate port** | Another port publicly exposed without cert policy | Fails security acceptance; isolate/close |
| **LB direct routing** | DNS/VIP hits backend pod bypassing ingress | Fails security acceptance; deny-by-default |
| **TLS 1.0/1.1 client** | Supports only weak versions | TLS negotiation rejected |
| **Certificate rotation** | Roll NGINX and backend CAs/certs with valid overlap | Never widens trust; traffic healthy after cutover |
| **Compromised cert** | Proxy client private key leaked | Revoke/rotate, verify alerts, stop trusting |
| **Health probe without client cert** | `/api/health` permitAll yet TLS need | Probe fails at TLS; configure proper probe |
| **Service mesh permissive traffic** | Policy allows plaintext alongside mTLS | Must not be marked mTLS enforced |
| **Token forwarded to wrong upstream** | NGINX routes to wrong `proxy_pass` host | Server SAN verification blocks wrong host; audit policy |
| **Direct user cert mistaken as proxy cert** | Client user cert not on proxy allowlist | Workload trust rejected |
| **Failover to another proxy** | Proxy B uses unapproved cert SAN/CA | Blocked from backend until identity policy authorizes it |
| **Time drift** | Clock skew affects cert NotBefore/After/validation | TLS fails; fix NTP rather than disabling time checks |
| **Private key readable by non-service account** | Broken permissions in container | Fails operational security acceptance |
| **Authorization after valid mTLS+JWT** | User lacks role/record permission | Denied; never treat certificate as a role |

**Pass criterion for mTLS:** Not merely seeing HTTP 200 in a browser or getting `curl --cert` to work. You must prove the backend **actually demands a client cert**, the proxy **actually verifies the server cert/SAN**, peer workload identities match the allowlist, and requests **cannot** take any bypass path. Only then verify user/tenant business authorization.

## 17. Operational procedures for certificate rotation and incidents

### 17.1. Controlled zero-downtime rotation

```text
T0: Old certs already approved:
  proxy client cert P_old, backend server cert S_old,
  valid CA trust anchors / identity policies.

T1: Prepare:
  issue P_new and S_new with valid SAN/EKU/chain,
  verify private keys, trust policies, and telemetry.

T2: Shift trust:
  backend trusts new proxy CA/identity if needed;
  NGINX trusts new backend server CA if needed;
  overlap old+new only within a short window per policy.

T3: Canary:
  one proxy→one backend node uses new certs;
  test mTLS + issuer/audience/tenant, reject unknown certs.

T4: Deploy:
  roll node/proxy gradually; monitor TLS errors, 401, 403, 502.

T5: Revoke:
  remove old certificate/CA/identity from trust policy,
  revoke if compromised; verify no client still uses old certs.

T6: Audit:
  record fingerprint, issuer, SAN, expiration date, ticket,
  change owner, policy version, and negative test results.
```

If the CA issuing client certs changes, **Spring's truststore** must be updated before the proxy switches certificates. If the CA issuing backend server certs changes, **NGINX's `proxy_ssl_trusted_certificate`** must be updated before Spring deploys the new server cert. Always verify both directions: **proxy trusting backend** and **backend trusting proxy**.

If a key/cert is compromised, do not merely wait for expiry. Execute incident response: revoke/rotate, isolate compromised workloads, audit requests/logs, tighten permissions, and trigger revalidation of affected sessions/tokens according to risk severity.

### 17.2. Useful monitoring signals

Monitor while avoiding logging secrets:

- TLS handshake success/failure rates per hop, protocol/cipher, and X509/PKIX errors.
- Certificate expiration dates, fingerprints, issuers, SAN/workload IDs, and truststore/policy versions.
- `502/503/504` at NGINX when upstream SSL verification/connection fails; distinguish from Spring `401/403`.
- Backend connection attempts without certs or with unknown CA/SAN certs.
- Direct traffic hitting backend ports outside the allowlist.
- JWT authentication failures by issuer/audience/exp/revocation (never log raw JWTs).
- Unauthorized tenant/resource actions, denied header spoofing attempts, invalid forwarded hosts.
- Differences between a single pod's cert error and cluster-wide cert failures.
- CPU/latency overhead from TLS handshakes and session reuse/connection pooling.
- Stale sessions on user logout/role changes and service-mesh policy drift.

**Logging:** Logging sanitized certificate subject/SAN/fingerprint/CA and controlled route/policy decisions is appropriate. Never log TLS private keys, full client cert PEMs needlessly, Authorization Bearer values, session cookies, SAMLResponse, ID Tokens, OIDC authorization codes, or unnecessary PII.

## 18. Self-check questions with answers

**Q1.** Browser uses HTTPS to NGINX. NGINX uses `proxy_pass http://backend:8080`. Is this end-to-end mTLS?

**Answer:** No. HOP 2 is plaintext HTTP; HOP 1 HTTPS terminates at NGINX. Enable HTTPS/mTLS between proxy and backend if policy requires it.

**Q2.** NGINX configures `proxy_ssl_certificate`/`proxy_ssl_certificate_key` without `proxy_ssl_verify on`. Is that secure enough?

**Answer:** No. NGINX sends a client cert upstream yet fails to verify the backend's server cert/SAN under two-way mTLS trust. Enable `proxy_ssl_verify on`, set the CA and expected hostname/SNI, and test with rogue certificates.

**Q3.** Does Spring `server.ssl.client-auth: want` guarantee every request presents a client cert?

**Answer:** No. `want` makes it optional, so clients can connect without a cert. For mandatory mTLS, use `need` with a truststore and allowed proxy identities.

**Q4.** Any service with a Corporate CA certificate can connect to the Spring backend; the team claims only NGINX can connect. Is that accurate?

**Answer:** Not sufficient. A broad trusted CA does not distinguish proxy identity. Enforce allowed SAN/URI workload policies, dedicated CAs, network segmentation/ACLs, and test with another service's cert.

**Q5.** Browser sends `X-Authenticated-User: admin` to the proxy; the proxy forwards it unchanged and the backend trusts it. Does mTLS stop this impersonation?

**Answer:** No. mTLS proves the proxy workload on hop 2, not the user header. The proxy must strip/overwrite headers after authenticating the user; the backend must accept only the proper route/trust boundary and check permissions.

**Q6.** Spring backend enables `http.x509()`, and the proxy→app TLS client cert is NGINX's cert. Who does Spring authenticate?

**Answer:** The TLS cert seen by the backend is normally the **NGINX workload**, not the browser user. End-user auth requires separate token/pre-auth evidence.

**Q7.** Proxy mTLS succeeds yet without a Bearer token `/api/me` returns 401. Is this an mTLS error?

**Answer:** Not necessarily. That enforces separate user authentication; the TLS peer passed while the resource server requires an access token with the right issuer/audience.

**Q8.** App enforces mTLS on 8443 yet HTTP 8080 remains reachable from other pods. Can you claim mTLS is enforced?

**Answer:** No. Callers can bypass via the HTTP listener. Close/isolate 8080, enforce network deny-by-default, and audit all routes/management ports.

**Q9.** Envoy mesh runs mTLS between gateway and sidecar, while the sidecar calls the app over localhost HTTP. Must `server.ssl.client-auth: need` be set in Spring?

**Answer:** Not by default; mTLS terminates at the sidecar, so verify mesh policies, sidecar→app isolation, and absence of bypasses. If direct TLS to the JVM is required, configure TLS/mTLS separately; the two models are not automatically equivalent.

**Q10.** App verifies proxy mTLS and the user logged into the IdP, yet lacks tenant authorization. May all reports be opened?

**Answer:** No. Membership/role/resource-object authorization still applies after user authentication. Proxy mTLS never grants business permissions.

## 19. Pre-production acceptance checklist

- [ ] Diagrammed HOP 1 browser→edge, HOP 2 edge→app, and HOP 3 app→services, marking TLS termination and decryption points.
- [ ] HOP 2 enforces HTTPS + **mutual certificate authentication**, not merely one-way `proxy_pass https`.
- [ ] NGINX/Envoy validates backend server certificates: CA, SAN/hostname, SNI, validity, policy; `proxy_ssl_verify off` is never left on.
- [ ] NGINX presents a client cert/key dedicated to the proxy workload; keys are protected with rotation and an owner.
- [ ] Spring sets `client-auth=need` + truststore trusting only approved client CAs; `want` is not used where mandatory.
- [ ] Enforced allowed workload identity SAN/URI/CA policies or dedicated CAs plus network ACLs; never accept arbitrary certs from a broad CA.
- [ ] Proxy/sidecar exposes no direct HTTP backend listeners, alternate management ports, or NodePort bypasses.
- [ ] Edge strips/overwrites all user identity headers and untrusted caller `Forwarded`/`X-Forwarded-*` headers; app never uses self-asserted raw headers.
- [ ] If using `RequestHeaderAuthenticationFilter`, a clear pre-auth contract, account mapping, and session expiration/revocation exist.
- [ ] If using OAuth2 Resource Server, backend validates access token issuer, signature/JWK, audience, expiry, and scope; wrong-audience ID Tokens are rejected.
- [ ] Spring X.509 principals are understood as the **client peer of the hop reaching the JVM**, not automatically the browser user when TLS terminates at a proxy.
- [ ] User/tenant/resource authorization is independent of mTLS, with tests for email/role/header spoofing and cross-tenant access.
- [ ] Certificates carry valid SANs/EKUs and chains, within validity windows; clocks/NTP are synchronized.
- [ ] Two-way truststores and keystores serve distinct roles; passwords/keys never appear in repos/container images/logs.
- [ ] Certificate issuance/rotation/revocation and trust overlap are governed with canary and rollback plans.
- [ ] Verified all NGINX pods/Spring nodes run compatible cert/CA/policy versions.
- [ ] Health probes, actuator/management, gRPC/WebSocket, and background service traffic have matching transport trust.
- [ ] Service mesh is not left in permissive mode when mTLS is required; plaintext rejection is tested.
- [ ] Tests cover missing cert, wrong CA/SAN, expired cert, wrong EKU, identity spoofing, wrong JWT aud/iss, direct backend routes, and role/tenant denials.
- [ ] TLS private keys/`Authorization`/cookies never appear in access logs/traces; audits capture only required metadata.
- [ ] Monitoring tracks SSL handshake failures, 502 upstream errors, 401 auth, 403 authz, cert expiry/rotation, and bypass traffic attempts.
- [ ] Runbooks distinguish the 4 failure domains: HOP 1 TLS, HOP 2 TLS/mTLS, user authentication, and business authorization.
- [ ] Least privilege and deny-by-default are enforced across network, trust policy, client cert issuance, JWT audience, and tenant authorization.

**Conclusion:** In the **proxy authentication** model, **mTLS between proxy and application** provides mutual **workload** authentication and protects transport **strictly along the proxy → app hop**. It **does not** restore an end-to-end browser TLS session terminated at the proxy, does not implicitly propagate browser user identity to Spring, and does not grant business privileges. A proper setup requires **NGINX verifying the backend cert + presenting a proxy client cert**, **Spring demanding and verifying the client cert**, **blocking all bypass paths**, and a **separate end-user authentication/authorization mechanism** (backend-verified JWTs or pre-auth headers under a strict trust contract). Only when every one of these layers holds may requests be admitted to protected resources.

## 20. Official references

1. [NGINX – Securing HTTP Traffic to Upstream Servers](https://docs.nginx.com/nginx/admin-guide/security-controls/securing-http-traffic-upstream/): `proxy_ssl_certificate`, `proxy_ssl_certificate_key`, `proxy_ssl_trusted_certificate`, and `proxy_ssl_verify`.
2. [NGINX – ngx_http_proxy_module](https://nginx.org/en/docs/http/ngx_http_proxy_module.html): defaults `proxy_ssl_verify off`, `proxy_ssl_server_name off`, and `proxy_ssl_name` for SNI/hostname.
3. [Spring Boot – Common Application Properties: server.ssl](https://docs.spring.io/spring-boot/appendix/application-properties/): `server.ssl.client-auth`, `key-store`, `trust-store`, `enabled-protocols`.
4. [Spring Boot – SSL](https://docs.spring.io/spring-boot/reference/features/ssl.html): TLS configuration and SSL bundles for server/client.
5. [Spring Security – X.509 Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/x509.html): TLS client certificates, principal mapping, and Spring `x509()`.
6. [Spring Security – OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): `NimbusJwtDecoder`, issuer/audience validation, and `SecurityFilterChain`.
7. [Spring Security – AbstractPreAuthenticatedProcessingFilter API](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/web/authentication/preauth/AbstractPreAuthenticatedProcessingFilter.html): external pre-authentication and header principal responsibility assumptions.
8. [Spring Framework – ForwardedHeaderFilter and Security Considerations](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html): trusting forwarded headers only from a trusted proxy, stripping `Forwarded` and `X-Forwarded-*` at the edge.
9. [Envoy – Securing Envoy, Upstream/Downstream TLS](https://www.envoyproxy.io/docs/envoy/latest/start/quick-start/securing): `UpstreamTlsContext`, `DownstreamTlsContext.require_client_certificate`, trust CA, and SAN.
10. [OWASP – TLS Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html): TLS/mTLS, certificate validation, and cipher policies.
11. [OWASP – Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): identity verification and authentication boundaries.
12. [OWASP – Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): deny-by-default, least privilege, and resource authorization after authentication.
13. [NIST SP 800-207 – Zero Trust Architecture](https://csrc.nist.gov/pubs/sp/800/207/final): never trusting internal networks implicitly; combining workload identity and access policy.
14. [RFC 8446 – TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446): TLS handshake, certificate authentication, and channel confidentiality/integrity.
15. [RFC 5280 – PKIX Certificate Path Validation](https://www.rfc-editor.org/rfc/rfc5280): X.509 certificate chains, validity, extensions, and trust anchors.
