# Boundary Between Infrastructure TLS Verification and Application Identity Mapping

## 1. The Distinction That Needs to Be Made

In systems using **X.509 certificates for client authentication**, the phrase “authenticated by certificate” often conflates two different things:

1. **TLS/mTLS verification at infrastructure:** the TLS terminator (web server, load balancer, ingress, reverse proxy, service mesh, or Spring Boot's embedded server itself) decides whether the **TLS peer's** certificate is trustworthy according to policy.
2. **Identity mapping at the application:** Spring Security determines which account/service the certificate or a **trusted assertion created by infrastructure** corresponds to, whether it is still allowed to be used, and which `GrantedAuthority` instances are assigned to it.

Key point: **a valid certificate at TLS does not automatically mean a valid application user; a username or HTTP header with a value matching a certificate subject is also not automatically proof of TLS authentication.**

For example: an internal CA issues a client certificate for `CN=lan`. The reverse proxy verifies the certificate and allows the connection. The HR profile application still needs to know which account `lan` corresponds to, whether the account status is locked, and whether it has `ROLE_HR` to view employee records. Without mapping/authorization, a successful TLS handshake only solves part of the problem.

### Two Trust Boundaries to See Clearly

~~~text
Case A — TLS terminates directly at the application:

Client with private key + X.509 certificate
       │  HTTPS + mTLS
       ▼
Spring Boot embedded server (Tomcat/Jetty...)
       │  verifies client certificate at TLS layer
       │  attaches received certificate to Servlet request
       ▼
Spring Security X.509 authentication
       │  extracts principal + loads account/authorities
       ▼
Controller / Service
          checks business permissions


Case B — TLS terminates at a reverse proxy:

Client with private key + X.509 certificate
       │  HTTPS + mTLS
       ▼
Reverse proxy / ingress  ◄── trust store, PKI policy
       │  verifies certificate, authenticates TLS peer
       │  creates verified identity metadata
       ▼  HTTP/mTLS between proxy and backend (a different connection)
Spring Boot application
       │  verifies source/provenance of assertion
       │  maps principal + authorities
       ▼
Controller / Service
          checks business permissions
~~~

In Case B, **mTLS from proxy to backend (if present) authenticates the proxy as the backend's TLS peer**, and does not turn the proxy into the original user's certificate. The original client identity must be passed using a **separate trust contract**, such as a signed assertion or metadata controlled by the proxy over a channel that only the proxy is allowed to use.

## 2. What Does Certificate Verification at the TLS Layer Actually Do?

X.509 is a certificate format containing a public key and fields such as subject, issuer, serial number, validity period, Subject Alternative Name (SAN), and Key Usage / Extended Key Usage depending on the profile. A certificate is **not a password**; the corresponding private key is not transmitted to the server.

With standard **server-authenticated TLS**, the server presents a certificate for the client to authenticate the server, and the protocol establishes a secure channel. With **mutual TLS (mTLS)**, the server also requests a client certificate. During the handshake, the TLS peer proves the right to use the corresponding private key and the verifier evaluates the certificate against trust configuration. Verification steps may include:

- Building a certificate path to a trusted CA and verifying signatures/issuance chain.
- Checking validity period, basic constraints, key usage, extended key usage, and certificate policies matching the **client authentication** purpose.
- Checking certificate revocation mechanisms (**CRL/OCSP**) if implemented by policy and product; do not assume every TLS stack automatically performs online revocation checks.
- Controlling TLS versions, allowed algorithms, which CAs certificates may come from, and whether a certificate is mandatory or optional.

When infrastructure rejects a client certificate, the failure can happen **right at the TLS handshake, before the HTTP request reaches Spring Security**. Therefore, application controllers, filters, or `@ExceptionHandler`s may never see the request to return custom JSON errors.

Distinguish the scope of each claim:

| Result / Data | What Can Be Concluded? | What Cannot Be Concluded Yet? |
|---|---|---|
| Successful TLS handshake with required client auth and proper validation policy | The TLS peer presented a certificate meeting the TLS terminator's policy. | That the peer has an application account, admin group, or permission to call sensitive APIs. |
| Certificate has subject `CN=lan` | The certificate contains that subject string. | That `lan` is unique across all CAs, is currently an employee, or is not locked in the application. |
| Certificate has SAN URI `spiffe://corp.example/payments/api` | The certificate asserts that URI under the issuing CA/PKI policy. | That the application automatically grants all permissions to that workload. |
| Request carries `X-Client-Cert` or `X-Verified-User` | There is an HTTP header with that value. | That the header was created by a trusted TLS terminator and not spoofed by a client or another proxy. |
| HTTP `200` from an endpoint behind TLS | The request was handled successfully according to that endpoint's logic. | That every endpoint in the same application has proper authorization configured. |

**mTLS authenticates the TLS peer on a specific connection.** When TLS is terminated and another connection is opened, the authentication result is not automatically “carried over as-is” to the next connection.

## 3. Boundary #1: Application Directly Terminates TLS

If Spring Boot's embedded Tomcat (or equivalent servlet container) receives HTTPS/mTLS directly, the container checks the certificate based on its TLS trust store/policy. When a client certificate is attached to the request, **Jakarta Servlet** specifies the request attribute:

~~~java
Object value = request.getAttribute("jakarta.servlet.request.X509Certificate");
~~~

A valid value is an array `java.security.cert.X509Certificate[]`; the first certificate is the one presented by the client, followed by the associated chain. **Simply reading this attribute does not mean the application itself validated the certificate**: assurance of origin and chain validation comes from container/TLS configuration and protection of the request path. The application may perform additional identity constraint checks according to business needs.

Spring Security (Servlet) provides `X509AuthenticationFilter` to obtain the certificate from the container-processed request, extract the principal, and then use pre-authentication to look up the user and authorities. The term **pre-authenticated** means a layer outside Spring Security performed the underlying authentication; Spring proceeds to bind that information into the application security model.

### Spring Boot Example: mTLS Directly at the Server

Suppose the server has a key store containing the server certificate/private key, and a trust store containing CAs allowed to issue **client certificates**:

~~~properties
server.port=8443
server.ssl.enabled=true
server.ssl.key-store=classpath:server.p12
server.ssl.key-store-type=PKCS12
server.ssl.key-store-password=read-from-secret-management
server.ssl.trust-store=classpath:client-trust.p12
server.ssl.trust-store-type=PKCS12
server.ssl.trust-store-password=read-from-secret-management
server.ssl.client-auth=need
~~~

Paths and passwords here are **illustrative values** and must be replaced with real resources and secrets before running. Do not store private keys or production passwords in the repository. `client-auth=need` requires the client to provide a valid certificate on the direct connection to the server. `client-auth=want` only asks the client to try presenting one; if missing, the handshake can still succeed, so routes protected by X.509 must be handled separately. The trust store must match the CA issuing client certificates and should not trust all public CAs by default.

The Spring Security **6.x, Java 17+, Servlet** example below illustrates the post-TLS mapping part. This is a class inside a **Spring Boot project with `spring-boot-starter-security`**, not a standalone Java program; `InMemoryUserDetailsManager` is only for illustrating the mapping result.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class CertificateSecurityConfig {

    @Bean
    UserDetailsService userDetailsService() {
        return new InMemoryUserDetailsManager(
            User.withUsername("lan")
                .password("{noop}unused-for-this-x509-example")
                .roles("EMPLOYEE")
                .build()
        );
    }

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http,
            UserDetailsService users) throws Exception {
        http
            .x509(x509 -> x509.userDetailsService(users))
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated());
        return http.build();
    }
}
~~~

Meaning of each part:

1. The TLS/servlet container authenticates the client certificate on the connection to the server; the Java code above **does not perform TLS certificate path validation itself**.
2. With the default configuration of Spring Security 6, the X.509 principal extractor relies on the **CN** to look up the username. When a valid certificate carries `CN=lan`, `UserDetailsService` looks up the account `lan`.
3. Account `lan` in the example has `ROLE_EMPLOYEE`, so it can access endpoints requiring `authenticated()`; it lacks `ROLE_ADMIN`, so access to `/api/admin/**` is denied. Role assignment policy belongs to the application.
4. The dummy password in the example only satisfies the user model interface; **X.509 pre-authentication does not prompt for an application password when authenticating with a client certificate**.
5. Production must replace the in-memory account with a real user source, check account enabled/locked/expired flags, manage permissions by real roles, and decide on a stable identifier based on the certificate profile and issuance policy.

**Security limitation of the example:** using CN as an identity is only sufficient for a demo when the CA enforces a policy guaranteeing unique CNs and never mis-issuing identities. In multi-CA/multi-tenant systems, CNs can collide or change. Consider **SAN (URI/DNS/email suited to the subject type), issuer, and designated stable attributes**, and use `x509PrincipalExtractor(...)` or a dedicated verified mapping process. Do not use the serial number alone as a global key because it is only unique within the scope of a single issuer.

An easily overlooked detail: when `server.ssl.client-auth=need`, **TLS is enforced right at the listener**, so even endpoints marked `permitAll()` in Spring Security cannot be reached if the client has no certificate. `permitAll()` cannot be used to relax the TLS handshake requirement.

## 4. Boundary #2: TLS Terminates at a Proxy, Ingress, or Load Balancer

This is the scenario where critical mistakes happen most easily:

~~~text
Client                       Gateway                     Spring Boot
   │                           │                              │
   ├─ HTTPS/mTLS ─────────────>│                              │
   │                           ├─ verify client certificate   │
   │                           │                              │
   │                           ├─ HTTP request ──────────────>│
   │                           │  (certificate does not cross │
   │                           │   to the new connection)     │
   │                           │                              │
   │                           │  optional: identity metadata │
   │                           ├─ trusted assertion ─────────>│
   │                           │                              ├─ map user/role
   │                           │                              └─ authorize
~~~

At the backend, `request.getAttribute("jakarta.servlet.request.X509Certificate")` usually **does not contain the original client's certificate**. If the proxy uses mTLS when calling the backend, the servlet container may see the **proxy's certificate** on the second connection. Therefore, simply enabling `http.x509(...)` on the backend **does not automatically handle** mapping the end user authenticated by the gateway.

### Illustrative NGINX Configuration Sample

~~~nginx
server {
    listen 443 ssl;
    server_name internal.corp.example;

    ssl_certificate     /etc/nginx/tls/server.crt;
    ssl_certificate_key /etc/nginx/tls/server.key;

    ssl_client_certificate /etc/nginx/tls/allowed-client-ca.pem;
    ssl_verify_client on;
    ssl_verify_depth 2;

    location / {
        proxy_set_header X-Verified-Client-Subject $ssl_client_s_dn;
        proxy_set_header X-Verified-Client-Status  $ssl_client_verify;

        proxy_pass http://127.0.0.1:8080;
    }
}
~~~

This is a **sample to explain each layer's role**, not a complete production configuration. With `ssl_verify_client on`, NGINX requests and verifies the client certificate against the configured CA. `$ssl_client_verify` can return `SUCCESS` when verification succeeds; `$ssl_client_s_dn` contains the subject DN of the client certificate received by the proxy. The `proxy_set_header` directives show the proxy **actively writing** metadata values into the request sent to the backend.

To turn metadata into a trustworthy assertion, **all** of these conditions must be established:

- The backend only accepts requests from the authenticated proxy: network/port restrictions, firewall/loopback, or proxy → backend mTLS, with no direct access path from clients to the backend.
- The proxy **strips and overwrites all versions** of the identity headers at every entry point, handles duplicate headers/case variants properly, and never forwards client-supplied values.
- If there are multiple proxy tiers, every hop must preserve the provenance contract; do not let uncontrolled intermediaries inject/modify assertions.
- The application only accepts assertions at the **proper trust boundary**, verifying issuer/proxy identity and format; rejecting when missing, duplicated, malformed, empty, or arriving from an untrusted path. `X-Verified-Client-Status: SUCCESS` from an HTTP client **proves nothing on its own**.
- For distributed systems or complex boundaries, use **signed** identity assertions (verifying signature, issuer, audience, expiry, and appropriate bindings) or a well-designed inter-tier authentication mechanism. mTLS from proxy to backend protects the channel and authenticates the proxy; the application must still verify the identity claims forwarded by the proxy.
- Decide how to check certificate revocation, restrict CAs/profiles, and handle certificate rotation policies; `ssl_verify_client on` alone is not a complete PKI operational solution.

**Do not simply read `X-Verified-Client-Subject` and call `SecurityContextHolder.setContext(...)` in an arbitrary filter.** When implementing pre-authentication, you need an integration that enforces the trust boundary, looks up users by defined mapping, manages authorities, and defaults to **fail closed**. `X-Forwarded-For` / `X-Forwarded-Proto` are for network/redirect information through proxies; they are **not** X.509 identity proof.

### Three Deployment Models with Different Consequences

| Model | Who Verifies the Original Certificate? | What Proof Does the Application Receive? | Mapping Responsibility |
|---|---|---|---|
| **TLS passthrough to app** | The app's embedded server / servlet container. | Certificate request attribute with provenance from the app's TLS. | X.509 authentication/pre-auth in Spring. |
| **TLS termination + proxy metadata** | Ingress/gateway. | Assertion/header issued by the proxy over a trusted path (if implemented properly). | Trusted pre-auth integration, account/role lookup, authorization. |
| **TLS termination + mTLS proxy→backend** | Gateway verifies original client; backend verifies **proxy**. | Proxy certificate on the second connection, plus separate assertion about original client (if any). | Proxy authentication and original client mapping are two separate steps. |

When a service mesh assigns a workload identity to an internal connection, that is typically the identity of the **calling workload**, not automatically the final employee's identity. To enforce user permissions, the application needs a user token/assertion with appropriate provenance and scope.

## 5. Boundary #3: From Certificate Identity to Application Account and Permissions

A strict mapping pipeline can be represented as:

~~~text
Verified TLS peer / verified gateway assertion
               │
               ▼
Extract canonical identity
  • what subject: user, service, device, workload?
  • which namespace/issuer/tenant?
  • which certified stable field (SAN/ID)?
               │
               ▼
Resolve exactly one application account
  • exists? active? not locked?
  • is the identifier duplicated/mismatched?
               │
               ▼
Build Spring Authentication / authorities
  • ROLE_EMPLOYEE, APP_READ, APP_APPROVE...
               │
               ▼
Authorization on each request/resource
               │
               ▼
Allow or Deny
~~~

**Identity mapping** requires a concrete policy, not just a single regex applied to all certificates.

For example, a payment server certificate has SAN URI `spiffe://corp.example/ns/payments/sa/collector`. The application can map **that exact** URI, within an authorized namespace/issuer, to account `payments-collector` with authority `PAYMENT_PUBLISH`. Another client certificate with CN `collector` but without the same SAN/issuer must **not** receive that permission.

In an employee model example: the certificate carries an employee ID issued by the corporate CA after identity verification. The application looks up the employee ID in the user table, checks active status, and retrieves permissions from a role management service. **Roles do not necessarily reside inside the certificate**, and roles in a certificate (if embedded) should not be used outside approved CA, lifecycle, and freshness policies.

Decisions that must be clearly defined:

1. **Durable identifier:** display CN may change; subject DN may be unstable; SAN or a PKI-profile identifier may be more suitable. When distinguishing multiple organizations, the namespace along with issuer/policy is also part of the identity.
2. **CA constraints:** “signed by a trusted CA” is insufficient if that CA is allowed to issue for many subject types. Narrow down CA, EKU, policy OID, or trust domain by business need.
3. **Account status:** locking an application account must block access even if the certificate has not expired. Base authorization on a database/authorization service kept current per policy.
4. **Certificate renewal and revocation:** user identity should persist across key/certificate rotation if policy dictates; conversely, permission revocation must have a clear effective time.
5. **Rule when evidence is missing:** if a unique account cannot be matched, provenance cannot be verified, or required roles cannot be read, deny; never “fallback” to guest or admin.

### Java 17 Code Illustrating the Mapping Boundary

This is a **standalone decision-logic model**, runnable on Java 17. `attestedByInfrastructure` is an **output already verified by a trusted integration**; in real code, **never take this boolean from an HTTP header or request parameter**.

~~~java
public class IdentityBoundaryDemo {
    record VerifiedIdentity(String subject, boolean attestedByInfrastructure) {}

    static String resolveAccount(VerifiedIdentity identity) {
        if (!identity.attestedByInfrastructure()) {
            throw new SecurityException("untrusted origin");
        }
        return switch (identity.subject()) {
            case "spiffe://corp.example/payments/collector" -> "payments-collector";
            case "spiffe://corp.example/reports/reader"     -> "reports-reader";
            default -> throw new SecurityException("unmapped identity");
        };
    }

    public static void main(String[] args) {
        var trusted = new VerifiedIdentity(
            "spiffe://corp.example/payments/collector", true);
        System.out.println(resolveAccount(trusted));

        try {
            var forged = new VerifiedIdentity(
                "spiffe://corp.example/payments/collector", false);
            System.out.println(resolveAccount(forged));
        } catch (SecurityException e) {
            System.out.println(e.getMessage());
        }
    }
}
~~~

Save as `IdentityBoundaryDemo.java` and run:

~~~bash
javac IdentityBoundaryDemo.java
java IdentityBoundaryDemo
~~~

Exact stdout:

~~~text
payments-collector
untrusted origin
~~~

The example only illustrates **accepting an identity after verifying provenance** and allowlist mapping. It is **not** a validator for TLS, JWT signatures, X.509 chains, issuers, or revocation. In a real system, these checks must be performed by properly configured and tested infrastructure or security libraries before invoking mapping code.

## 6. Why Are Vulnerabilities Common When Boundaries Are Confused?

### Scenario 1: Backend Exposes a Public Port Yet Trusts Headers

~~~http
GET /api/payroll HTTP/1.1
Host: backend.corp.example
X-Verified-Client-Subject: CN=director
X-Verified-Client-Status: SUCCESS
~~~

If a client connects directly to the backend and the application trusts the two headers above without verifying provenance, it may treat an attacker-sent string as an infrastructure-verified identity. **A header having the words “Verified” or “SUCCESS” does not make it trustworthy.**

Remediation: close direct access paths, have the proxy strip/overwrite headers, authenticate the proxy→backend hop, and clearly define the assertion verification provider. Where architecture allows, use signed assertions with mandatory validation checks.

### Scenario 2: “Valid Certificate” Interpreted as “Administrator”

A CA may issue certificates for both employees and servers. If the application grants `ROLE_ADMIN` to every valid certificate, the system has turned a **device/subject authentication** condition into an unfounded **authorization** decision. Explicitly map to accounts and roles; machine certificates should not automatically become human accounts.

### Scenario 3: Two Certificates with the Same CN

Certificates from two different departments both have `CN=service-api`. An extractor taking only the CN can mistakenly map them to the same account. You must distinguish issuer, trust domain, SAN, or an identifier guaranteed unique by the CA. Using only thumbprint/serial can identify a specific certificate, but incurs operational overhead during rotation; the choice depends on whether you need certificate pinning or persistent user/workload identity.

### Scenario 4: Backend Uses mTLS with Gateway and Treats Gateway's CN as End-User

The backend sees `CN=api-gateway` because the gateway is the TLS peer of the downstream connection. `http.x509(...)` might then map `api-gateway`, which **does not prove** the request belongs to user Lan in front of the gateway. If authorization per Lan is needed, a separate user assertion verified by the gateway is required.

### Scenario 5: Spring Security Configured Correctly but TLS Policy Is Wrong

`http.x509(...)` cannot compensate for an overly broad trust store, optional client certificates, expired certificates forwarded by a proxy labeled “verified”, or skipping revocation checks against policy. TLS validation and Spring user mapping are **two layers that must be tested independently**.

### Scenario 6: Protecting Requests but Forgetting Sessions and Certificate Rotation

After authenticating with mTLS, a system may retain a session or cached authentication. If an employee is locked out or a certificate is revoked, existing connections and sessions may continue according to current cache/session policies. You must decide on TTLs, account re-check mechanisms, session revocation, and when permission changes take effect. **Do not assume revoking a certificate immediately terminates every session.**

## 7. Practical Scenario: HR Portal Behind a Reverse Proxy

Suppose employee Lan has a client certificate issued by the HR CA. NGINX is the TLS terminator, Spring Boot runs behind the proxy, and payroll data is restricted to employees with authority `PAYROLL_VIEW`.

Desired flow:

1. The browser/client establishes mTLS with NGINX. NGINX checks the certificate against the HR trust store and certificate acceptance policy. If missing/invalid, the request is blocked at infrastructure; Spring does not have to interpret TLS errors itself.
2. NGINX determines the normalized subject/SAN, attaches a protected assertion, and forwards the request over an authenticated path to the backend.
3. The backend accepts the assertion only after verifying the gateway's provenance. The backend maps the identity precisely to Lan's account, verifies Lan is active, and retrieves authorities from a trusted source.
4. Spring Security stores the `Authentication` object containing Lan's principal and valid authorities in the request's `SecurityContext`; the application checks `PAYROLL_VIEW` when accessing payroll features.
5. When Lan transfers departments and loses `PAYROLL_VIEW`, caches/sessions and the role source must synchronize within policy timelines; an unexpired certificate is **not** a reason to retain old permissions.

A commonly used reference design:

| Layer | Data Checked | Decision |
|---|---|---|
| TLS terminator | Certificate chain, authorized CA, client auth purpose, validity period, revocation policy. | Allow or reject handshake/HTTP before backend. |
| Trusted identity bridge | Assertion source, proxy identity, signature/issuer/audience/expiry if using tokens; anti-header-spoofing. | Accept or reject identity provenance. |
| Spring Security authentication | Normalized principal, account exists/active, role mapping. | Create Authentication with authorities or fail. |
| Spring authorization + business logic | Role/scope, resource ownership, transaction state. | Allow/403 per operation/resource. |

## 8. Mandatory Boundary-Focused Testing

The test suite should verify the **exact point of rejection** and the application consequences, rather than looking at just a single HTTP code.

| Test | Expectation | Where to Observe |
|---|---|---|
| Client provides no certificate under `need/on` policy | Blocked at TLS or terminator component. | Terminator access/error logs, handshake/curl. |
| Certificate signed by an unauthorized CA | Does not reach protected routes. | TLS verification/error logs. |
| Valid certificate, but SAN/identity maps to no account | Rejected by app authentication/mapping. | Backend security audit; do not grant anonymous special roles. |
| Valid certificate, locked account | No valid authenticated session. | Application account policy / audit. |
| Valid account, missing `ROLE_ADMIN` | Rejected at authorization, typically HTTP 403 once authenticated. | Spring Security authorization log. |
| Client sends `X-Verified-Client-Subject` header through proxy | Proxy strips/overwrites; app identity must come from verified TLS session. | Controlled header capture at backend hop. |
| Client calls backend port directly with forged header | Connection blocked or assertion rejected. | Firewall/ingress and application audit. |
| Gateway calls backend via separate mTLS | Backend sees **gateway certificate** on second connection; end-user assertion handled separately. | TLS peer info and application principal. |
| Certificate expired, revoked, or switched to another CA | Matches configured TLS/PKI policy; test expiry/caching. | Terminator/DC/PKI audit. |
| Certificate rotated while keeping same valid user/workload | Stable mapping or proper re-enrollment as designed. | User mapping and key-change audit. |
| Two certificates with same CN but different issuer/trust domain | Must not accidentally map to the same account if policy forbids it. | Identity resolver/audit. |
| Gateway sends duplicate headers or omits assertion | Fail closed, never pick a value arbitrarily. | Backend ingress integration and audit. |

You can use curl with a client certificate in a test environment:

~~~bash
curl --verbose \
  --cert client.crt \
  --key client.key \
  --cacert server-ca.crt \
  https://internal.corp.example/api/profile
~~~

This command is only an **illustrative structure**; paths, certificates, and endpoints must exist. `--cacert` on the client verifies the **server certificate**; `--cert`/`--key` provide client identity when the server requires mTLS. Do not use `-k` or disable verification to “fix” a certificate error during authentication testing.

When testing invalid certificates with curl, **do not assume you will always get HTTP 401/403**: it may be rejected at TLS and receive no HTTP response. HTTP 401/403 generally belong to the application layer once the request passes infrastructure.

## 9. Operations, Observability, and Troubleshooting

A well-built system distinguishes errors by layer directly from telemetry:

- **TLS terminator:** log handshake/verification failure types, CA policy, and certificate status; limit sensitive data. Do not log private keys or unnecessary certificate contents.
- **Trusted bridge:** log proxy identity, assertion issuer, request correlation ID, and provenance verification result; check mismatches, duplicate headers, bad signatures.
- **Spring authentication:** log non-existent/locked account reasons or inconsistent mappings in a controlled way; **do not** return details to clients to avoid account enumeration.
- **Authorization:** record denied account/role and resource/action in proper audit format, without logging sensitive HR record data.
- **CA management:** monitor soon-to-expire certificates, CA/client certificate rotation, OCSP/CRL per policy, and trust-store rollouts.
- **Traffic topology:** re-verify after changing ingress, adding a service mesh sidecar, switching from TLS passthrough to TLS termination, or enabling intermediate CDN/LBs; changing one hop can change **who the actual TLS peer is**.

Some symptoms requiring proper reasoning:

- `request.getAttribute("jakarta.servlet.request.X509Certificate") == null` on a backend behind a proxy: **not necessarily a Spring Security bug**; the backend might not be the TLS terminator for the client connection.
- Proxy returns a client-certificate error while app logs no request: the request failed **before reaching Spring**.
- Login succeeds but returns 403: prioritize checking authority mapping and endpoint rules, **do not** rush to broaden CA trust.
- Every request behind the proxy shows the same principal `gateway`: the app is seeing the TLS peer of the proxy → backend hop without trusted end-user mapping.
- Locked user can still access: check caches/sessions, authority refresh intervals, and secondary paths bypassing authentication policy.

## 10. Architecture Selection Principles and Conclusion

When the application directly receives TLS/mTLS, configure the trust store and client-auth on the server, then use Spring Security X.509 to map the certificate to an **account and authorities**. When an ingress/proxy handles TLS/mTLS first, treat the certificate check result as the **output of a separate trust boundary**: the backend must receive an assertion with trusted provenance and perform mapping, never trusting any header simply because its name resembles certificate data.

Clearly answer five questions before deployment:

1. **Who is the TLS terminator?** Which component actually verifies the client's original certificate?
2. **Who is the backend's TLS peer?** The end client, gateway, or service mesh sidecar?
3. **How is identity transmitted?** Directly via Servlet certificate attribute, or via an assertion signed/forwarded by the proxy over an authenticated channel?
4. **Which identifier is used for mapping?** How do SAN/issuer/trust domain/CA policies guarantee uniqueness and lifecycle?
5. **Who decides permissions?** What is the account state, where do authorities come from, at which layer are specific resources checked, and when are permissions refreshed?

**Core message:** TLS verifies *the connection and the key-holding subject per PKI policy*; Spring Security determines *an application-meaningful principal*; authorization decides *what that principal is allowed to do*. Each layer must have its own source of truth, clear trust boundaries, and deny-by-default rules when evidence is insufficient.

## References

- [Spring Security — X.509 Authentication (Servlet)](https://docs.spring.io/spring-security/reference/servlet/authentication/x509.html): X.509 filter, principal extraction, and user mapping.
- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): Authentication, SecurityContext, GrantedAuthority, and providers.
- [Spring Boot — SSL / Embedded Web Server](https://docs.spring.io/spring-boot/how-to/webserver.html): `server.ssl.*` configuration for embedded containers.
- [NGINX — ngx_http_ssl_module](https://nginx.org/en/docs/http/ngx_http_ssl_module.html): `ssl_verify_client`, `ssl_client_s_dn`, `ssl_client_verify`, and certificate policies.
- [Jakarta Servlet Specification 6.1](https://jakarta.ee/specifications/servlet/6.1/): client certificate via `jakarta.servlet.request.X509Certificate` request attribute.
- [RFC 5280 — Internet X.509 PKI Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280): certificate structure, path validation, and revocation.
