# X.509 Certificates Behind a Reverse Proxy: Protecting Transport and Authentication Headers

## 1. Objectives and Use Case

When a Spring Security application runs behind a **reverse proxy** (NGINX, Apache HTTP Server, ingress controller, API gateway, or service mesh), the TLS connection from the client may **terminate at the proxy** rather than at the Java process. This directly affects **X.509 client certificate** authentication.

Suppose a B2B system allows only clients with certificates issued by an enterprise CA to access its API:

~~~text
Client (certificate + private key)
          │
          │ HTTPS + mutual TLS (mTLS)
          ▼
    Reverse proxy
    - verifies TLS handshake and client certificate
    - extracts verified identity
    - regenerates trusted header
          │
          │ HTTP over loopback / HTTPS or mTLS on internal network
          ▼
     Spring Boot API
    - reads identity from trusted proxy
    - maps identity → authorities
    - decides allow/deny access
~~~

Lesson objectives:

1. Understand **two certificate-receiving models**: TLS directly into Java vs. TLS terminated at a proxy.
2. Distinguish a **verified real X.509 certificate** from an **HTTP header string carrying certificate info**.
3. Know how to configure a proxy to require client certificates, verify CAs, forward only verified identities, and prevent header spoofing.
4. Know how to use **pre-authentication** in Spring Security when identity is provided by a proxy; do not confuse it with `http.x509()`.
5. Protect the full **client → proxy → backend** path, restrict direct access paths, monitor certificate lifecycle, and test negative scenarios.

**Most important rule:** headers sent by a client can be spoofed. A header containing a username or PEM certificate **does not prove** the client possesses the private key. Trust an identity header only when the entire path and the system generating the header are secured.

## 2. Review of X.509 and Mutual TLS

An X.509 certificate is a digitally signed document binding a public key to identifying information and attributes such as subject, subject alternative name (SAN), issuer, serial number, validity period, key usage, and extended key usage (EKU).

With **one-way TLS**, the client verifies the **server** certificate. With **mutual TLS (mTLS)**, the server/proxy also requires the client to present a valid certificate and verifies that the client holds the right to use the corresponding private key during the TLS handshake.

Simplified steps:

1. The client opens a TLS connection to the proxy.
2. The proxy presents its server certificate; the client verifies hostname, trust chain, and applicable conditions.
3. The proxy requests a client certificate.
4. The client presents its certificate chain and proves private key possession via the handshake.
5. The proxy verifies the certificate chain against trusted CAs, validity, policy/EKU, and certificate revocation mechanisms per configuration.
6. **Only upon success** does the proxy construct an HTTP request to the backend and attach the identity derived from the TLS connection.

The mTLS outcome is proof of identity at the **TLS termination endpoint**. If that endpoint is a proxy, the Java backend does not directly witness the original client's handshake.

Concepts to distinguish:

| Concept | Meaning | Notes |
| --- | --- | --- |
| Server certificate | Certificate of the website/proxy | Authenticates the server; does not replace client certificate |
| Client certificate | Certificate identifying the client | Must be verified and used for its intended purpose |
| Client private key | Client's private key | Never transmitted via headers or sent to the backend |
| Subject DN | Distinguished name such as `CN=app-client,O=Example` | May not be unique across CAs or issuance policies |
| SAN | Additional identifiers such as DNS, URI, or email | Should have stable identity mapping rules |
| Issuer + serial | Issuing CA and certificate serial number | Useful for correlation, revocation, and auditing |
| CA trust store | Set of CAs allowed to validate client certificates | Trust only authorized CAs; avoid overly broad trust |
| Certificate revocation | Mechanism to reject revoked certificates | Requires CRL/OCSP policy or equivalent; not enabled by default |

## 3. What Does Spring Security See When TLS Terminates at a Proxy?

### 3.1. Case A: TLS Reaches the Servlet Container Directly

If Tomcat/Jetty handles the mTLS connection directly, the servlet container can expose the client certificate chain through the request attribute:

`jakarta.servlet.request.X509Certificate`

Spring Security Servlet provides `X509AuthenticationFilter` and the DSL:

~~~java
http.x509(Customizer.withDefaults());
~~~

This is an **illustrative configuration snippet** inside `SecurityFilterChain`, not a standalone program. The filter reads the certificate published by the servlet container, extracts the principal, looks up the account, and attaches permissions; the TLS connector is responsible for checking the handshake/certificate. Configure the connector/trust store properly before expecting `x509()` to work.

### 3.2. Case B: TLS Terminates at a Reverse Proxy

If the proxy accepts mTLS and calls the application over HTTP, the servlet container only sees the connection from the **proxy**. The original client's X.509 request attribute usually **does not exist**. Calling `http.x509()` on the backend **does not automatically read** any header like `X-Client-Cert` or `X-Forwarded-Client-Cert`.

Two integration approaches:

- **Identity-based pre-authentication:** the proxy authenticates the client, selects the verified identity, and passes it via a **proxy-set** header; Spring Security uses `RequestHeaderAuthenticationFilter`, maps user/roles, and checks authorization.
- **Passing certificate to the servlet container:** the proxy forwards certificate info in a format expected by the container; a component like **Tomcat SSLValve** (when properly configured) can convert trusted headers into the request attribute. Only then does `x509()` have data to process, but **SSLValve's inputs must be protected** against spoofing. Forwarding a PEM certificate does not substitute for mTLS verification itself.

Comparison table:

| Aspect | Java Receives mTLS Directly | Proxy Terminates mTLS, Forwards Identity |
| --- | --- | --- |
| Component seeing client handshake | Servlet container | Reverse proxy |
| Source of identity | Certificate published by container | Header generated by trusted proxy |
| Typical Spring Security | `http.x509()` | `RequestHeaderAuthenticationFilter` + pre-auth provider |
| Client cert verification | TLS connector | Reverse proxy |
| Primary risk | Misconfigured connector/PKI | Spoofed headers, proxy bypass, insecure internal hop |
| Source of app permissions | UserDetailsService/AuthenticationProvider | UserDetailsService or trusted group mapping |

**Do not conflate the two cases:** a header named `X-SSL-Client-Cert` does not automatically become the servlet attribute `jakarta.servlet.request.X509Certificate`.

## 4. Trust Boundaries and Four Mandatory Conditions

An architecture accepting identity headers must satisfy **all** of the following conditions simultaneously.

### Condition 1: The Proxy Genuinely Verifies the Certificate

Do not merely check “PEM header exists” or “client sent `CN=Alice`”. The reverse proxy must perform mTLS and accept only certificates valid under CA, algorithm/policy, validity period, purpose (client authentication), and revocation status as required by the system.

If you merely forward a public certificate in a header, someone else can **copy that exact certificate** without holding the private key. Parsing PEM in Java or checking the certificate's CA signature does not itself prove the HTTP sender owns the private key.

### Condition 2: Strip or Overwrite Client-Supplied Headers

Suppose the application trusts the `X-Verified-Client-DN` header. A client could send:

~~~http
GET /whoami HTTP/1.1
Host: api.example.test
X-Verified-Client-DN: CN=admin,O=Example
~~~

If the proxy passes this header untouched to the backend, the client can **impersonate** someone else. The proxy must discard external headers and **recreate** the value from verified TLS info. HTTP header names are case-insensitive; control case variants, duplicate headers, and every ingress path.

Do not infer trust from header names: `X-Forwarded-Client-Cert`, `X-SSL-CERT`, `SSL_CLIENT_S_DN`, or `X-Verified-*` are just **HTTP strings**; trustworthiness depends on the system that created them.

### Condition 3: Backend Accepts Requests Only Through the Trusted Proxy

If the internet or an untrusted workload can call `http://backend:8080` directly, it can send forged identity headers and **bypass mTLS**. Therefore, you must:

- Block direct access with firewalls/security groups, Kubernetes NetworkPolicy, service mesh policies, or loopback binding.
- Restrict all secondary ports, direct hostnames, health/admin listeners, and routes through other ingresses.
- When proxy and backend are on **different hosts**, use server-authenticated TLS and prefer mTLS between proxy and backend, plus network ACLs.
- Also check whether the backend can be reached through another internal proxy that does not sanitize headers.

**Checking only source IP from `X-Forwarded-For` is insufficient**, because that header can also be spoofed if the proxy chain is misconfigured.

### Condition 4: Backend Trusts Only Provisioned and Authorized Identities

A valid certificate issued by a trusted CA does not inherently grant access to every API. The backend must map the certificate identifier to a provisioned account/service and attach appropriate authorities.

Do not treat every `CN` as a privileged username. In organizations with multiple CAs, colliding subjects, reissued certificates, SAN changes, or distinct permission groups, you need a stable mapping key (such as issuer + serial, controlled SAN identifier, or an internal ID generated by the proxy after policy checks). Verify certificate rotation and permission revocation as well.

## 5. NGINX Example: Accepting mTLS and Forwarding Verified Identity

The example below is for **NGINX and Spring Boot running on the same host**. Spring listens on `127.0.0.1:8080`; NGINX is the sole gateway for external clients.

Learning assumptions:

- `api.example.test` points to the proxy; the server certificate has a valid SAN for that name.
- `/etc/nginx/certs/server.crt` and `server.key` belong to the proxy; `client-ca.crt` is the CA allowed to issue **client** certificates for this system.
- The client uses a certificate whose subject DN is exactly `CN=app-client,O=Example` when output by NGINX in RFC 2253 format.
- System administrators have configured certificate lifecycle, CA trust, revocation policy, and private key file permissions.

Sample NGINX configuration (`server` context):

~~~nginx
server {
    listen 443 ssl;
    server_name api.example.test;

    ssl_certificate     /etc/nginx/certs/server.crt;
    ssl_certificate_key /etc/nginx/certs/server.key;

    # Trusted CA for verifying the CLIENT certificate.
    ssl_client_certificate /etc/nginx/certs/client-ca.crt;
    ssl_verify_client on;
    ssl_verify_depth 2;
    ssl_protocols TLSv1.2 TLSv1.3;

    location / {
        proxy_pass http://127.0.0.1:8080;

        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto https;

        # Overwrite client-supplied header with value provided by TLS at NGINX.
        proxy_set_header X-Verified-Client-DN $ssl_client_s_dn;

        # Strip identity headers not used by the application.
        proxy_set_header X-Forwarded-Client-Cert "";
        proxy_set_header X-SSL-Client-Cert "";
    }
}
~~~

**Important explanations:**

- `ssl_verify_client on` requires and verifies the client certificate. Missing, invalid, or untrusted-CA certificates are rejected **at the proxy**; they are never forwarded into Spring as an authenticated user.
- `ssl_client_certificate` specifies the CA for client verification, **distinct from** `ssl_certificate` used as the server certificate.
- `$ssl_client_s_dn` obtains the subject DN of the client certificate presented on the TLS connection (modern NGINX returns RFC 2253 format). This is an **identity derived by the proxy after mTLS**, not original header content.
- `proxy_set_header X-Verified-Client-DN ...` actively **resets** the header in the upstream request. If the client sent a header with the same name, the value reaching the backend must be overwritten by the proxy.
- The `proxy_set_header ... ""` directives illustrate not forwarding other certificate headers that clients could spoof. Audit all actual header names that your backend/sidecar/framework might trust.
- `proxy_pass http://127.0.0.1:8080` is appropriate only on the **same machine**, with the backend bound to loopback and the local host secured. This is not a secure configuration for a network hop between two machines.

**NGINX configurations must be tested on the deployed version.** If `proxy_set_header` directives are set at the `location` level, directives of the same kind inherited from parent blocks may no longer apply as expected; verify effective configuration and upstream traffic.

### 5.1. When Proxy and Backend Are on Two Different Machines

HTTPS and upstream authentication are required; the configuration below is an **illustrative snippet** replacing loopback HTTP `proxy_pass`, to be used only when the backend actually serves HTTPS with matching CA and policies:

~~~nginx
proxy_pass https://app.internal.example:8443;
proxy_ssl_server_name on;
proxy_ssl_name app.internal.example;
proxy_ssl_verify on;
proxy_ssl_trusted_certificate /etc/nginx/certs/backend-ca.crt;

# Enable when the backend also requires authenticating the proxy via mTLS:
proxy_ssl_certificate /etc/nginx/certs/proxy-client.crt;
proxy_ssl_certificate_key /etc/nginx/certs/proxy-client.key;
~~~

- `proxy_ssl_verify on` forces the proxy to verify the backend certificate; defaults in many reverse proxy setups should not be assumed to verify upstream.
- The backend must restrict port 8443 so only the proxy may connect and verify the proxy's client certificate if using upstream mTLS.
- You must still **sanitize and regenerate identity headers** at the proper trust point; HTTPS between hops does not stop a misconfigured proxy from forwarding spoofed headers.
- If there are multiple layers of load balancers/ingress/mesh, document which layer performs client mTLS, which layer regenerates identity, and which layer strips external headers. Never assume NGINX on the second hop still sees the client certificate from the first hop.

## 6. Spring Security Example: Pre-Authentication via Protected Header

### 6.1. Choosing the Right Mechanism

Spring Security provides `RequestHeaderAuthenticationFilter` to read a principal from a request header supplied by an external authentication system. This filter **does not verify certificates or digital signatures**. It only reads a username; the result is passed to `AuthenticationManager` and `PreAuthenticatedAuthenticationProvider` to load account details and authorities.

Therefore, the example below **must only be used behind a proxy configured with mTLS + header sanitization + backend bypass prevention**. Running Spring Boot standalone and sending arbitrary headers allows impersonating users; that is the nature of pre-authentication, not a post-build bug.

### 6.2. Creating the Project

Use **Java 17+**, **Spring Boot 3.x**, and corresponding Spring Security 6.x. Create a Maven project on Spring Initializr with:

- `spring-boot-starter-web` (Spring MVC/Servlet, embedded Tomcat).
- `spring-boot-starter-security`.

`spring-security-ldap` is not needed because this lesson does not perform LDAP binds. A separate X.509 dependency is not needed to use `RequestHeaderAuthenticationFilter`; the class is inside Spring Security Web provided by the security starter.

File `src/main/resources/application.properties`:

~~~properties
# Demo: NGINX and Spring Boot on the same host.
server.address=127.0.0.1
server.port=8080
~~~

In container/Kubernetes environments, bind addresses and NetworkPolicies must be designed for the real topology. Copying this loopback config verbatim into two separate containers usually prevents NGINX from connecting; never expose the backend publicly to fix networking errors.

### 6.3. Complete Java Code

Create file `src/main/java/demo/mtls/ProxyCertificateDemoApplication.java`:

~~~java
package demo.mtls;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsByNameServiceWrapper;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationProvider;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationToken;
import org.springframework.security.web.authentication.preauth.RequestHeaderAuthenticationFilter;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ProxyCertificateDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ProxyCertificateDemoApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        // Demo provisioning: only registered subject receives ROLE_MTLS_CLIENT.
        var user = User.withUsername("CN=app-client,O=Example")
                .password("{noop}not-used-for-mtls")
                .roles("MTLS_CLIENT")
                .build();
        var users = new InMemoryUserDetailsManager(user);

        var userDetails =
                new UserDetailsByNameServiceWrapper<PreAuthenticatedAuthenticationToken>();
        userDetails.setUserDetailsService(users);

        var provider = new PreAuthenticatedAuthenticationProvider();
        provider.setPreAuthenticatedUserDetailsService(userDetails);

        // Create filter inside the chain, avoiding Servlet container auto-registering
        // an extra standalone Filter bean outside Spring Security.
        var preAuthFilter = new RequestHeaderAuthenticationFilter();
        preAuthFilter.setPrincipalRequestHeader("X-Verified-Client-DN");
        preAuthFilter.setExceptionIfHeaderMissing(true);
        preAuthFilter.setAuthenticationManager(new ProviderManager(provider));

        http
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/whoami").hasRole("MTLS_CLIENT")
                .anyRequest().denyAll())
            .addFilterBefore(preAuthFilter, UsernamePasswordAuthenticationFilter.class);

        return http.build();
    }

    @RestController
    static class CertificateApi {
        @GetMapping("/whoami")
        Map<String, String> whoAmI(Authentication authentication) {
            return Map.of("principal", authentication.getName());
        }
    }
}
~~~

### 6.4. Why Does This Configuration Fit Its Role?

1. `RequestHeaderAuthenticationFilter` reads `X-Verified-Client-DN` and extracts it as the pre-authentication principal. It **does not invoke TLS, check chains**, or inspect client private keys.
2. `PreAuthenticatedAuthenticationProvider` processes the pre-authentication token and queries `InMemoryUserDetailsManager` via `UserDetailsByNameServiceWrapper`. Only the DN provisioned in the example loads a user with role `MTLS_CLIENT`.
3. The password `not-used-for-mtls` is required data for the example's `UserDetails` object; the provider **does not check passwords** in the pre-auth path. Never store certificates/private keys there.
4. The `hasRole("MTLS_CLIENT")` rule checks for `ROLE_MTLS_CLIENT`. Other users or those without the matching role are denied at authorization.
5. `SessionCreationPolicy.STATELESS` avoids relying on sessions to persist identity: for every request, the proxy must supply the identity corresponding to **that request's own client TLS connection**. Do not overwrite another application's session policy if multiple security chains exist.
6. The filter is created **inside** the configuration method rather than declared as a standalone `@Bean Filter` so Spring Boot does not register it a second time outside `springSecurityFilterChain`.

The example has one fixed account for demonstration. Real systems should look up identity mappings/roles from controlled configuration or a database, supporting certificate rotation, tenant isolation, and permission updates. If two certificates share the same subject DN yet must not be treated as one identity, using DN alone as in the example is **not sufficient**; replace it with an identifier guaranteed unique by the certificate issuance policy.

### 6.5. Running and Testing

From the project's Maven directory:

~~~bash
./mvnw spring-boot:run
~~~

On Windows, use `mvnw.cmd spring-boot:run`; if no Maven Wrapper is present, use `mvn spring-boot:run`.

Once NGINX and real certificates are set up, test with a valid client certificate:

~~~bash
curl --cert client.crt --key client.key \
     --cacert server-ca.crt \
     https://api.example.test/whoami
~~~

The files must point to compatible test certificates/keys, the actual server CA, and the exact DNS hostname. The command above is for shells supporting `\` line continuation (Linux/macOS); on Windows it can be written on a single line. Never disable TLS verification with `-k`.

If the client certificate is valid and its subject DN matches the sample user, the expected response is:

~~~json
{"principal":"CN=app-client,O=Example"}
~~~

DN order/escaping may vary depending on actual certificate contents and proxy version. When they differ, compare RFC 2253 output against your system's identity mapping; do not arbitrarily change usernames.

Important negative tests:

| Test | Expected Result | Component That Must Block |
| --- | --- | --- |
| Send no client certificate | Request is not sent upstream as an authenticated user | NGINX mTLS |
| Client certificate not from trusted CA | Rejected at TLS boundary | NGINX mTLS |
| Certificate expired / disallowed usage | Rejected per TLS/PKI policy | NGINX/PKI |
| Client has no cert but sends `X-Verified-Client-DN: CN=app-client,O=Example` | Still rejected | NGINX mTLS |
| Client has valid cert but sends a forged header to NGINX | Backend must receive the DN extracted from TLS by NGINX, not the forged DN | NGINX header overwrite |
| Valid client cert, but DN is unprovisioned | Denied access to `/whoami` | Spring Security |
| Call backend directly from external network with forged header | Cannot establish connection to backend | Firewall/bind/NetworkPolicy |
| Authenticated user lacking required authority | Denied per authorization rule | Spring Security |

The exact HTTP status code for invalid certificates depends on NGINX version and configuration (TLS handshake, internal 495/496 handling, error_page); do not write tests hard-coding every case to 401.

**Trust-boundary verification test:** from the **same host** where the backend listens on loopback, sending a forged header directly to `127.0.0.1:8080` may be accepted by the pre-auth filter. This proves why **backend isolation is a mandatory part of the security design**. Production systems must also restrict untrusted local workloads from accessing that listener.

## 7. Protecting Headers Layer by Layer

### 7.1. Trust Only the Endpoint That Created the Identity

The identity must be supplied by the component that **actually verified mTLS**. If an outer load balancer verifies the certificate while an inner NGINX receives only HTTP, NGINX cannot claim `$ssl_client_s_dn` reflects the original client. Identity must be conveyed over an **authenticated channel between hops**, ensuring every hop drops forged inputs from the internet.

Many proxies have built-in mechanisms such as `X-Forwarded-Client-Cert`; configuration must specify **sanitize / set / append / forward** behavior, upstream/downstream trust levels, and which header the application reads. Avoid assuming every value arriving from XFCC has passed TLS verification.

### 7.2. Do Not Trust a Value Just Because It Looks Like PEM

If a proxy forwards certificates in PEM format via headers:

- NGINX provides `$ssl_client_escaped_cert` (URL-encoded PEM) used by some container integrations; the older `$ssl_client_cert` variable is discouraged.
- Enforce header size limits, decode exactly once, and handle encoding errors.
- A PEM header **does not prove possession of the private key**. The proxy must still verify the client during the handshake.
- If using Tomcat `SSLValve`, accept SSL headers only from a trusted proxy and ensure the container has no bypass access paths. Never enable SSLValve just because you see a header containing `CERT`.
- If the backend performs certificate chain checks itself, it still must understand the **proxy's** mTLS evidence and trusted transport; verifying certificate signatures alone on the backend is insufficient.

### 7.3. Preventing Header Injection, Duplicates, and Normalization Issues

HTTP header names are case-insensitive. Gateways and libraries may handle underscores, hyphens, or multiple headers with the same name differently. You must:

- Designate **exactly one** valid header name for the principal.
- Strip/overwrite client-originated values on **every ingress path**.
- Never arbitrarily concatenate multiple identity values or accept client-supplied lists.
- Enforce policies blocking malformed headers, empty/oversized values, CRLF control characters, and unusual encodings at the gateway.
- Preserve verified identities through canonicalization rules consistent with the provisioning system.
- Be cautious if also enabling `ForwardedHeaderFilter` or Spring Boot forward headers configuration: those components mainly handle host/scheme/client IP and **do not turn a client certificate header into mTLS proof**.

### 7.4. Never Leak Certificates or Sensitive Content

Do not write private keys, full PEMs, sensitive subjects, or certificate details into general access logs. Log only minimal fields needed for investigation: request/correlation ID, verification result, internal identity, issuer/serial or fingerprint per policy, and rejection reason at an appropriate level. Logs must have access control and retention policies.

If using SAN/email/CN for identification, treat them as **PKI-issued data** rather than safe free-form strings to embed directly into SQL, file paths, HTML output, or policy expressions. All queries and mappings still require input validation.

## 8. A Valid Certificate Does Not Mean Access Is Permitted

Spring Security separates **authentication** (who is calling) from **authorization** (what they are allowed to do).

Example:

- NGINX verifies a client certificate issued by an internal CA.
- Header carries DN `CN=partner-7,O=Example`.
- Backend confirms the DN is provisioned, but grants only `ROLE_READER`.
- Endpoint `/admin` requires `ROLE_ADMIN`, so it is still denied.

There are multiple ways to map certificates to identities:

| Mapping Approach | Pros | Risks to Manage |
| --- | --- | --- |
| Subject DN | Simple, readable | Can collide, change formatting, unstable on reissue |
| SAN URI/DNS/email | Expresses identity clearly per PKI policy | Must ensure CA issues within proper namespaces and extensions |
| Issuer + serial | Distinguishes each certificate per CA | Rotation issues new serial; mapping must be updated |
| Fingerprint | Binds to a specific certificate | Rotation changes value; algorithm choice and fingerprint management |
| Internal subject ID after proxy policy step | Decouples app from certificate format | Must protect mapping logic and proxy output headers |

In standard NGINX, `$ssl_client_fingerprint` is a SHA-1 fingerprint; do not rely on SHA-1 as a long-term identifier key requiring strong collision resistance. In complex systems, use a dedicated authentication layer generating identities based on SAN/issuer/serial and transmitting them through a protected mechanism.

## 9. Common Mistakes

### Mistake 1: Enabling `http.x509()` Even Though TLS Terminates at the Proxy

Symptom: NGINX logs a valid client certificate, yet Spring Security sees no certificate in the servlet request.

Cause: `http.x509()` does not read `X-Client-Cert` automatically. Fix: use trusted pre-auth headers **or** configure container integration (like SSLValve) to populate the request attribute from a trusted proxy.

### Mistake 2: Leaving the Backend Exposed Publicly

Symptom: an attacker calling the backend port directly with an identity header bypasses NGINX mTLS.

Fix: bind the right interface, firewall, deny-by-default network policies, authenticated internal transport; inspect all secondary routes.

### Mistake 3: Proxy Forwards Client Headers As-Is

Symptom: a forged `X-Verified-Client-DN` is trusted by the backend.

Fix: strip/overwrite incoming headers at the trust boundary; inspect NGINX config after file includes and verify actual packets reaching the backend in a lab.

### Mistake 4: Enabling HTTPS Only Between Client → Proxy

Symptom: the client uses mTLS securely, yet identity headers can be observed or tampered with on the internal network between proxy and app.

Fix: verify backend via HTTPS, prefer upstream mTLS and network ACLs when across hosts or trust boundaries. Never disable `proxy_ssl_verify` to bypass certificate errors.

### Mistake 5: Confusing “Valid Certificate” with “Authorized Client”

Symptom: every certificate from a trusted CA can access administrative APIs.

Fix: explicit identity mapping, provisioning, role/authority checks, and deny-by-default.

### Mistake 6: Forgetting Revoked or Rotated Certificates

Symptom: a previously valid certificate continues to be accepted despite revocation, or the application rejects a new service after rotation.

Fix: design CA trust/CRL/OCSP or equivalent policies, monitor expiry, maintain mapping update workflows, and rehearse rotation.

### Mistake 7: Two Inconsistent Proxy Layers

Symptom: real identity is lost, overwritten with the proxy's DN, or mixed with client headers.

Fix: diagram TLS hops, identity sources, and transforms at each layer; verify SAN, issuer, gateway policy, and header sanitization end-to-end.

### Mistake 8: Confusing 401, 403, and TLS Errors

- Invalid client certificates may be blocked **at the proxy or inside TLS**, so Spring never receives the request.
- An identity passing mTLS whose user is unprovisioned may be rejected by the pre-auth provider.
- An authenticated identity lacking permissions may receive **403** from Spring Security.
- Final HTTP status depends on entry points and exception handling, not solely on Java exception types.

## 10. Implementation and Testing Checklist

### Configuration

- [ ] mTLS termination endpoint is clearly defined, and trusted CAs are scoped strictly to intended clients.
- [ ] Chain, validity, clientAuth/EKU, and revocation are checked according to organizational policy.
- [ ] Proxy strips/overwrites all client-sent identity headers.
- [ ] System has only controlled ingress paths; backend is not publicly reachable.
- [ ] Proxy → backend channel is protected appropriately for the topology (isolated loopback or TLS/mTLS + ACLs).
- [ ] Identity source (SAN/DN/issuer/serial/internal ID) has clear normalization and uniqueness rules.
- [ ] Authority mapping follows least privilege and deny-by-default.
- [ ] Certificate issuance, rotation, revocation, and permission update processes are tested.
- [ ] Logging/auditing is minimal, never exposing PEMs/private keys/sensitive headers.

### Testing

- [ ] Valid cert + mapped identity → valid request succeeds.
- [ ] No cert / wrong CA / expired/revoked cert → no authenticated path into backend.
- [ ] Spoofed identity header from internet → proxy replaces or strips it without altering identity.
- [ ] Direct request to backend → blocked by network isolation.
- [ ] Valid cert with unmapped identity → rejected.
- [ ] Mapped identity without required role → denied at authorization.
- [ ] Upstream TLS wrong CA/hostname, or proxy/backend failure → fail closed.
- [ ] Certificate renewal/rotation and multiple proxy hops → accurate identity without loss or ambiguity.

**Testing solely with MockMvc or unit tests injecting headers is insufficient to claim security.** Those tests only verify Spring's mapping; you must run integration tests through a real proxy and verify firewalls/network paths, because TLS verification and header overwriting occur outside Java.

## 11. Self-Check Questions

1. Why might `http.x509()` fail to see the client certificate when NGINX terminates TLS?
2. Why does a header containing a PEM certificate fail to prove the client owns the private key?
3. If the proxy fails to overwrite `X-Verified-Client-DN`, what can an attacker do?
4. Is enabling HTTPS solely between client → proxy enough to protect identity between proxy and backend?
5. Why are identity allowlisting/provisioning and role-based authorization still needed after CA verification?
6. What can happen if two valid client certificates share the same subject DN?
7. Does an HTTP 403 status always mean the client certificate was rejected?
8. What test proves the backend cannot be called directly with a forged header?

Once you clearly separate where **private key possession is proven**, where **identity headers are generated**, and where **access decisions are made**, you can design and review X.509 flows behind a reverse proxy without misplacing trust.

## 12. Official Reference Documentation

- [Spring Security — X.509 Authentication (Servlet)](https://docs.spring.io/spring-security/reference/servlet/authentication/x509.html)
- [Spring Security — Pre-Authentication Scenarios](https://docs.spring.io/spring-security/reference/servlet/authentication/preauth.html)
- [Spring Security — RequestHeaderAuthenticationFilter API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/preauth/RequestHeaderAuthenticationFilter.html)
- [Spring Security — PreAuthenticatedAuthenticationProvider API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/preauth/PreAuthenticatedAuthenticationProvider.html)
- [NGINX — ngx_http_ssl_module: client certificate verification and variables](https://nginx.org/en/docs/http/ngx_http_ssl_module.html)
- [NGINX — Securing HTTP Traffic to Upstream Servers](https://docs.nginx.com/nginx/admin-guide/security-controls/securing-http-traffic-upstream)
- [Apache Tomcat — SSLValve documentation](https://tomcat.apache.org/tomcat-10.1-doc/config/valve.html)
