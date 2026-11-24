# Distinguishing mTLS at the Proxy from Application-Verified Identity

## 1. The Problem: Does "Gateway Checked mTLS" Mean the App Knows Who Is Calling?

A Spring WebFlux system frequently sits behind an API Gateway, Ingress Controller, Envoy, NGINX, or service mesh. Externally, clients send requests over **mutual TLS (mTLS)**: both server and client present matching certificates during the TLS handshake. The gateway can verify the certificate chain, CA policy, and certificate fields, then forward the request to the WebFlux backend.

A very common misconception is:

> **A gateway authenticating a TLS connection does not automatically mean Spring Security on the backend has verified the end-user/workload identity and granted the right application permissions.**

A common architecture:

~~~text
        mTLS connection 1                 mTLS connection 2 (optional)
Client ----------------------> Proxy ------------------------------> WebFlux API
 cert C                     cert P                cert P           Server
   |                          |                        |               |
   | TLS handshake proves     | TLS to upstream        | Backend        |
   | possession of C private  | proves proxy P         | sees P as TLS   |
   | key to the proxy         | (not necessarily C)    | peer            |
~~~

Distinct observations must be kept separate:
- The proxy may authenticate client certificate C on **hop 1**.
- The WebFlux backend connects to the proxy on **hop 2**. If hop 2 uses mTLS, the backend typically sees **proxy P itself**, not C.
- The proxy may send HTTP headers like `X-Forwarded-Client-Cert` (XFCC) or `X-Authenticated-User` asserting the identity it checked; that is an **upstream assertion**, not TLS proof directly observed by the backend.
- The application needs a **protected, verified authentication source**, paired with mapping certificate identity → account/service principal → authorities/roles → data permissions.
- Holding a valid certificate also does not automatically grant permission to read every report or become `ROLE_ADMIN`.

This lesson belongs to **Advanced Authentication** in the Spring Security - reactive module. It focuses on trust boundaries, secure architecture choices, and practical verification in Java 17 + Spring WebFlux.

### Learning Objectives

After this lesson, you will be able to:

1. Distinguish **TLS peer identity**, **gateway assertion**, **Spring Security Authentication**, and **business authorization**.
2. Explain what is verified at the TLS handshake vs what cannot be inferred from HTTP headers.
3. Recognize when `ServerHttpSecurity.x509(...)` makes sense vs when the app only sees the proxy's certificate.
4. Handle `XFCC`/`X-Forwarded-*` headers properly, avoiding header spoofing and confused-deputy bugs.
5. Design two options: **direct mTLS to the application** or **proxy mTLS + app-verified identity assertion**.
6. Use Reactive OAuth2 Resource Server to verify a JWT assertion signed by a trusted gateway, including `iss`, `aud`, `exp`, signature, and scopes.
7. Write `WebTestClient` tests: forged headers do not authenticate, validly signed JWTs succeed, wrong signature/issuer/audience/expiration fail, and missing permissions return 403.
8. Distinguish local tests using real signed JWTs from integration tests requiring real TLS handshakes, certificates, and proxies.
9. Design auditing, certificate rotation/revocation operations, network isolation, and multi-hop gateway handling.

## 2. What Does mTLS Actually Verify?

Standard TLS: the client verifies the server certificate to confirm it is talking to a server with a trusted name/key. With **mTLS**, the server also requires the client to present a certificate and prove possession of its private key during the TLS handshake.

At the connection where mTLS terminates, the verifier can:
- Verify the client certificate chain up to a trusted trust anchor/CA.
- Check certificate validity dates, algorithms/signatures, and constraints.
- Check key usage and extended key usage such as `clientAuth` when required by policy.
- Verify the peer possesses the matching private key via the TLS handshake.
- Read Subject/SAN/URI SAN (e.g., SPIFFE ID), fingerprint, issuer, and serial number.
- Enforce platform trust domains, revocation, or workload allowlists.

**However**, TLS does not inherently know "this user may view invoice 123" or "this workload has `ROLE_ADMIN`". That belongs to the system's **identity mapping and authorization**.

### 2.1. Certificate Subject ≠ Internal Account ≠ Access Rights

Suppose a certificate has:

~~~text
Subject: CN=report-client,O=Example
URI SAN: spiffe://corp.example/ns/finance/sa/report-reader
Issuer:  CN=Example Workload CA
~~~

There are three levels:

1. **Certificate identity:** an endpoint proved key possession and presented a valid certificate chain at a trust boundary.
2. **Application principal:** the system looks up/maps `spiffe://corp.example/ns/finance/sa/report-reader` to an internal principal such as `workload-report-reader`. This may involve checking account status, tenant, expiry, and risk/entitlements.
3. **Authorization:** is the principal allowed to call `GET /api/reports`, hold `reports.read` scope, and view records belonging to its tenant?

Never skip steps 2 and 3 just because a certificate's Subject/issuer "looks corporate".

### 2.2. CN vs SAN

Many older X.509 examples extract the Common Name (CN). Modern workload identity systems, however, prefer **Subject Alternative Name** entries of type DNS or URI, such as SPIFFE URIs. A CN can collide, be reused, or fail to express a strong application identifier.

Use SAN with an explicit trust policy and identity mapping. Even if a framework defaults to extracting CN, treat that as a **technical default**, not automatically the best policy for your organization's workloads or tenants.

### 2.3. A Valid Certificate Does Not Mean Unrevoked

A certificate whose `notAfter` lies in the future may still be revoked, or its service account disabled. Platforms must account for CA revocation policies (CRL/OCSP, short-lived certs, mesh rotation), network handling, and current authorization state.

**TLS certificate validation, account status, and resource permissions are three distinct controls.**

## 3. Four Trust Zones to Draw on the Diagram

~~~text
Untrusted external network
           |
           | Client certificate C, mTLS handshake
           v
+--------------------+
| Trusted proxy/edge |
| - Verify client C  |
| - Map cert -> ID   |
| - Apply edge rules |
+--------------------+
           |
           | Protected hop (TLS/mTLS, network policy)
           | Optionally signed identity assertion
           v
+------------------------------+
| Spring WebFlux Resource API  |
| - Verify gateway assertion   |
| - Construct Authentication   |
| - Map authorities            |
| - Check object/tenant access |
+------------------------------+
           |
           v
         Database
~~~

Each step needs a clear answer:

| Question | Responsible Party | Appropriate Evidence |
| --- | --- | --- |
| Does client possess private key C? | TLS terminator of client→proxy hop | Valid TLS handshake |
| Does cert C have valid chain/issuer/SAN? | Proxy or mTLS policy engine | TLS verification + cert policy |
| Does proxy forward true identity C or accept forged headers? | Proxy ingress config | Strip + set trusted headers/assertions |
| Is the proxy→backend hop protected? | Proxy + backend + network | TLS/mTLS, ACLs, network policy, allowlist |
| Does backend trust the assertion came from an authorized gateway? | WebFlux Security | Signature/JWKS or bound trusted channel |
| Is the assertion meant for this app and unexpired? | WebFlux decoder/validators | `iss`, `aud`, `exp`, `nbf`, `iat`, `jti` per policy |
| Is the principal authorized for the route? | Spring Security | `GrantedAuthority`/permission |
| May the principal read the specific record? | Domain service | Ownership/tenant/ABAC/entitlement |

Checking mTLS only at the proxy while ignoring the backend questions invites **header spoofing, confused-deputy attacks, ingress bypasses, or cross-tenant access**.

## 4. Three Common Architectures and What Spring Security Observes

### 4.1. Option A — Direct Client mTLS to WebFlux

~~~text
Client certificate C
       |
       | TLS handshake directly to Reactor Netty
       v
Spring WebFlux TLS endpoint
       |
       | ServerHttpSecurity.x509(...)
       v
X.509 principal extraction -> account lookup -> Authentication
       |
       v
authorizeExchange -> controller
~~~

Here WebFlux receives the client certificate **directly from the TLS connection terminated by Netty itself**. Spring Security Reactive provides `ServerHttpSecurity.x509(...)`; when enabled, the x509 authentication filter reads the certificate from the request's TLS info, extracts the principal, and invokes the authentication manager.

Prerequisites: the Netty TLS listener must require/verify client certificates; a proper truststore/CA is required; the app must map identities and enforce authorities. Merely enabling the `x509` DSL without configuring TLS client-auth **does not magically produce valid client certificates in TLS**.

### 4.2. Option B — Client mTLS to Proxy, Backend Trusts an Identity Assertion

~~~text
Client --mTLS (C verified)--> Proxy
                                 |
                                 | Mapping + signed JWT assertion:
                                 | iss=gateway, aud=webflux-api,
                                 | sub=client identity, exp≈now+60s
                                 v
                 WebFlux --ReactiveJwtDecoder--> Authentication
~~~

The backend verifies an **assertion cryptographically signed** by a trusted gateway/identity service. It does not need to parse a raw client certificate from an HTTP header to "reconstruct" TLS proof. Also protect the proxy→backend hop with network policies and TLS/mTLS, and never expose the backend directly to the Internet.

The assertion is minted **only after the proxy validates mTLS C** and maps it to an approved identity. The backend verifies the JWT signature, issuer, audience, lifetime, and permissions, never accepting an arbitrary client-supplied `sub`.

This is the option demonstrated in the Java 17 project below. **A gateway JWT assertion is not automatically the original client's OIDC ID token or OAuth access token**; it is a dedicated security contract between gateway and backend. Spring Security Resource Server supports signed JWTs and lets you enforce contract-specific validators.

### 4.3. Option C — Backend Sees Only the Proxy's mTLS

~~~text
Client --mTLS C--> Proxy --mTLS P--> WebFlux
                                  |
                                  v
                          TLS peer = proxy P
~~~

The backend knows it is talking to proxy P over mTLS. That protects **hop 2**, but proves nothing about who client C was on hop 1. If you enable `.x509(...)` in WebFlux under this architecture, X.509 authentication normally represents **proxy P**, not automatically C.

**Never map the proxy's CN/SAN as the end-user's identity.** To authorize on behalf of client C, you need a protected mechanism conveying and verifying C's identity plus application-level mapping.

## 5. XFCC and Identity Headers: HTTP Data, Not TLS Proof

Many proxies can send:

~~~http
X-Forwarded-Client-Cert: By=spiffe://corp.example/gateway;Hash=...;Subject="CN=report-client"
X-Authenticated-User: report-reader
X-Forwarded-Proto: https
X-Forwarded-For: 203.0.113.25
~~~

Meanings:
- `X-Forwarded-Client-Cert` (XFCC) is a structured header conveying certificate information across one or more hops per proxy convention.
- `X-Authenticated-User` is a **custom header** with no universal HTTP signing/validation mechanism.
- `X-Forwarded-For` and `Forwarded` are routing/protocol/client-address metadata, **not authenticated user identity**.
- `X-Forwarded-Proto=https` only tells you an upstream claims the original request used HTTPS; **it does not prove a TLS client certificate was verified**.

An attacker can send `curl -H 'X-Authenticated-User: admin'` to any HTTP endpoint they can reach. If the backend builds an `Authentication` from that header without a strict trust boundary, attackers can impersonate anyone.

### 5.1. XFCC Has Multiple Elements — Never Parse with Naive Split

Per Envoy documentation, text-format XFCC can contain multiple comma-separated elements, semicolon-separated key-value pairs, quoted/escaped values, or JSON formatting depending on configuration. It can represent a **chain of proxy hops**, not solely the original client certificate.

Do not write:

~~~java
// WRONG: both missing trust checks and parsing XFCC against the protocol.
String user = request.getHeaders()
        .getFirst("X-Forwarded-Client-Cert")
        .split("Subject=")[1];
grantRoleAdmin(user);
~~~

This is an **anti-pattern**, not valid code to deploy. Even parsing the format accurately **does not turn an HTTP header into TLS proof**.

### 5.2. Header Spoofing Risk via Proxy Bypass

If the backend is exposed directly (Service type LoadBalancer/NodePort, a second ingress, debug ports, port-forwarding, or an untrusted internal network), an attacker can send whatever headers they choose.

Even when the primary production ingress strips headers, a secondary entry path can bypass that policy. Therefore:
- Block direct ingress to the backend with network-level controls.
- Allow only trusted proxy workloads to connect; use mTLS on the proxy→backend hop when appropriate.
- Strip **all** client-supplied identity headers before the proxy sets new ones.
- Leave no unauthenticated path to sensitive routes.
- The backend should **independently verify a signed assertion** or identity proof at the security layer rather than trusting traffic merely because it arrived on a private network.

### 5.3. Header Names to Audit

Audit at least:
- `X-Forwarded-Client-Cert` and gateway-specific variants.
- `X-Client-Cert`, `X-SSL-Client-Cert`, `SSL_CLIENT_CERT`.
- `X-Authenticated-User`, `X-User`, `X-User-Id`, `X-Remote-User`.
- `Forwarded`, `X-Forwarded-For`, `X-Forwarded-Host`, `X-Forwarded-Proto`.
- `Authorization` if the gateway mints an assertion while the client also sends Bearer.

Do not normalize all these fields into a single identity. **Only one system-selected authentication channel** may construct `Authentication`. Remaining headers are for observability/routing after trust is established, never replacing authorization.

## 6. Envoy: SANITIZE, SANITIZE_SET, and the Risk of FORWARD_ONLY

Envoy's `HttpConnectionManager` provides `forward_client_cert_details` to handle XFCC.

Typical modes:
- **`SANITIZE`:** strips XFCC when forwarding upstream; the default in Envoy docs.
- **`SANITIZE_SET`:** strips any existing XFCC and sets it fresh from the current downstream mTLS connection's certificate.
- **`FORWARD_ONLY`:** forwards existing XFCC when downstream is mTLS, **without replacing its contents with the verified identity**.
- **`APPEND_FORWARD`:** appends current cert info to the chain, requiring an explicit parser/trust policy to tell "which hop is whom".
- **`ALWAYS_FORWARD_ONLY`:** forwards the header even when the request is not mTLS—especially dangerous if backends treat the header as authentication.

An illustrative Envoy `HttpConnectionManager` **configuration snippet** (not a complete runnable Envoy config):

~~~yaml
# Only the field snippet inside HttpConnectionManager:
forward_client_cert_details: SANITIZE_SET
set_current_client_cert_details:
  subject: true
  uri: true
~~~

Critical condition: the listener **must enforce real downstream mTLS verification** if you expect XFCC to reflect a verified client cert. The snippet above **does not configure CA trust, listeners, `transport_socket`, routing, or RBAC**.

**`SANITIZE_SET` mitigates inbound spoofing, yet still does not establish app identity by itself.** Spring WebFlux still needs assurance that the header truly came from the trusted gateway without bypass, and must map cert identity → app principal and authorize. For high assurance, a signed assertion as in Section 11 lets the backend cryptographically verify the source.

### 6.1. The Danger of FORWARD_ONLY in a Misconfigured Setup

Suppose a client sends:

~~~http
X-Forwarded-Client-Cert: Subject="CN=admin"
~~~

If the proxy forwards the header untouched and the backend treats `Subject=CN=admin` as authentication, the client can spoof identity. Even if the client completed a valid mTLS handshake using **a different CN**, forwarding a client-written header never proves `CN=admin`.

Solution: strip/sanitize untrusted headers, emit identity assertions only after certificate verification, and block direct backend access. Never judge security solely by the header name `X-Forwarded-Client-Cert`.

## 7. Spring Security Reactive X.509 When the App Directly Terminates mTLS

Spring Security supports **Reactive X.509 Authentication**:

~~~java
@Bean
SecurityWebFilterChain directMtlsChain(ServerHttpSecurity http) {
    return http
            .x509(Customizer.withDefaults())
            .authorizeExchange(ex -> ex
                    .anyExchange().authenticated())
            .build();
}
~~~

This snippet belongs in a Spring WebFlux configuration and requires importing `Bean`, `ServerHttpSecurity`, `SecurityWebFilterChain`, and `Customizer`. It applies when Reactor Netty receives a **client certificate from a real TLS handshake**.

Per Spring Security documentation, when left at defaults:
- The default principal extractor in current releases is `SubjectX500PrincipalExtractor`, typically extracting CN from the X.500 subject.
- The default authentication manager is `ReactivePreAuthenticatedAuthenticationManager`, checking that the user account for the extracted name exists and is not locked, disabled, or expired.
- You can customize `principalExtractor(...)` and `authenticationManager(...)` for stricter trust domain/SAN/entitlement mapping.

**Configuring X.509 principal extraction does not replace the server's truststore and TLS client certificate verification.**

### 7.1. TLS Configuration at Reactor Netty / Spring Boot

Configuration template (applicable only once you have real keystores/truststores):

~~~yaml
server:
  port: 8443
  ssl:
    enabled: true
    key-store: classpath:server.p12
    key-store-type: PKCS12
    key-store-password: <secure-secret-from-secret-manager>
    trust-store: classpath:trusted-clients.p12
    trust-store-type: PKCS12
    trust-store-password: <secure-secret-from-secret-manager>
    client-auth: need
~~~

This is a **template** and cannot run verbatim without real PKCS12 files and secrets. Never commit keystore private keys or passwords to a repository; use a secret manager or properly governed SSL bundles.

- `client-auth: need` requires a client certificate during the handshake.
- `client-auth: want` requests one if the client can send it, allowing certless connections through; never use `want` as a substitute for mandatory assurance.
- `trust-store` controls which CAs/certificates the server accepts when verifying clients.
- The TLS server certificate is verified by the client for matching hostname and trust chain.
- Only after a valid handshake does Spring Security X.509 map the principal on the request.

### 7.2. Reactive X.509 Principal Lookup

Example demo account with CN `report-client`:

~~~java
@Bean
ReactiveUserDetailsService users() {
    UserDetails serviceClient = User.withUsername("report-client")
            .password("{noop}unused-for-x509")
            .roles("REPORT_READER")
            .build();
    return new MapReactiveUserDetailsService(serviceClient);
}
~~~

This snippet supplements the direct flow, not a production configuration. The `noop` password exists only to build `UserDetails` in the example; real apps must not enable Basic/password authentication with this credential. Production X.509 identity mapping must rely on vetted CA/SAN/trust-domain policies, not just a nice-looking CN.

To protect an API:

~~~java
.x509(Customizer.withDefaults())
.authorizeExchange(ex -> ex
        .pathMatchers("/api/report/**").hasRole("REPORT_READER")
        .anyExchange().denyAll())
~~~

If a certificate passes TLS validation yet its CN does not map to a valid account, authentication still fails. If an account holds the role yet does not own the specific document, domain authorization must deny access.

### 7.3. Why Not Enable .x509 on a Backend Behind a TLS-Terminating Proxy?

If the proxy terminates client mTLS C and opens a **new TLS connection using certificate P** to the backend, the backend sees only certificate P in its TLS peer info. Enabling `x509` will authenticate **P** (if trusted and mapped), not "recover" certificate C from a header.

If the proxy uses plain HTTP to the backend, `x509` sees no peer certificate at all. Merely having the gateway write `X-Forwarded-Client-Cert` **does not populate** Reactor Netty's TLS peer certificate source.

## 8. What Does "Application-Verified" Mean?

In a Spring Security app, treat an identity as an **authenticated principal** only when:
1. The credential/assertion arrives over a protected channel with explicit **trust rules**.
2. The right verifier succeeded (TLS client cert at the app, JWT signature/claims, or a strong backend pre-auth trust policy).
3. The identity maps to a known, permitted application principal.
4. `Authentication` is placed into the request's security context via Reactive mechanisms, never by editing an HTTP header yourself.
5. Controllers/services enforce authorization on the principal and data.

Valid sources include:
- `ServerHttpSecurity.x509` when the app **directly** receives the TLS client certificate.
- `oauth2ResourceServer(jwt)` when the app receives a **gateway-signed short-lived JWT assertion** or real OAuth access token and verifies it itself.
- A custom `ReactiveAuthenticationManager`/pre-authentication filter if you must consume a trusted proxy header—requiring network/mTLS/header sanitization, strict parsing, issuer binding, anti-replay controls, and explicit permissions; this is more complex and error-prone than a signed JWT.

**Never construct `UsernamePasswordAuthenticationToken.authenticated("admin", null, ROLE_ADMIN)` simply because a header says `admin`.** That bypasses trust checks and invites privilege escalation.

### 8.1. Identity Proof Differs from Authorization Proof

A gateway proving certificate C belongs to workload `report-client` does not mean `finance.approve` scope was granted. The backend still needs roles/authorities mapped from trusted entitlements and object-level tenant checks.

If the gateway signs a JWT with `scope=profile.read`, that scope must originate from a **governed permission decision**, never copied from a client-supplied header or parameter.

## 9. Choosing a Verification Approach: Direct TLS, Signed Assertion, or Proxy Header?

| Approach | What Proof Does the App Receive? | Minimum Requirements | Trade-Offs |
| --- | --- | --- | --- |
| Direct app mTLS + X.509 | Peer certificate from Netty TLS session | Server truststore, `client-auth` NEED, principal mapping | App manages PKI/cert trust |
| Proxy mTLS + hop-2 mTLS, no assertion | Proxy's identity on hop 2 | Trust proxy cert, ACLs | Backend does not know C from hop 1 |
| Proxy mTLS + raw XFCC header | An HTTP string describing C | Proxy strip/set, no bypass, hop 2 protected, mapping | Easily spoofed if any trust rule breaks |
| Proxy mTLS + proxy-signed JWT assertion | App verifies assertion signature/`iss`/`aud`/`exp`/`sub` | Gateway signs post-mTLS, trusted JWKS, network isolation | Adds issuance/key rotation/replay policy |
| Client sends OAuth access token directly through proxy | App verifies access token itself | Trusted issuer/JWKS, `aud`, `scope` | Access token not bound to mTLS cert without token binding |
| DPoP/mTLS-bound access token | App/API or verifier adds proof-of-possession | Protocol support, `cnf` binding, request verification | More complex than plain Bearer |

Architectural recommendations:
- If the app terminates TLS: use **direct X.509** and sound principal mapping.
- If the edge terminates mTLS: let the **gateway verify the client certificate** and forward identity through a trusted contract (typically a **signed short-lived assertion** or purpose-built identity service/gateway model); the app verifies the assertion and authorizes.
- For OAuth2 APIs with proper access tokens: the app can verify the access token; if binding to mTLS is desired, enforce `cnf` binding and proof verification per RFC 8705 or equivalent rather than checking the two independently.

## 10. Designing Gateway-Signed Assertions: Do Not Turn the Proxy into an Unbounded "Name Stamper"

A gateway may attach an assertion only after it has:
1. Completed TLS client certificate validation and policy checks (CA, SAN, trust domain, EKU, revocation where applicable).
2. Mapped certificate identity C to an **authorized principal**.
3. Determined backend permissions **from a trusted source**, never from HTTP request headers.
4. Signed a JWT using a key controlled by the gateway/issuer.
5. Scoped the JWT to the backend via `aud`, short lifetime, fixed issuer, and optional `jti`.
6. Forwarded only to the intended backend over a trust-protected channel.
7. Blocked all direct/untrusted ingress and **stripped any client-sent headers sharing the assertion header name**.

Example JWT assertion payload (JSON illustration only, not a signed token):

~~~json
{
  "iss": "https://gateway.example.test/assertions",
  "aud": ["internal-profile-api"],
  "sub": "spiffe://corp.example/ns/finance/sa/report-reader",
  "iat": 1790000000,
  "nbf": 1790000000,
  "exp": 1790000060,
  "jti": "one-time-or-unique-id",
  "scope": "profile.read",
  "authn_method": "client_certificate",
  "cert_sha256": "thumbprint-metadata-if-policy-requires"
}
~~~

**Trust any of these claims only after the application verifies the JWT.** Payloads are Base64URL-encoded, not encrypted; never put private-key material or unnecessary sensitive data inside a JWT. A ~60-second lifetime is a design example, **not** a universal default.

### 10.1. Why Are aud and issuer Mandatory?

- `iss` ensures the app accepts assertions only from an authorized gateway/identity issuer.
- `aud` ensures the token was minted for **this specific backend**, preventing replay of service A's assertion against service B.
- `exp`/`nbf` bound lifetime, allowing minimal clock skew.
- `scope`/entitlements carry only approved permissions.
- `sub` represents user/workload identity, not a role.

A validly signed JWT with an unknown issuer, wrong audience, or expired timestamp must be rejected. Never disable audience validation to "fix a 401".

### 10.2. Signed Assertions Do Not Automatically Replace Hop-2 mTLS

If the backend accepts a valid gateway-signed token from any caller, it remains a **replayable Bearer token** during its lifetime. Protect hop 2, keep lifetimes short, enforce `jti`/anti-replay stores when needed, and combine with mTLS/DPoP/token binding or request-bound signatures if your threat model demands it.

Signed assertions + hop-2 mTLS are **complementary**: one proves **asserted end-client identity**, while the other proves **transport peer gateway**.

### 10.3. Certificate-to-sub Mapping Needs an Explicit Policy

Never blindly use `CN` as a unique username across every issuer. Map using:
- Trusted CA/trust domain.
- SAN URI or DNS name in a governed namespace.
- Certificate policy/EKU.
- Revocation/account status.
- Explicit allowlist/entitlement mapping.

If a gateway accepts a valid mTLS certificate from client X yet lets the client choose `sub=admin` in a header and signs it with its valid gateway key, the backend cannot detect the upstream mistake. **Signing proves the gateway issued the assertion**, not that every upstream mapping decision was right. Security reviews must therefore inspect **both the gateway's mapping code and its signing privileges**.

## 11. Runnable Java 17+ Project: WebFlux Trusts Only Signed JWT Assertions

The project below demonstrates **Option B**: the backend rejects `X-Authenticated-User` or `X-Forwarded-Client-Cert` headers carried on HTTP requests. Instead, it authenticates identity from a **JWT signed by a test-simulated gateway** using a real `ReactiveJwtDecoder`.

Important:
- **No real proxy/mTLS exists in this project.** Tests generate an in-memory RSA keypair acting as the gateway issuer and sign tokens; app security genuinely verifies the RSA signature and claims.
- The issuer/JWKS URLs in `application.yml` are mock hostnames. The app boots and public routes respond; authenticating requests outside tests requires a real gateway/issuer with live JWKS.
- These tests cannot prove that TLS handshakes, SAN policies, certificate revocation, or Envoy header sanitization are configured correctly; those require separate E2E tests.
- The demo API simply accepts the Bearer assertion from HTTP. In production, the **gateway** sets/overwrites the token header after mTLS, and the backend is never exposed directly.
- If your organization uses user OAuth 2.0 access tokens instead of gateway assertions, Resource Server works similarly, though trusted issuers, claim semantics, and certificate binding may differ.

### 11.1. Directory Structure

~~~text
webflux-gateway-identity/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── DemoApplication.java
    │   │   ├── SecurityConfig.java
    │   │   └── IdentityController.java
    │   └── resources/
    │       └── application.yml
    └── test/java/demo/
        └── GatewayAssertionHttpTest.java
~~~

### 11.2. settings.gradle

~~~groovy
rootProject.name = 'webflux-gateway-identity'
~~~

### 11.3. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.7'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Uses the **Resource Server** starter because the app consumes signed JWTs. It does not mint JWTs, perform OAuth2 Login, or verify caller certificates directly on the client→proxy hop.

### 11.4. application.yml

`src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

spring:
  application:
    name: webflux-gateway-identity
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://gateway.example.test/assertions
          jwk-set-uri: https://gateway.example.test/assertions/jwks
          audiences:
            - internal-profile-api
~~~

- `issuer-uri`: fixes the trusted assertion source.
- `jwk-set-uri`: endpoint for fetching public keys to verify gateway/identity issuer signatures.
- `audiences`: binds assertions to `internal-profile-api`.

**These are not live endpoints.** Tests swap the decoder via `TestConfiguration`, avoiding network JWKS dependencies. Production applications must reach a real issuer/JWKS over HTTPS, support key rotation, and validate additional claims/token profiles as needed.

### 11.5. DemoApplication.java

`src/main/java/demo/DemoApplication.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 11.6. SecurityConfig.java

`src/main/java/demo/SecurityConfig.java`:

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                // No cookie login in this Bearer-only demo.
                .securityContextRepository(
                        NoOpServerSecurityContextRepository.getInstance())
                .csrf(ServerHttpSecurity.CsrfSpec::disable)
                .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .authorizeExchange(ex -> ex
                        .pathMatchers(HttpMethod.GET, "/public/ping")
                                .permitAll()
                        .pathMatchers(HttpMethod.GET, "/api/identity")
                                .authenticated()
                        .pathMatchers(HttpMethod.GET, "/api/private")
                                .hasAuthority("SCOPE_profile.read")
                        .anyExchange().denyAll())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults()))
                .build();
    }
}
~~~

Analysis:
- No `headers("X-Authenticated-User")`, and never reads `X-Forwarded-Client-Cert` to construct a principal.
- Every protected API request requires a JWT verified by `ReactiveJwtDecoder`.
- `JwtAuthenticationToken` puts the principal and authorities into the Reactive security context.
- `SCOPE_profile.read` comes from the `scope=profile.read` claim of the **verified** JWT.
- `anyExchange().denyAll()` blocks undeclared routes and methods.
- CSRF is disabled **solely because this Bearer-only demo has no ambient browser cookie credentials**; if your app uses login sessions, cookies, or Basic, design CSRF accordingly.
- `NoOpServerSecurityContextRepository` avoids persisting authentication across requests, though it does not guarantee every `WebSession` mechanism is disabled.
- Production still requires restricting network paths, backend mTLS, and signed assertion TTL/anti-replay policies; this code does not check proxy IP addresses itself.

### 11.7. IdentityController.java

`src/main/java/demo/IdentityController.java`:

~~~java
package demo;

import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class IdentityController {

    @GetMapping("/public/ping")
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping("/api/identity")
    public Mono<Map<String, Object>> identity(
            @AuthenticationPrincipal Jwt jwt) {

        return Mono.just(Map.of(
                "principal", jwt.getSubject(),
                "issuer", jwt.getIssuer().toString(),
                "audience", jwt.getAudience()));
    }

    @GetMapping("/api/private")
    public Mono<Map<String, String>> privateData(
            @AuthenticationPrincipal Jwt jwt) {

        return Mono.just(Map.of(
                "principal", jwt.getSubject(),
                "result", "AUTHORIZED"));
    }
}
~~~

The `principal` field comes from the **verified JWT**, not a spoofable HTTP header. The DTO intentionally omits `jwt.getTokenValue()` and full claims. In production, even subject/issuer can be sensitive; expose only the minimum needed and enforce object-level permissions on real data.

## 12. Real RSA Signature and JWT Claim Validation Tests via WebTestClient

The project uses an RSA keypair generated **in memory inside the test** as a simulated gateway signer. `NimbusReactiveJwtDecoder` with the test RSA public key genuinely verifies the signature and validates issuer, audience, and timestamps. This is stronger than `mockJwt()`, because it includes a negative case signed by an untrusted key.

**Yet it still does not simulate a client-to-proxy TLS handshake.** The mTLS portion must be tested separately with gateway/TLS/certificate fixtures.

### 12.1. GatewayAssertionHttpTest.java

`src/test/java/demo/GatewayAssertionHttpTest.java`:

~~~java
package demo;

import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.NoSuchAlgorithmException;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.time.Instant;
import java.util.Date;
import java.util.List;

import com.nimbusds.jose.JOSEException;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.JwtClaimValidator;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
@Import(GatewayAssertionHttpTest.TestKeys.class)
class GatewayAssertionHttpTest {

    private static final String ISSUER =
            "https://gateway.example.test/assertions";
    private static final String AUDIENCE =
            "internal-profile-api";
    private static final String SUBJECT =
            "spiffe://corp.example/ns/finance/sa/report-reader";

    private static final KeyPair SIGNER = keyPair();
    private static final KeyPair ATTACKER = keyPair();

    @TestConfiguration(proxyBeanMethods = false)
    static class TestKeys {
        @Bean
        @Primary
        ReactiveJwtDecoder localSignedAssertionDecoder() {
            NimbusReactiveJwtDecoder decoder =
                    NimbusReactiveJwtDecoder
                            .withPublicKey(
                                    (RSAPublicKey) SIGNER.getPublic())
                            .build();
            decoder.setJwtValidator(
                    new DelegatingOAuth2TokenValidator<>(
                            JwtValidators.createDefaultWithIssuer(ISSUER),
                            new JwtClaimValidator<List<String>>(
                                    "aud",
                                    aud -> aud != null
                                            && aud.contains(AUDIENCE))));
            return decoder;
        }
    }

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    private static KeyPair keyPair() {
        try {
            KeyPairGenerator generator =
                    KeyPairGenerator.getInstance("RSA");
            generator.initialize(2048);
            return generator.generateKeyPair();
        } catch (NoSuchAlgorithmException error) {
            throw new IllegalStateException(error);
        }
    }

    private static String signed(
            KeyPair key,
            String issuer,
            String audience,
            String scope,
            Instant expiresAt) throws JOSEException {

        Instant now = Instant.now();
        JWTClaimsSet claims = new JWTClaimsSet.Builder()
                .issuer(issuer)
                .subject(SUBJECT)
                .audience(audience)
                .issueTime(Date.from(now.minusSeconds(10)))
                .notBeforeTime(Date.from(now.minusSeconds(10)))
                .expirationTime(Date.from(expiresAt))
                .claim("scope", scope)
                .build();

        SignedJWT jwt = new SignedJWT(
                new JWSHeader.Builder(JWSAlgorithm.RS256)
                        .keyID("trusted-gateway-key")
                        .build(),
                claims);
        jwt.sign(new RSASSASigner(
                (RSAPrivateKey) key.getPrivate()));
        return jwt.serialize();
    }

    private String valid(String scope) throws JOSEException {
        return signed(SIGNER, ISSUER, AUDIENCE, scope,
                Instant.now().plusSeconds(120));
    }

    @Test
    void publicPingWithoutAuthenticationIs200() {
        client.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("pong");
    }

    @Test
    void anonymousWithSpoofedUserHeaderIsStill401() {
        client.get().uri("/api/identity")
                .header("X-Authenticated-User", "admin")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void forgedXfccWithoutJwtIsStill401() {
        client.get().uri("/api/identity")
                .header("X-Forwarded-Client-Cert",
                        "Subject=\"CN=admin\"")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void validSignedIdentityWinsOverSpoofedHeader()
            throws JOSEException {
        client.get().uri("/api/identity")
                .header("Authorization", "Bearer " + valid("profile.read"))
                .header("X-Authenticated-User", "admin")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.principal").isEqualTo(SUBJECT)
                .jsonPath("$.issuer").isEqualTo(ISSUER)
                .jsonPath("$.audience[0]").isEqualTo(AUDIENCE);
    }

    @Test
    void correctScopeCanAccessPrivateEndpoint()
            throws JOSEException {
        client.get().uri("/api/private")
                .headers(h -> h.setBearerAuth(valid("profile.read")))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.result").isEqualTo("AUTHORIZED");
    }

    @Test
    void missingScopeIs403EvenIfJwtIsValid()
            throws JOSEException {
        client.get().uri("/api/private")
                .headers(h -> h.setBearerAuth(valid("other.scope")))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void wrongIssuerIs401() throws JOSEException {
        String jwt = signed(SIGNER,
                "https://attacker.example.test", AUDIENCE,
                "profile.read", Instant.now().plusSeconds(120));
        client.get().uri("/api/identity")
                .headers(h -> h.setBearerAuth(jwt))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void wrongAudienceIs401() throws JOSEException {
        String jwt = signed(SIGNER,
                ISSUER, "another-backend",
                "profile.read", Instant.now().plusSeconds(120));
        client.get().uri("/api/identity")
                .headers(h -> h.setBearerAuth(jwt))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void expiredAssertionIs401() throws JOSEException {
        String jwt = signed(SIGNER,
                ISSUER, AUDIENCE,
                "profile.read", Instant.now().minusSeconds(3600));
        client.get().uri("/api/identity")
                .headers(h -> h.setBearerAuth(jwt))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void attackerSignedAssertionIs401() throws JOSEException {
        String jwt = signed(ATTACKER,
                ISSUER, AUDIENCE,
                "profile.read", Instant.now().plusSeconds(120));
        client.get().uri("/api/identity")
                .headers(h -> h.setBearerAuth(jwt))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void missingBearerTokenIs401() {
        client.get().uri("/api/identity")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void malformedBearerTokenIs401() {
        client.get().uri("/api/identity")
                .headers(h -> h.setBearerAuth("not-a-signed-jwt"))
                .exchange()
                .expectStatus().isUnauthorized();
    }
}
~~~

### 12.2. Why Is This Test Meaningful?

- `anonymousWithSpoofedUserHeaderIsStill401` proves **HTTP headers do not create authentication** on the backend.
- `forgedXfccWithoutJwtIsStill401` proves self-asserted XFCC is rejected by the backend.
- `validSignedIdentityWinsOverSpoofedHeader` uses an assertion **signed with the test private key whose public key the decoder trusts**; the principal comes from the JWT, not from `admin` in the header.
- Wrong issuer/audience tests prove **a valid signature alone is not enough**.
- Wrong signature test proves **plausible-looking claims alone are not enough**.
- Expired token test proves time bounds are enforced.
- Valid signature with wrong scope returns 403: identity verification differs from authorization.
- Remaining tests verify missing/malformed tokens and the public route.

**Total: 12 test methods** in the file, expected to PASS with the right dependencies/API versions. This is **code designed for learners to compile and run**, not a transcript of an executed Gradle run.

### 12.3. Real JWT Verification Without Real mTLS Testing

`NimbusReactiveJwtDecoder.withPublicKey(...)` in `TestConfiguration` verifies JWS with an RSA public key. `@Import(TestKeys.class)` supplies this decoder to Spring Security in the test context; Spring Boot's placeholder URL decoder is not used during these tests.

However, the tests **do not prove**:
- That the proxy requires a client certificate at the TLS handshake.
- That cert chain/issuer/KeyUsage/EKU/SAN are verified.
- That `SANITIZE_SET` ran in the gateway.
- That the backend cannot be reached directly from an untrusted network.
- That the proxy certificate is verified by the backend on hop 2.
- That assertions are issued by the gateway only after mTLS succeeds.
- That certificate revocation works.
- That anti-replay token binding is deployed.

Separate TLS/Envoy/Kubernetes integration tests are required for those conditions; never claim `WebTestClient` mocks suffice.

## 13. Running the Application and Observing HTTP

In the directory containing `build.gradle`:

~~~bash
gradle test
gradle bootRun
~~~

If a Gradle Wrapper exists, use `./gradlew test` or `gradlew.bat test` per OS. Expect **12 `@Test` methods**; actual Gradle output depends on configuration and environment, so no fake stdout is fabricated as if executed.

The app at `http://localhost:8080` only demonstrates the security layer. Because `application.yml` uses placeholder issuer/JWKS URLs, there is no real gateway assertion to verify during a plain `bootRun`; to test the happy path, run the local RSA tests or replace the config with a real issuer/gateway in staging.

### 13.1. Public Ping

~~~bash
curl -i http://localhost:8080/public/ping
~~~

Expect **200 OK**, body:

~~~text
pong
~~~

### 13.2. Forged Header Grants No Access

~~~bash
curl -i http://localhost:8080/api/identity \
  -H 'X-Authenticated-User: admin'
~~~

Expect **401 Unauthorized**. This shows the app **does not trust raw headers** as identity. Missing JWT also returns 401 even if the client attaches a hand-crafted XFCC header.

### 13.3. Only a Valid Token from the Gateway/Issuer Is Trusted

~~~bash
curl -i https://api-staging.example.test/api/identity \
  -H 'Authorization: Bearer <gateway-signed-assertion>'
~~~

This is a template only, with no real token. Once the proxy→app trust model and real issuer are deployed, the backend verifies JWT signature/`iss`/`aud`/`exp`. Valid token → 200, invalid token → 401.

**Never place raw production JWTs/tokens into shared shell history, logs, screenshots, or tickets.** A JWT assertion is a Bearer credential and can be replayed within its lifetime if stolen; test only with test data.

### 13.4. Why Doesn't curl Prove an mTLS Handshake?

`curl -H 'X-Forwarded-Client-Cert: ...'` sends only a text header, not a TLS certificate. To test mTLS at the proxy, present a valid client cert and private key:

~~~bash
# Illustrative command, only when organization-issued cert/key exist.
curl --cert client.pem --key client.key \
  --cacert trusted-gateway-ca.pem \
  https://gateway-staging.example.test/api/identity
~~~

No real cert/key files exist in this lesson. The proxy must verify the client certificate in TLS, map identity, and mint the assertion. If a client key passphrase is required, handle secrets securely; never commit `client.pem`/`client.key` or place them in shared environments.

## 14. Comparing HTTP 401/403 Errors with TLS Handshake Failures

| Scenario | Rejecting Party | Typical Outcome |
| --- | --- | --- |
| No client cert sent when proxy requires mTLS NEED | TLS terminator | TLS handshake fails; **may have no HTTP status** |
| Client cert has untrusted CA or is expired | TLS terminator | TLS handshake/certificate validation failure |
| Valid client cert, mapping unauthorized at gateway | Gateway auth policy | Typically 403 or gateway-specific failure |
| Hop-1 mTLS valid, app receives no signed assertion | Spring Security backend | 401 |
| Attacker sends forged `X-Authenticated-User`/XFCC, no JWT | Spring Security backend | 401 |
| Signed JWT assertion has wrong issuer/audience/expiry/signature | Spring Security backend | 401 |
| Valid JWT, missing `SCOPE_profile.read` | `AuthorizationWebFilter`/backend | 403 |
| Valid JWT scope, tenant/object not owned by principal | Domain authorization | 403/404 per policy |
| Backend sees only proxy P via hop-2 TLS | Network/TLS/app | TLS peer identity is P; no end-client C |
| Valid JWT yet backend bypassed from Internet | Misconfigured infra | JWT still enforces auth, yet replay/bypass risks remain |
| Revoked certificate not checked by gateway policy | Misconfigured gateway/PKI | App sees only the assertion gateway minted; fix gateway |

**A TLS handshake failure is not a 401.** If the client cannot establish a TLS connection, the HTTP handler never receives a request to return 401/403.

## 15. Raw-Header Proxy Pre-Auth Pattern: Only When the Trust Boundary Is Proven

Some organizations have existing infrastructure where the edge authenticates mTLS, only internal traffic reaches the backend, the gateway always overwrites `X-Authenticated-User`, and the app uses a custom filter to build the principal. This **pre-authentication pattern** is not inherently wrong if rigorously engineered, yet many safety assumptions live outside Java code.

Before using it:
1. Gateway enforces client mTLS on all sensitive routes.
2. Strip all client-sent identity headers and overwrite headers from cert validation results.
3. Backend is reachable only from gateway workloads, with zero debug/direct ingress.
4. Proxy→backend hop is protected, verifying peer proxy identity where appropriate.
5. Header formats, encoding, commas, duplicates, and multi-hop forwarding are explicitly defined.
6. App builds `Authentication` only when requests definitively come from the trusted gateway, never trusting client-supplied `X-Forwarded-For`.
7. Identity maps to accounts/tenants/roles from a trusted source; never auto-grant `ADMIN` from headers.
8. Address header replay if attackers on the same network can capture requests.
9. Run bypass/negative tests from different networks/zones.
10. Require security reviews for all ingress/gateway config changes, as they can break app assumptions.

**There is no boolean `trust-all-proxy-headers=true` that replaces all the requirements above.** Operationally, a signed JWT assertion verified at the app usually yields a clearer, more testable trust boundary.

### 15.1. Why Checking Proxy IP Alone Is Insufficient

Source IPs change due to NAT/load balancers, IP reuse, proxy chaining, pods, and cloud networking. `X-Forwarded-For` can originate from clients unless sanitized by proxies. Relying solely on CIDRs without TLS peer validation gives weak assurance that a request truly came from your trusted gateway.

IP allowlists and network policies should serve as an **additional defense layer**, never as the sole basis for granting `ROLE_ADMIN`.

## 16. Authenticated Client Certificate Does Not Automatically Bind a Bearer Access Token

Sometimes a gateway sees certificate C while forwarding `Authorization: Bearer TOKEN`. If the backend verifies the JWT independently, the app knows the token is valid—but **does not automatically know the token's presenter is the holder of certificate C**.

If you need OAuth2 mTLS sender-constrained access tokens per RFC 8705:
- The Authorization Server mints a token bound to the certificate, typically via a `cnf` thumbprint such as `x5t#S256`.
- The Resource Server or trusted enforcement point must verify that the certificate actually presented by the caller matches that confirmation claim.
- With TLS termination at a proxy, you need a protocol conveying the **verified cert identity** to a trusted backend or performing confirmation at the gateway.
- Never merely compare `X-Forwarded-Client-Cert` with the token claim if XFCC can be forged.

Similarly for DPoP (RFC 9449), require a DPoP proof JWT bound to request method/URI plus anti-replay checks per spec; never read `cnf` alone and assume replay protection.

**mTLS at the proxy, OAuth access tokens, and gateway-signed assertions are three distinct pieces of evidence.** Your architecture must state explicitly which carries authoritative identity and which adds assurance.

## 17. Threat Modeling Attack Scenarios

### 17.1. Scenario 1: Header Spoofing

An attacker sends:

~~~http
GET /api/private HTTP/1.1
X-Authenticated-User: ceo
X-Forwarded-Client-Cert: Subject="CN=ceo"
~~~

If the backend allows direct access and builds `Authentication` from headers, the attacker impersonates the CEO. Defenses: network isolation, proxy header sanitization, app-verified signed assertions, negative tests. In our project, this request without a JWT still returns 401.

### 17.2. Scenario 2: "mTLS to Proxy, but Backend Mistakes Proxy for User"

Proxy P connects to the backend with cert `CN=gateway`. Backend `.x509` extracts `CN=gateway` and a flawed mapping grants `ADMIN`. Any caller forwarded by the proxy could inherit the gateway's role. Defenses: never map gateway transport identity to user privileges; use client C's identity assertion and separate authorization.

### 17.3. Scenario 3: Trusted Proxy Signs the Wrong Subject

The gateway verifies `report-reader`'s certificate, yet lets the client pass `sub=admin` in a header and signs it with the valid gateway key. The backend's crypto check passes, yet it receives the wrong identity. Defenses: the gateway **must derive `sub` from verified cert identity/entitlements**, never untrusted client claims. Signatures do not prove mapping correctness, so security reviews must cover **both the gateway's mapping code and signing keys**.

### 17.4. Scenario 4: Assertion Replay

An attacker captures a valid signed gateway assertion and replays it within 30–60 seconds. If the backend is Bearer-only with a bypass path, the request can succeed. Defenses: hop-2 mTLS/network isolation, short TTLs, one-time `jti`/replay stores where needed, sender-constrained tokens, or request-bound signatures.

### 17.5. Scenario 5: Spoofing Upstream Metadata

An attacker sets `X-Forwarded-Proto=https` and `X-Forwarded-For=127.0.0.1` to bypass HTTP scheme or IP checks. Defenses: trust forwarded headers only from authenticated proxies, strip inbound headers, and never treat forwarded metadata as authentication.

### 17.6. Scenario 6: Overly Broad Certificate CA

The gateway trusts a CA that issues certs for many unrelated workloads. A client with a valid cert whose SAN lies outside the allowed namespace can still pass certificate chain verification. Defenses: authorize by SAN/trust domain/role; never equate "trust CA = trust every identity".

### 17.7. Scenario 7: Hidden permitAll Route in the App

Authentication on `/api/private` is solid, yet an auxiliary route `/internal/health/config` is `permitAll` and leaks data. Defenses: `anyExchange().denyAll()`, method-level security, route inventories, ingress policies, and negative testing.

### 17.8. Scenario 8: Multiple Proxy Hops and Chain Confusion

Client→Edge A→Mesh B→Backend. One hop uses `APPEND_FORWARD` while another uses `FORWARD_ONLY`, leaving XFCC with multiple elements mixing verified and caller-supplied values. Defenses: identify the authoritative hop, configure sanitizers properly, use end-to-end signed assertions, and never arbitrarily parse "first or last element".

## 18. Real Integration Testing with Proxy/mTLS

Java WebFlux tests verify JWT cryptography and HTTP authorization, whereas production needs E2E tests for:

| Test | Required Result |
| --- | --- |
| Client without cert → gateway mTLS-required route | TLS handshake rejected |
| Expired client cert or wrong CA | Proxy rejects per policy |
| Valid client cert with non-allowlisted SAN | No identity/route access granted |
| Revoked client cert | Rejected per approved revocation/short-lived cert policy |
| Client authenticated via proxy, app receives signed assertion | Backend receives only the mapped `sub` |
| Client spoofs `X-Authenticated-User: admin` | Proxy strips; app never sees `admin` |
| Client spoofs `X-Forwarded-Client-Cert` | Proxy sanitizes; verified cert not overwritten |
| Call backend directly bypassing proxy | Rejected by network policy/mTLS |
| Call through a secondary ingress | Cannot bypass the same security controls |
| Replace gateway signed assertion with attacker-signed token | Backend 401 |
| Wrong issuer/audience/expiry token | Backend 401 |
| Valid token lacking role/scope | Backend 403 |
| Valid route scope for different tenant/object | Domain denial |
| Proxy→backend cert is not a trusted gateway | TLS peer validation failure |
| Gateway signing key rotation | Assertions never signed with keys untrusted by verifier |
| Stolen signed assertion replayed elsewhere | Rejected/mitigated per replay policy |
| WebSocket/gRPC/HTTP2 paths | Trust boundaries and auth policies intact |
| Multi-region failover | Consistent header/identity policies across all edges |

**Never use real data or real secrets** in tests; generate isolated test CAs, test certs, test accounts, and signed tokens.

### 18.1. Negative Tests from Inside the Same Pod/Internal Network

Do not test only from the Internet. An attacker could be a compromised cluster pod, a container with network access, or an overly privileged service account. Test:
- Bypass attempts from unauthorized internal namespaces.
- Sending identity headers straight to the pod IP.
- Hitting debug or alternate ports.
- Hitting service ports unprotected by ingress policies.
- Whether a peer workload lacking the right SAN/identity can open the mTLS hop.

The goal is confirming **the backend never treats network proximity as a role**.

## 19. Troubleshooting: mTLS Reports Success Yet Backend Returns 401/403

### Backend Returns 401 Despite Proxy Verifying mTLS

- Did the proxy actually mint a signed assertion?
- Is the assertion in the expected header name and forwarded along that route?
- Is the backend using `oauth2ResourceServer(jwt)` or mistakenly expecting direct TLS `.x509`?
- Does the token have valid signature, issuer, audience, and expiry?
- Did the gateway rotate signing keys before the backend refreshed JWKS?
- Is there significant clock skew between proxy and backend?
- Did the request hit the intended security chain?
- Did traffic route through a secondary gateway lacking assertion configuration?

Never "fix" a 401 by accepting `X-Authenticated-User` directly as the principal.

### Backend Returns 403 After a Valid Assertion

- Is `SCOPE_profile.read` or the required role present?
- Does `JwtGrantedAuthoritiesConverter` map the `scope` claim in the right format?
- How does `hasAuthority` differ from `hasRole`?
- Is the account/tenant mapping still valid?
- Did the service check object ownership and deny access?
- Is CSRF blocking from another cookie-based route/chain?
- Did the gateway copy a scope from a client header? If so, **fix the gateway**, never remove authorization.

### Backend Sees Only CN=proxy

If the backend terminates mTLS on the **proxy→backend hop**, seeing the proxy's peer certificate is expected. That is not a Spring Security bug. To identify client C, use a verified upstream identity assertion or configure TLS passthrough/direct mTLS appropriately.

### XFCC Sent Yet WebFlux x509 Principal Is Null

`ServerHttpSecurity.x509` inspects TLS peer info on the connection the app itself terminates. XFCC is an HTTP header string; it **does not turn into** `SslInfo.getPeerCertificates()`. Never build a request wrapper faking SSL info from XFCC without trust checks.

### Valid Assertion Yet Wrong Subject

- Verify cert SAN→principal mapping at the gateway.
- Check whether the gateway trusted a client-supplied claims header.
- Check multi-hop proxies and header sanitization.
- Check tenant/workload delegation policies.
- Verify the raw certificate subject was validated without treating a CN suffix as a role.
- Inspect signer identity, audit trails, and key rotation.

## 20. Secure Deployment Checklist

### TLS and Proxy
- [ ] Proxy requires client mTLS on mandatory routes.
- [ ] CA/trust domain, SAN, EKU, expiry, and revocation policies are clearly defined.
- [ ] TLS terminator knows client certificate C; backend knows which hop actually carries client certs.
- [ ] Proxy→backend enforces network isolation, TLS/mTLS, and authenticated proxy peers as appropriate.
- [ ] No direct backend routes, alternate ingresses, or port bypasses exist.
- [ ] `XFCC`/`X-Authenticated-User` and all client-supplied identity headers are sanitized/overwritten.
- [ ] Never use `FORWARD_ONLY`/`ALWAYS_FORWARD_ONLY` to construct trusted principals.
- [ ] `Forwarded`/`X-Forwarded-*` trusted only via trusted proxies for intended purposes.
- [ ] Audits track changes to gateway routes, Envoy/Istio filters, and network policies.

### Identity and Signed Assertions
- [ ] Gateway signs assertions only after successful certificate validation and mapping.
- [ ] `sub` derives from trusted certificate identity/account mapping.
- [ ] `iss` is fixed and `aud` binds strictly to the target backend.
- [ ] Verify JWS signature, allowed algorithms, and `exp`/`nbf`/`iat`/`jti` per policy.
- [ ] Signing private keys remain on the issuer; backends hold only public verification keys.
- [ ] Short assertion TTLs, anti-replay, and sender binding evaluated per threat model.
- [ ] Header and token values never logged at edge or backend.
- [ ] Gateway never grants scopes by copying client-sent parameters.
- [ ] Principals map to roles/tenants/entitlements from trusted sources.
- [ ] App enforces ownership in services, not just HTTP routes.
- [ ] Tokens from wrong issuers/audiences or unsigned/malformed tokens are rejected.

### Spring Security Reactive
- [ ] `ServerHttpSecurity`, `SecurityWebFilterChain`, and `ReactiveJwtDecoder` match the reactive stack.
- [ ] `.x509` used only when the backend directly receives TLS client certs or matching peer identities.
- [ ] When a proxy terminates mTLS, the backend **never** treats XFCC as the TLS peer.
- [ ] `JwtAuthenticationToken` is produced from a verified JWT, never raw headers.
- [ ] Never use Servlet `HttpSecurity` or store `Authentication` in `ThreadLocal`.
- [ ] Never call `block()` inside Reactive auth filters.
- [ ] Bearer-only CSRF policy separated from cookie/browser flows.
- [ ] HTTP 401 vs 403 semantics preserved; TLS handshake failures kept distinct from HTTP auth failures.

### Testing and Operations
- [ ] Tests prove spoofed user/XFCC headers create no authentication.
- [ ] Tests verify real signed tokens: valid/invalid issuer, audience, expiry, signature.
- [ ] Negative tests cover scopes/roles and object/tenant access.
- [ ] Tests cover direct backend bypass and alternate ingresses.
- [ ] Tests cover client cert trust, SANs, expiry, and revocation.
- [ ] Tests cover proxy signing-key rotation and TLS cert rotation.
- [ ] Multi-region/multi-proxy behavior tested.
- [ ] Incident response plan ready for private key/gateway compromise.
- [ ] Metrics track authentication failures, signer versions, and gateway decisions without leaking tokens.
- [ ] Never treat `mockJwt()` as proof of real certificate validation.

## 21. Self-Check Questions

**1. Once the gateway authenticates a client via mTLS, does WebFlux automatically know the client SAN?**

> No. If TLS terminates at the gateway, the backend sees a new connection from the gateway; you need an identity forwarded under a trust contract, TLS passthrough, or direct verification.

**2. When the backend uses mTLS with the proxy, whose peer cert does it see?**

> Usually the proxy's own certificate on the proxy→backend hop, not the client's certificate from the prior hop.

**3. Is `X-Forwarded-Client-Cert` TLS proof?**

> No. It is an HTTP header asserted by an upstream; it requires trusted proxy sanitization and an explicit identity contract.

**4. Does `SANITIZE_SET` complete authentication inside the application?**

> No. It cleans and sets XFCC at the proxy under proper conditions, yet the app still needs a trusted channel, principal mapping, and authorization.

**5. Is passing `X-Authenticated-User: admin` in `curl` enough to log in?**

> It must never be enough. The app must reject requests lacking credentials or assertions it verifies itself.

**6. When does `ServerHttpSecurity.x509` make sense?**

> When Spring WebFlux directly terminates client mTLS, receives real peer certificates, and has an appropriate principal mapping.

**7. Why not grant `ROLE_ADMIN` to every cert from the internal CA?**

> One CA can issue certs for many identities; certificate trust is distinct from role entitlement.

**8. Which claims should a signed gateway assertion include?**

> At minimum `issuer`/`audience`/`subject`/timestamps per protocol, and permissions per business policy; add `jti`/replay/certificate binding as needed.

**9. Is a valid JWT signature enough to enter `/api/private`?**

> No. Issuer, audience, expiration, scope, tenant/ownership, and other validators also apply.

**10. Do `mockJwt()` tests prove RSA signatures or mTLS handshakes?**

> No. `mockJwt()` bypasses the JWT decoder; TLS handshakes require separate TLS integration tests.

**11. If the gateway signs a wrong `sub` copied from a client header, can the backend detect it?**

> The backend can verify the signer, but cannot inherently know the upstream mapping was wrong. Fix mapping/sanitization at the gateway with audits and negative tests.

**12. Does mTLS prevent replay of a stolen gateway JWT assertion?**

> Not automatically. Hop-2 mTLS restricts the presenter, yet Bearer assertions still need short lifetimes, binding, and anti-replay per threat model.

**13. How do TLS `clientAuth=want` and `need` differ?**

> `want` permits connections without a client cert per server policy; `need` mandates a client cert during the handshake.

**14. Why not use `X-Forwarded-For` to identify the authenticated user?**

> It is routing/IP metadata and is spoofable when untrusted; it is not identity authentication.

**15. Is a TLS handshake failure a 401?**

> Typically no. An HTTP response may not even exist because the handshake fails before any request reaches WebFlux.

**16. What more does an mTLS-bound access token require?**

> Confirmation claim/binding and proof-of-possession validation per RFC 8705; merely having an access token and a cert on two separate layers does not bind them together.

## 22. Summary: Never Confuse Transport Trust with Application Identity

**mTLS at the proxy** proves the client's certificate identity to the **proxy** on that TLS hop. **mTLS between the proxy and WebFlux** proves the transport peer of the second hop—usually the proxy. **Application-verified identity** exists only after the app receives and verifies trusted proof, maps it to a principal, and enforces authorization.

Two clear design paths:
- **Direct mTLS at WebFlux:** configure Reactor Netty `client-auth`/truststore + Spring Security Reactive `.x509(...)` + principal lookup + domain permissions.
- **mTLS at the proxy:** the proxy verifies certs and maps identities, sanitizes untrusted headers, and emits a short-lived signed assertion or controlled trust mechanism; the backend verifies signature, issuer, audience, timestamps, and scopes while protecting the proxy→backend hop and blocking bypasses.

**Never treat self-asserted `XFCC`/`X-Authenticated-User` headers as equivalent to a TLS handshake.** Even when headers are properly set by a proxy, the application must enforce trust boundaries and authorize specific resources.

### Official References

- Spring Security — Reactive X.509 Authentication: https://docs.spring.io/spring-security/reference/6.5/reactive/authentication/x509.html
- Spring Security — ServerHttpSecurity Reactive API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html
- Spring Security — Reactive OAuth2 Resource Server JWT: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html
- Spring Security — Testing Reactive JWT Authentication: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/oauth2.html
- Spring Boot — Common Application Properties (`server.ssl.client-auth`): https://docs.spring.io/spring-boot/3.5/appendix/application-properties/
- Spring Security — Proxy headers and request trust: https://docs.spring.io/spring-security/reference/features/exploits/http.html
- Envoy — X-Forwarded-Client-Cert header semantics: https://www.envoyproxy.io/docs/envoy/latest/configuration/http/http_conn_man/headers.html
- Envoy — HttpConnectionManager `forward_client_cert_details`/`SANITIZE_SET`: https://www.envoyproxy.io/docs/envoy/latest/api-v3/extensions/filters/network/http_connection_manager/v3/http_connection_manager.proto
- Istio — XFCC and network topology: https://istio.io/latest/docs/ops/configuration/traffic-management/network-topologies/
- RFC 5280 — Internet X.509 Public Key Infrastructure Certificate and CRL Profile: https://www.rfc-editor.org/rfc/rfc5280
- RFC 7519 — JSON Web Token: https://www.rfc-editor.org/rfc/rfc7519
- RFC 8725 — JWT Best Current Practices: https://www.rfc-editor.org/rfc/rfc8725
- RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens: https://www.rfc-editor.org/rfc/rfc8705
- RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession: https://www.rfc-editor.org/rfc/rfc9449
- SPIFFE — Workload Identity Concepts: https://spiffe.io/docs/latest/spiffe-about/overview/