# X.509 Certificate Authentication and Mapping Certificates to Users

> **Module:** Spring Security – reactive  
> **Topic:** Advanced Authentication  
> **Task:** X.509 certificate authentication and mapping certificates to users.  
> **Example stack:** Java 17+, Spring WebFlux, Spring Security 6.5.11, Spring Boot 3.5.16, Reactor Netty, JUnit 5, and WebTestClient.

## 1. The Real-World Problem: A Certificate Does Not Automatically Grant Business Permissions

Suppose a reporting API is called by internal services/applications over HTTPS. Instead of requiring `Authorization: Basic ...` or `Authorization: Bearer ...`, the server requires clients to present an **X.509 certificate** during the TLS handshake (*mutual TLS*, abbreviated **mTLS**).

The server verifies that the client possesses the private key matching the certificate and that the certificate has a valid trust chain. Spring Security then reads certificate information from the TLS request, extracts a **principal identifier**, looks up the corresponding user/service record, and loads current roles/authorities.

Example:

```text
Client holds private key + client certificate
       |
       | TLS handshake: presents certificate, proves private key possession
       v
Reactor Netty HTTPS server (trusted CA, TLS policy, client-auth=need)
       |
       | TLS verifies certificate chain / validity / signature / EKU per policy
       | (failure here => handshake does not complete)
       v
Spring Security WebFlux x509 authentication
       |
       | X509PrincipalExtractor: SAN URI
       | spiffe://example.test/users/alice  --->  "alice"
       v
ReactivePreAuthenticatedAuthenticationManager
       |
       | ReactiveUserDetailsService: findByUsername("alice")
       | checks account enabled/locked/expired
       | loads ROLE_READER
       v
Authenticated principal + authorities in Reactor Context
       |
       | AuthorizationWebFilter: /api/reports requires ROLE_READER
       v
Controller / service processes report
```

**Three separate questions:**

1. **Is the certificate trustworthy and does the connecting party hold its private key?** → TLS/trust store/PKI.
2. **Which account does this valid certificate map to?** → `X509PrincipalExtractor` and subject/SAN policy.
3. **Is that account allowed to call this endpoint?** → user directory/account status/roles and Spring Security authorization.

A valid certificate from a trusted CA **does not automatically** carry `ROLE_ADMIN`. Trusting a CA means trusting **how certificates are issued under a policy**, while business permissions must be decided by the application.

### 1.1. Learning Outcomes

After this lesson, you will be able to:

- Explain mTLS/X.509, trust anchors, leaf certificates, issuer/subject, SAN, EKU, key usage, serial numbers, thumbprints, and private keys.
- Distinguish the TLS handshake from WebFlux authentication: TLS failures may produce no HTTP 401/403.
- Use `ServerHttpSecurity.x509(Customizer)`, `X509PrincipalExtractor`, `ReactivePreAuthenticatedAuthenticationManager`, and `ReactiveUserDetailsService`.
- Understand default CN mapping and how to tighten it with **Subject Alternative Name URIs**.
- Write a `SanUriPrincipalExtractor` enforcing namespace, syntax, ambiguity rejection, and failure on missing identity.
- Read certificates from **trusted TLS `SslInfo`**, never from untrusted `X-Client-Cert` HTTP headers.
- Configure Spring Boot `server.ssl.client-auth=need`, truststore/keystore, and generate **learning-only** certificates with OpenSSL/keytool.
- Distinguish certificate authentication from OAuth2 Resource Server JWT/opaque, Basic, and session auth.
- Write tests for mapping, account locks, roles, and HTTP security using test-only simulated TLS, understanding those tests **do not prove real TLS handshakes**.
- Operate CA rotation, certificate revocation, identity collisions, proxy termination, and observability without leaking private keys.

## 2. X.509, PKI, and Mutual TLS

### 2.1. What Does a Certificate Contain?

An X.509 certificate typically includes:

| Field | Meaning | Notes |
| --- | --- | --- |
| Subject | Identity asserted by the CA, e.g., `CN=alice,O=Example` | CN is not always the best identity |
| Issuer | CA that issued the certificate | Issuer name alone is insufficient: signature/chain must be verified |
| Serial Number | Certificate identifier under the issuer | Useful together with issuer for auditing/revocation |
| Validity | `notBefore` and `notAfter` | Synchronize clocks; reject expired certs |
| Subject Alternative Name (SAN) | DNS, email, URI, IP, etc. | Ideal for namespaced identities |
| Key Usage | Key permissions, e.g., `digitalSignature` | Must match TLS usage |
| Extended Key Usage (EKU) | E.g., `clientAuth` / `serverAuth` | Client certificates require `clientAuth` per policy |
| Basic Constraints | CA vs end-entity | Leaf certs must not have CA signing capability |
| Public key | Used in signature verification / proof of key possession | Public keys are not secret |
| Signature | CA's signature over certificate contents | Must chain to a trusted trust anchor |

**The client's private key is never inside the certificate.** During mTLS, the client proves possession of the private key through TLS cryptographic messages; the private key is never sent over the network. The server validates the certificate using trust anchors and TLS policy. If a client certificate is merely a PEM string sent in an HTTP body/header, **that is not mTLS**.

### 2.2. One-Way TLS and Two-Way TLS

**Standard HTTPS:** the client verifies the server certificate and secures the transport channel, while the server authenticates the client via tokens/sessions/passwords or leaves it anonymous.

**mTLS:** in addition to the above, the server requests a client certificate and verifies it, giving both sides cryptographic authentication. However, mTLS **does not by itself solve** role/tenant/resource authorization.

```text
Standard TLS:
  Browser/Client --- verify server certificate ---> HTTPS Server

mTLS:
  Client <--- verify server certificate --- HTTPS Server
  Client --- present trusted client cert -----> Server
  Client --- prove key possession -----------> Server
  Application --- cert identity -> app user ---> Authorization rules
```

### 2.3. server.ssl.client-auth: need, want, none

| Value | TLS Handshake | Effect |
| --- | --- | --- |
| `need` | Client certificate mandatory | Missing/untrusted certs typically fail before HTTP |
| `want` | Requested but optional | Suits mixed ports, though endpoints must verify identity |
| `none` | Client certificate not requested | Enabling Spring `.x509(...)` alone cannot create mTLS |

In the demo, `need` applies **to the entire HTTPS port**—including `/health`. `permitAll("/health")` allows anonymous access only at the Spring layer **after the TLS handshake succeeds**. With `client-auth=need`, a client presenting no certificate may receive **no HTTP status at all** because TLS rejects it before any request reaches WebFlux.

### 2.4. Truststore vs Keystore

- **Server keystore:** the server's own private key and server certificate/chain, proving the server's identity to clients.
- **Server truststore:** the list of CAs/public trust anchors accepted by the server to verify **client certificates**.
- **Client private key/cert:** the client's credential for completing mTLS.
- **Client CA trust:** where the client obtains trusted server CAs to verify the HTTPS server and prevent MITM.

Never dump a huge public root CA bundle into the server truststore for client-auth when you only intend to accept internal clients; **least trust** matters more than "more CAs means fewer errors".

## 3. X.509 Authentication Flow in Spring WebFlux

Spring Security reactive X.509 provides:

```java
@Bean
SecurityWebFilterChain springSecurity(ServerHttpSecurity http) {
    return http
        .x509(Customizer.withDefaults())
        .authorizeExchange(exchanges ->
            exchanges.anyExchange().authenticated())
        .build();
}
```

This snippet goes inside `@Configuration` and requires importing Spring WebFlux security classes. In Spring Security 6.5.11, the `x509(Customizer)` DSL matches the WebFlux API; avoid parameterless `http.x509()`, which was deprecated in 6.x.

Once a valid client certificate has been accepted by TLS and exposed via `ServerHttpRequest.getSslInfo().getPeerCertificates()`, Spring's X.509 authentication filter:

1. Receives the client certificate chain from the request's TLS info.
2. Uses `X509PrincipalExtractor` to extract a principal representing the certificate.
3. Passes the principal as a pre-authenticated authentication request.
4. Calls the configured `ReactiveAuthenticationManager`.
5. If the account is valid, stores the authenticated principal and authorities in the Spring Security context.
6. `authorizeExchange` rules decide whether the endpoint may be accessed.

**Pre-authenticated** means a trusted TLS/upstream layer **already cryptographically verified the credential**, and Spring Security then maps the principal and checks account status and roles. It does not mean the application skips account-status checks or lets every certificate become admin.

### 3.1. Core APIs

| API | Package | Role |
| --- | --- | --- |
| `ServerHttpSecurity` | `org.springframework.security.config.web.server` | Reactive security DSL |
| `SecurityWebFilterChain` | `org.springframework.security.web.server` | WebFlux filter chain |
| `X509PrincipalExtractor` | `org.springframework.security.web.authentication.preauth.x509` | `Object extractPrincipal(X509Certificate)` |
| `SubjectX500PrincipalExtractor` | Same package | Extracts `CN` or `emailAddress` per the newer default design |
| `ReactivePreAuthenticatedAuthenticationManager` | `org.springframework.security.web.server.authentication` | Looks up user, checks locked/disabled/expired, loads authorities |
| `PreAuthenticatedAuthenticationToken` | `org.springframework.security.web.authentication.preauth` | Authentication credential already verified by an upstream layer |
| `ReactiveUserDetailsService` | `org.springframework.security.core.userdetails` | Finds `UserDetails` by principal |
| `MapReactiveUserDetailsService` | Same package | In-memory user store for the demo |
| `ReactiveSecurityContextHolder` | `org.springframework.security.core.context` | Reads authentication from Reactor Context |
| `SslInfo` | `org.springframework.http.server.reactive` | TLS session ID and peer X.509 certificate chain |

### 3.2. Why Not Read Certificates from Headers?

An HTTP request might carry:

```http
X-Client-Cert: CN=admin
X-SSL-Client-DN: CN=admin
X-User: admin
```

Those are **client-supplied data** and provide zero proof that the client holds a private key. Never use such headers to grant `ROLE_ADMIN`. If TLS termination happens at an API gateway, the backend may need a **separately protected identity-forwarding contract**: the gateway must verify the certificate itself, strip spoofed client headers, sign/bind metadata if needed, use separate gateway→backend mTLS, and trust traffic only from the gateway via network policy. Enabling `.x509(...)` on the backend will not resurrect the original client's TLS peer certificate once a gateway terminates TLS upstream.

## 4. Mapping Certificates to Users

Verifying the **certificate** and mapping the **application principal** are two distinct steps. A certificate might contain `CN=alice` or SAN URI `spiffe://example.test/users/alice`, yet the application must decide which values are accepted and which account they map to.

### 4.1. Default Mapping by CN

According to Spring Security reactive documentation, the default principal extractor is `SubjectX500PrincipalExtractor`, extracting `CN` from the X.500 Subject; the default authentication manager is `ReactivePreAuthenticatedAuthenticationManager`, checking that the account exists and is not locked, disabled, or expired.

Conceptual example:

```text
Client certificate Subject: CN=alice,O=Example
               |
               v
SubjectX500PrincipalExtractor
               |
               v
principal "alice"
               |
               v
ReactiveUserDetailsService.findByUsername("alice")
               |
               v
UserDetails(alice, ROLE_READER)
```

If users are identified by email in the distinguished name, the extractor offers `setExtractPrincipalNameFromEmail(true)`. Use it only when **certificate issuance policy** guarantees emails cannot be spoofed or duplicated; never treat an email from an arbitrary issuer as a global identity.

### 4.2. CN Security and CVE-2026-47838

In June 2026, Spring disclosed **CVE-2026-47838**, concerning how the legacy `SubjectDnX509PrincipalExtractor` parsed certain unusual `CN` values, risking mapping to an incorrect username. Spring Security **6.5.0–6.5.10** was affected, with the OSS fix released in **6.5.11**. `SubjectDnX509PrincipalExtractor` is deprecated; `SubjectX500PrincipalExtractor` is recommended instead.

**Security lesson:** Never hand-parse `certificate.getSubjectDN().getName()` with a regex like `CN=(.*?)` to determine identity. Distinguished Names involve escaping, RDN ordering, multi-valued RDNs, and unusual encodings. Use the standard `X500Principal` parser or, better yet, an explicit SAN/CA policy identity.

In the runnable example below, we choose a **namespaced SAN URI** to demonstrate a stricter identity contract. Not every system requires a SAN URI; what matters is that the identity comes from a **controlled CA** with unambiguous mapping.

### 4.3. Mapping with Subject Alternative Name URIs

A client certificate issued by an internal CA carries extensions:

```text
Subject: CN=Alice Laptop,O=Example
X509v3 Subject Alternative Name:
    URI:spiffe://example.test/users/alice
Extended Key Usage:
    TLS Web Client Authentication
```

Application mapping:

```text
SAN URI spiffe://example.test/users/alice
   |
   +-- scheme = spiffe
   +-- trust domain = example.test
   +-- path = /users/alice
   +-- query/fragment/userinfo/port not accepted
   +-- username pattern = [a-z][a-z0-9-]{0,31}
   |
   v
username = alice -> ReactiveUserDetailsService -> UserDetails
```

**Note:** `spiffe://...` here is a **URI naming convention for the example**, not a claim that the app implements the full SPIFFE Workload API, SPIRE, or workload attestation. Choose an appropriate trust domain and certificate issuance policy. If a CA can arbitrarily issue `/users/admin` to any customer, mapping is dangerous **even with flawless parsing**; protect enrollment and certificate issuance.

### 4.4. Mapping Options in Production

| Mapping Type | Strengths | What Must Be Controlled |
| --- | --- | --- |
| CN in X.500 Subject | Easy to start, built into Spring | Safe RDN parser, unique CNs, CA issuance |
| SAN RFC822 email | Easy directory matching | Mutable/aliased emails, issuer, and tenant |
| Namespaced SAN URI | Explicit identity, supports workload/service IDs | Trust-domain allowlist, path format, uniqueness |
| Serial + Issuer | Certificate-specific mapping, audit/revocation | Certificate rotation must update mapping |
| Public-key fingerprint/SPKI pin | Pins a specific key | Key rotation, pin management |
| SAN URI + tenant + issuer | Good for multi-tenant systems | Needs authoritative registry/lookup |
| Self-asserted `X-Client-Cert` header | **Untrustworthy** | Never use as TLS proof |

**Never** hardcode roles from a CN name, e.g., `if (cn.equals("admin")) ROLE_ADMIN`. Roles must come from a **governed user directory**, and certificate issuance policy must prevent SAN/CN spoofing.

## 5. Server-Level TLS Configuration Before Enabling x509()

Spring Security `.x509(...)` does not create a CA, turn on HTTPS by itself, or replace Netty's TLS handshake. The first critical piece is Spring Boot SSL configuration:

```yaml
server:
  port: 8443
  ssl:
    enabled: true
    key-store: file:certs/server.p12
    key-store-type: PKCS12
    key-store-password: ${SERVER_KEYSTORE_PASSWORD:localpass}
    trust-store: file:certs/trust.p12
    trust-store-type: PKCS12
    trust-store-password: ${SERVER_TRUSTSTORE_PASSWORD:localpass}
    client-auth: need
```

In this demo, `localpass` is a password **for local key/truststores only**. It is **not** suitable for production; manage keystore passwords and private keys via secret managers, file permissions, and rotation. `file:certs/...` is a path **relative to the Maven working directory**, and these files are generated via the OpenSSL/keytool commands in Section 12.

**Do not enable** `server.ssl.client-auth: need` without a truststore recognizing valid client CAs—Netty may trust no certificates or fail to start depending on configuration.

### 5.1. Certificate Chains Are Checked at TLS, Account Status at Spring

| Step | If It Fails | Outcome |
| --- | --- | --- |
| Invalid server private key / certificate | Cannot serve HTTPS | Server startup fails or TLS handshake fails |
| Client sends no cert under `need` | TLS client auth fails | Usually **no HTTP response** |
| Cert signed by CA not in truststore | TLS trust fails | Usually no HTTP response |
| Expired cert, wrong key usage, bad chain | TLS policy rejects (provider-dependent) | Never reaches Spring controller |
| Cert passes TLS, SAN violates app policy | Spring authentication rejects | Request denied; HTTP status per entry point |
| Valid SAN, account does not exist | Spring pre-auth lookup rejects | HTTP authentication failure |
| Account locked/disabled | Manager denies | No access granted |
| Valid account lacking role | `AuthorizationWebFilter` denies | Usually HTTP 403 |
| Valid account and right role | Controller handles | Usually HTTP 200 |

Behind a reverse proxy, failures may be translated into a proxy error page/status. Never mechanically assume "mTLS always returns HTTP 401 when no cert is sent": the handshake **can fail before HTTP even starts**.

### 5.2. When to Use client-auth=want?

`want` permits TLS connections without a certificate, useful when sharing a port with public endpoints or other auth mechanisms. However, if sensitive routes require X.509, you must configure the Spring authorization chain so it **never** falls back unexpectedly to anonymous or Basic. When the entire port serves mTLS only, `need` is simpler to audit.

## 6. Java 17+ Project: WebFlux X.509 + SAN URI + User Lookup

The project uses **Spring Boot 3.5.16** and pins **Spring Security 6.5.11** in the BOM to avoid 6.5 releases affected by the CN parser CVE. Spring Boot 3.5.x has reached end of OSS support per Spring; use this baseline to learn the 6.5 APIs, and choose a currently supported Boot/Security branch with migration tests for new production deployments.

Project layout:

```text
reactive-x509-mtls/
├── pom.xml
├── certs/                         # Generated locally with OpenSSL/keytool; never commit keys
│   ├── ca.crt
│   ├── ca.key
│   ├── server.p12
│   ├── trust.p12
│   ├── alice.crt / alice.key
│   ├── admin.crt / admin.key
│   ├── locked.crt / locked.key
│   └── stranger.crt / stranger.key
└── src/
    ├── main/
    │   ├── java/demo/x509/
    │   │   ├── Application.java
    │   │   ├── SanUriPrincipalExtractor.java
    │   │   ├── SecurityConfiguration.java
    │   │   └── ApiController.java
    │   └── resources/application.yml
    └── test/java/demo/x509/
        ├── SanUriPrincipalExtractorTests.java
        ├── ReactivePreAuthManagerTests.java
        └── X509WebFluxTests.java
```

The project separates **three test layers**: parser unit tests, reactive account manager tests, and WebFlux security tests with peer certificates **simulated by a test-only WebFilter**. Real mTLS testing with `curl` in Section 13 is a separate step; unit/mock tests neither perform TLS handshakes nor validate truststores.

### 6.1. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>reactive-x509-mtls</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <!-- Uses version fixing CVE-2026-47838. -->
        <spring-security.version>6.5.11</spring-security.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

**No need** for `spring-boot-starter-oauth2-resource-server` in this pure client-certificate authentication example. If an API uses both JWT/opaque Bearer and X.509, that is a multi-mechanism design requiring route/security chain partitioning, not something `.x509(...)` creates automatically.

**Check dependency versions:**

```bash
mvn dependency:tree -Dincludes=org.springframework.security
```

Verify that `spring-security-web` and all Spring Security modules consistently resolve to **6.5.11**, without mixing 6.5.10 and 6.5.11. Overriding the property in the example follows Spring Security's documented way to override Boot-managed Maven dependency versions; never assume a safe upgrade without checking the tree and running regression tests.

### 6.2. src/main/resources/application.yml

```yaml
server:
  port: 8443
  ssl:
    enabled: true
    key-store: file:certs/server.p12
    key-store-password: ${SERVER_KEYSTORE_PASSWORD:localpass}
    key-store-type: PKCS12
    trust-store: file:certs/trust.p12
    trust-store-password: ${SERVER_TRUSTSTORE_PASSWORD:localpass}
    trust-store-type: PKCS12
    client-auth: need
```

Do not use `https://...` in Boot's key-store path because the keystore lives on the local filesystem here. The server reads `certs/server.p12` and `certs/trust.p12` created in Section 12; without these two files, starting the real HTTPS app will fail, **which is the right behavior**.

### 6.3. src/main/java/demo/x509/Application.java

```java
package demo.x509;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
```

## 7. Custom X509PrincipalExtractor Using SAN URI

Instead of parsing a `CN=...` string, the extractor receives the `X509Certificate` obtained by Spring Security from the trusted transport. It accepts only **one** SAN of type **URI (GeneralName type 6)** belonging to trust domain `example.test` with path `/users/{username}`.

### 7.1. src/main/java/demo/x509/SanUriPrincipalExtractor.java

```java
package demo.x509;

import java.net.URI;
import java.security.cert.CertificateParsingException;
import java.security.cert.X509Certificate;
import java.util.Collection;
import java.util.List;

import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.web.authentication.preauth.x509.X509PrincipalExtractor;

public final class SanUriPrincipalExtractor
        implements X509PrincipalExtractor {

    private static final String SCHEME = "spiffe";
    private static final String TRUST_DOMAIN = "example.test";
    private static final String PATH_PREFIX = "/users/";

    @Override
    public Object extractPrincipal(X509Certificate certificate) {
        try {
            Collection<List<?>> sans =
                certificate.getSubjectAlternativeNames();

            if (sans == null || sans.isEmpty()) {
                throw new BadCredentialsException(
                    "Client certificate has no subjectAltName");
            }

            String username = null;
            for (List<?> entry : sans) {
                if (entry.size() < 2 ||
                        !(entry.get(0) instanceof Integer tag) ||
                        tag != 6 ||
                        !(entry.get(1) instanceof String rawUri)) {
                    continue;
                }

                URI uri = URI.create(rawUri);
                String path = uri.getPath();

                if (!SCHEME.equals(uri.getScheme()) ||
                        !TRUST_DOMAIN.equals(uri.getHost()) ||
                        uri.getPort() != -1 ||
                        uri.getUserInfo() != null ||
                        uri.getRawQuery() != null ||
                        uri.getRawFragment() != null ||
                        path == null ||
                        !path.startsWith(PATH_PREFIX)) {
                    continue;
                }

                String candidate = path.substring(PATH_PREFIX.length());
                // Prevent path traversal, extra slashes, empty usernames, or odd characters.
                if (!candidate.matches("[a-z][a-z0-9-]{0,31}")) {
                    throw new BadCredentialsException(
                        "Invalid certificate user identifier");
                }

                // Two SANs matching the namespace => ambiguous identity.
                if (username != null) {
                    throw new BadCredentialsException(
                        "Ambiguous certificate user identifiers");
                }
                username = candidate;
            }

            if (username == null) {
                throw new BadCredentialsException(
                    "No trusted user URI in certificate");
            }
            return username;
        }
        catch (CertificateParsingException | IllegalArgumentException ex) {
            throw new BadCredentialsException(
                "Invalid certificate subjectAltName", ex);
        }
    }
}
```

**Intentional properties:**

- Does not run regex on DN or trust CN as a user ID.
- Accepts only URI SANs, never falling back unexpectedly to DNS SAN or email SAN.
- Accepts only scheme `spiffe`, trust domain `example.test`, path `/users/{username}`; no query/fragment/userInfo/port.
- Accepts only lowercase ASCII usernames with no slashes or dots, preventing path confusion/normalization issues.
- If **no** valid SAN exists or **two** matching SANs exist, rejects instead of guessing.
- Never assigns roles inside the parser; the parser **only selects a username**. Roles come from the user directory.
- Certificate parsing errors throw `BadCredentialsException`.

In multi-tenant projects, include tenant/issuer in the identity key and restrict trust domains/CAs per tenant. A clean URI namespace **does not replace** PKI issuance controls: the CA must ensure only Alice receives `spiffe://example.test/users/alice`.

### 7.2. Sample Inputs and Expected Mapping

| SAN URI in Certificate | Result |
| --- | --- |
| `spiffe://example.test/users/alice` | `alice` |
| `spiffe://example.test/users/admin` | `admin` (still looks up account roles) |
| `spiffe://other.test/users/alice` | Reject: wrong trust domain |
| `http://example.test/users/alice` | Reject: wrong scheme |
| `spiffe://example.test/users/alice/extra` | Reject: fails username pattern |
| `spiffe://example.test/users/ALICE` | Reject: fails username pattern |
| `spiffe://example.test/users/alice?role=ADMIN` | Reject: query not allowed |
| Two URI SANs in same namespace | Reject: non-unique principal |
| CN only, no SAN | Reject under project policy |
| One emailAddr SAN and no URI SAN | Reject under project policy |

In production, URI normalization/punycode, PKI name constraints, SAN extensions, and library versions require explicit threat modeling; do not treat this table as a substitute for a PKI audit.

## 8. Reactive User Lookup and Security Configuration

### 8.1. src/main/java/demo/x509/SecurityConfiguration.java

```java
package demo.x509;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.ReactivePreAuthenticatedAuthenticationManager;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfiguration {

    @Bean
    ReactiveUserDetailsService users() {
        // Password field only completes UserDetails; not used for
        // X.509 pre-authentication credential verification.
        UserDetails alice = User.withUsername("alice")
            .password("{noop}unused-x509-only")
            .roles("READER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password("{noop}unused-x509-only")
            .roles("READER", "ADMIN")
            .build();

        UserDetails locked = User.withUsername("locked")
            .password("{noop}unused-x509-only")
            .roles("READER")
            .accountLocked(true)
            .build();

        return new MapReactiveUserDetailsService(alice, admin, locked);
    }

    @Bean
    ReactiveAuthenticationManager x509AuthenticationManager(
            ReactiveUserDetailsService users) {
        return new ReactivePreAuthenticatedAuthenticationManager(users);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            ReactiveAuthenticationManager x509AuthenticationManager) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/health").permitAll()
                .pathMatchers("/api/admin").hasRole("ADMIN")
                .pathMatchers("/api/reports").hasRole("READER")
                .pathMatchers("/api/me").authenticated()
                .anyExchange().denyAll())
            .x509(x509 -> x509
                .principalExtractor(new SanUriPrincipalExtractor())
                .authenticationManager(x509AuthenticationManager))
            .httpBasic(basic -> basic.disable())
            .formLogin(form -> form.disable())
            .build();
    }
}
```

**Points to note:**

1. `users()` is a **`ReactiveUserDetailsService`** (exact class name: `ReactiveUserDetailsService`) backed by an in-memory directory; real apps need R2DBC/LDAP or a directory service with an appropriate SLA.
2. `ReactivePreAuthenticatedAuthenticationManager(users)` checks user existence and account status. It skips password comparison because **TLS already verified the client certificate**. The `{noop}unused-x509-only` password is purely a dummy field because `UserDetails` requires a password; **do not** enable Basic/form login where it could become a valid credential.
3. `.x509(x509 -> ...)` configures the extractor and manager **explicitly**. Never build a production `WebFilter` that converts an HTTP header into a trusted certificate.
4. `hasRole("READER")` maps to the `ROLE_READER` authority convention; `hasRole("ADMIN")` maps to `ROLE_ADMIN`.
5. `admin` holds both READER and ADMIN, while `alice` holds only READER; `locked` has a role yet the manager must reject it because the account is locked.
6. `httpBasic` and `formLogin` are disabled so there is **no password fallback** in this cert-only demo. If the same server also uses OAuth2/JWT, design multi-chain routing and test for no bypasses.
7. Do not disable CSRF arbitrarily: browsers can present client certificates automatically per browser settings; on state-changing browser endpoints, **the CSRF threat model still applies**. The demo has GETs only, so it keeps default CSRF behavior.

**Important reminder:** X.509 does not automatically mean "every certificate from a trusted CA is permitted". If user `stranger` holds a valid certificate signed by the demo CA but **does not exist** in `MapReactiveUserDetailsService`, `ReactivePreAuthenticatedAuthenticationManager` rejects it.

### 8.2. Role of Pre-Authentication and Account Status

Assuming the client cert passed TLS:

```text
cert SAN alice  --> "alice"  --> user found, enabled --> ROLE_READER
cert SAN admin  --> "admin"  --> user found, enabled --> ROLE_READER + ROLE_ADMIN
cert SAN locked --> "locked" --> user found, locked  --> authentication rejected
cert SAN guest  --> "guest"  --> user missing        --> authentication rejected
```

With a real database, use non-blocking `ReactiveUserDetailsService.findByUsername`; you can strengthen this by checking the certificate serial/issuer/fingerprint bound to the account and the certificate's revocation state. If you map solely by username, a CA issuing a new cert with the same SAN can authenticate as that same account; that policy must be explicitly defined and audited, never accidental.

### 8.3. Default CN Extractor with Standard Manager for Comparison

If your internal CA issues identities via CN and you have audited the issuance policy, Spring Security 6.5.11 supports:

```java
// Snippet replacing .x509(...) in the project if choosing a CN policy.
SubjectX500PrincipalExtractor extractor =
    new SubjectX500PrincipalExtractor();

http.x509(x509 -> x509
    .principalExtractor(extractor)
    .authenticationManager(x509AuthenticationManager));
```

Import `SubjectX500PrincipalExtractor` from `org.springframework.security.web.authentication.preauth.x509`. Never use the deprecated `SubjectDnX509PrincipalExtractor` or hand-rolled regex on DNs. Never chain two extractors as "if SAN fails, fall back to CN" unless you have an explicit identity contract and tests preventing a weaker bypass path.

## 9. API Controller: Reading the Principal from Reactor Context

### 9.1. src/main/java/demo/x509/ApiController.java

```java
package demo.x509;

import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    @GetMapping("/health")
    public Mono<String> health() {
        return Mono.just("OK");
    }

    @GetMapping("/api/me")
    public Mono<String> me() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(authentication ->
                "user=" + authentication.getName());
    }

    @GetMapping("/api/reports")
    public Mono<String> reports() {
        return Mono.just("reports OK");
    }

    @GetMapping("/api/admin")
    public Mono<String> admin() {
        return Mono.just("admin OK");
    }
}
```

`/api/me` does not read `?user=alice` or `X-User: alice`; it reads only the `Authentication` populated by the filter from **certificate identity + directory lookup**. Never use Servlet's ThreadLocal `SecurityContext` in a reactive service. Spring WebFlux subscribes to the `Mono` within the request pipeline.

If you need to return issuer, subject, serial, or thumbprint for auditing, extract them in a controlled component and redact appropriately; **never** return the entire client certificate chain or private key in an HTTP body.

## 10. Unit Testing the Principal Extractor

These are Java 17 tests verifying the **SAN URI mapping algorithm**. They use Mockito to stub `X509Certificate.getSubjectAlternativeNames()`; they do not sign certs or verify TLS chains.

### 10.1. src/test/java/demo/x509/SanUriPrincipalExtractorTests.java

```java
package demo.x509;

import java.security.cert.CertificateParsingException;
import java.security.cert.X509Certificate;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.BadCredentialsException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class SanUriPrincipalExtractorTests {

    private final SanUriPrincipalExtractor extractor =
        new SanUriPrincipalExtractor();

    private X509Certificate certificate(String... uris)
            throws CertificateParsingException {
        X509Certificate cert = mock(X509Certificate.class);
        List<List<?>> sans = java.util.Arrays.stream(uris)
            .map(uri -> (List<?>) List.of(6, uri))
            .toList();
        when(cert.getSubjectAlternativeNames()).thenReturn(sans);
        return cert;
    }

    @Test
    void validAliceUriMapsToAlice() throws Exception {
        Object principal = extractor.extractPrincipal(
            certificate("spiffe://example.test/users/alice"));
        assertEquals("alice", principal);
    }

    @Test
    void validAdminUriMapsToAdminWithoutGrantingRole() throws Exception {
        Object principal = extractor.extractPrincipal(
            certificate("spiffe://example.test/users/admin"));
        assertEquals("admin", principal);
        // Extractor ONLY returns username; it does not decide ROLE_ADMIN.
    }

    @Test
    void differentTrustDomainIsRejected() throws Exception {
        assertThrows(BadCredentialsException.class, () ->
            extractor.extractPrincipal(
                certificate("spiffe://attacker.test/users/alice")));
    }

    @Test
    void wrongSchemeIsRejected() throws Exception {
        assertThrows(BadCredentialsException.class, () ->
            extractor.extractPrincipal(
                certificate("https://example.test/users/alice")));
    }

    @Test
    void extraPathIsRejected() throws Exception {
        assertThrows(BadCredentialsException.class, () ->
            extractor.extractPrincipal(
                certificate("spiffe://example.test/users/alice/admin")));
    }

    @Test
    void queryOrFragmentIsRejected() throws Exception {
        assertThrows(BadCredentialsException.class, () ->
            extractor.extractPrincipal(
                certificate("spiffe://example.test/users/alice?role=admin")));
    }

    @Test
    void ambiguousTrustedUrisAreRejected() throws Exception {
        assertThrows(BadCredentialsException.class, () ->
            extractor.extractPrincipal(certificate(
                "spiffe://example.test/users/alice",
                "spiffe://example.test/users/admin")));
    }

    @Test
    void missingSanIsRejected() throws Exception {
        assertThrows(BadCredentialsException.class, () ->
            extractor.extractPrincipal(certificate()));
    }

    @Test
    void uppercaseUsernameIsRejected() throws Exception {
        assertThrows(BadCredentialsException.class, () ->
            extractor.extractPrincipal(
                certificate("spiffe://example.test/users/ALICE")));
    }
}
```

There are **9 unit tests** for the parser (valid case, wrong scheme/domain/path/query, dual-identity SAN, missing SAN, uppercase). Even when they pass, you have **not proven** that mTLS is active or that certificates are issued by a trusted CA; these test only a function receiving a caller-supplied certificate object.

## 11. Testing ReactivePreAuthenticatedAuthenticationManager

`ReactivePreAuthenticatedAuthenticationManager` is the **application** layer after TLS: it accepts a pre-authentication token, looks up the user, and checks account status. The tests below intentionally feed in a pre-built `PreAuthenticatedAuthenticationToken`; that **does not prove** network credentials are secure—that responsibility belongs to TLS.

### 11.1. src/test/java/demo/x509/ReactivePreAuthManagerTests.java

```java
package demo.x509;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationToken;
import org.springframework.security.web.server.authentication.ReactivePreAuthenticatedAuthenticationManager;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ReactivePreAuthManagerTests {

    private final ReactiveAuthenticationManager manager =
        new ReactivePreAuthenticatedAuthenticationManager(
            new MapReactiveUserDetailsService(
                User.withUsername("alice")
                    .password("{noop}unused")
                    .roles("READER").build(),
                User.withUsername("admin")
                    .password("{noop}unused")
                    .roles("READER", "ADMIN").build(),
                User.withUsername("locked")
                    .password("{noop}unused")
                    .roles("READER")
                    .accountLocked(true).build()));

    private static Authentication token(String username) {
        // For manager unit tests only: assumes TLS already verified the certificate.
        return new PreAuthenticatedAuthenticationToken(
            username, "tls-verified-integration-boundary");
    }

    @Test
    void aliceIsResolvedWithReaderRole() {
        StepVerifier.create(manager.authenticate(token("alice")))
            .assertNext(auth -> {
                assertTrue(auth.isAuthenticated());
                assertEquals("alice", auth.getName());
                assertTrue(auth.getAuthorities().stream()
                    .anyMatch(a -> a.getAuthority().equals("ROLE_READER")));
            })
            .verifyComplete();
    }

    @Test
    void adminReceivesAdminAndReaderRoles() {
        StepVerifier.create(manager.authenticate(token("admin")))
            .assertNext(auth -> {
                assertTrue(auth.getAuthorities().stream()
                    .anyMatch(a -> a.getAuthority().equals("ROLE_ADMIN")));
                assertTrue(auth.getAuthorities().stream()
                    .anyMatch(a -> a.getAuthority().equals("ROLE_READER")));
            })
            .verifyComplete();
    }

    @Test
    void unknownSubjectDoesNotAuthenticate() {
        StepVerifier.create(manager.authenticate(token("stranger")))
            .expectError()
            .verify();
    }

    @Test
    void lockedSubjectDoesNotAuthenticate() {
        StepVerifier.create(manager.authenticate(token("locked")))
            .expectError()
            .verify();
    }
}
```

There are **4 tests**. `UserDetailsService` looks up the username supplied by pre-authentication, returning current roles or rejecting disallowed accounts. Do not confuse this unit test with an endpoint allowing clients to POST `username=admin` and treating it as pre-authenticated.

**Note on imports:** `org.springframework.security.authentication.AuthenticationManager` is included to illustrate the imperative/reactive distinction, **is unused in the test file**, and can be removed when cleaning imports. `ReactiveAuthenticationManager` is the class actually used.

## 12. Testing the WebFlux X.509 Filter Without Starting a TLS Server

In Spring Framework 6.2, `WebTestClient.bindToApplicationContext(...)` uses a mock server that does not perform a real TLS handshake. To test the X.509 filter, we **simulate a trusted `SslInfo` strictly inside the test context** and exercise the security chain. The test below defines a `WebFilter` existing only in `src/test`; it reads a test-only `X-Test-Peer` header and attaches a fake `SslInfo` to the mock request.

**Mandatory warning:** This is **not a production pattern**. Putting such a test filter into `src/main` would let attackers set that header to impersonate any user. Over a real network, peer certificates **must come exclusively from a transport-verified mTLS handshake**, never from a user-provided HTTP header. Real network testing in Section 13 uses OpenSSL and `curl`.

### 12.1. src/test/java/demo/x509/X509WebFluxTests.java

```java
package demo.x509;

import java.security.cert.CertificateParsingException;
import java.security.cert.X509Certificate;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.http.server.reactive.SslInfo;
import org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.server.WebFilter;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest(properties = {"server.ssl.enabled=false",
    "server.ssl.client-auth=none"})
@Import(X509WebFluxTests.TestTlsTransportConfiguration.class)
class X509WebFluxTests {

    @TestConfiguration
    static class TestTlsTransportConfiguration {

        @Bean
        @Order(Ordered.HIGHEST_PRECEDENCE)
        WebFilter testOnlyTlsPeerFilter() {
            return (exchange, chain) -> {
                String identity = exchange.getRequest().getHeaders()
                    .getFirst("X-Test-Peer");
                if (identity == null) {
                    return chain.filter(exchange);
                }

                X509Certificate cert = certificateForTest(identity);
                SslInfo simulatedTls = new SslInfo() {
                    @Override
                    public String getSessionId() {
                        return "test-session-only";
                    }

                    @Override
                    public X509Certificate[] getPeerCertificates() {
                        return new X509Certificate[] {cert};
                    }
                };

                ServerHttpRequest request = exchange.getRequest()
                    .mutate().sslInfo(simulatedTls).build();
                return chain.filter(exchange.mutate()
                    .request(request).build());
            };
        }

        private static X509Certificate certificateForTest(
                String identity) {
            try {
                X509Certificate cert = mock(X509Certificate.class);
                if ("missing-san".equals(identity)) {
                    when(cert.getSubjectAlternativeNames())
                        .thenReturn(List.of());
                }
                else {
                    // This header ONLY exists in the test fake TLS transport.
                    String uri = "spiffe://example.test/users/" + identity;
                    when(cert.getSubjectAlternativeNames())
                        .thenReturn(List.<List<?>>of(List.of(6, uri)));
                }
                return cert;
            }
            catch (CertificateParsingException ex) {
                throw new IllegalStateException(ex);
            }
        }
    }

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient
            .bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    private WebTestClient.ResponseSpec get(
            String path, String peer) {
        return client.get().uri(path)
            .headers(headers -> {
                if (peer != null) {
                    headers.set("X-Test-Peer", peer);
                }
            })
            .exchange();
    }

    @Test
    void healthIsPublicInMockTransportWithoutCertificate() {
        get("/health", null)
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("OK");
    }

    @Test
    void protectedEndpointWithoutPeerCertificateIsDenied() {
        get("/api/me", null)
            .expectStatus().is4xxClientError();
    }

    @Test
    void aliceIsMappedToAuthenticatedUser() {
        get("/api/me", "alice")
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("user=alice");
    }

    @Test
    void aliceCanReadReports() {
        get("/api/reports", "alice")
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("reports OK");
    }

    @Test
    void aliceCannotUseAdminRoute() {
        get("/api/admin", "alice")
            .expectStatus().isForbidden();
    }

    @Test
    void adminCanUseAdminRoute() {
        get("/api/admin", "admin")
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("admin OK");
    }

    @Test
    void adminCanAlsoReadReports() {
        get("/api/reports", "admin")
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("reports OK");
    }

    @Test
    void unknownDirectoryIdentityIsDenied() {
        get("/api/me", "stranger")
            .expectStatus().is4xxClientError();
    }

    @Test
    void lockedDirectoryIdentityIsDenied() {
        get("/api/me", "locked")
            .expectStatus().is4xxClientError();
    }

    @Test
    void missingSanIdentityIsDenied() {
        get("/api/me", "missing-san")
            .expectStatus().is4xxClientError();
    }

    @Test
    void invalidSanIdentityIsDenied() {
        get("/api/me", "ALICE")
            .expectStatus().is4xxClientError();
    }

    @Test
    void spoofedOrdinaryIdentityHeaderDoesNotWork() {
        client.get().uri("/api/me")
            .header("X-User", "admin")
            .exchange()
            .expectStatus().is4xxClientError();
    }
}
```

There are **12 WebTestClient tests**. Several assert `is4xxClientError()` instead of forcing every invalid cert to HTTP 401: Spring Security entry points/chains may return different 4xx codes, and this test **performs no real TLS handshake**. With `client-auth=need` on a real server, requests lacking a cert or trusted CA **can be rejected before HTTP**, so `curl` sees a TLS alert rather than a 401 response.

**What has been tested and what has not:**

| Test Level | Can Prove | Cannot Prove |
| --- | --- | --- |
| `SanUriPrincipalExtractorTests` | SAN parsing, ambiguity, trust namespace | Certificate chain, private key possession |
| `ReactivePreAuthManagerTests` | User lookup/roles/account lock | Caller actually holds a trusted certificate |
| `X509WebFluxTests` | Filter reads mocked peer certificate, maps user, authorizes routes | TLS handshake, OpenSSL CA, truststore, cert revocation |
| `curl --cert --key --cacert` real server | TLS client cert + SSL trust + app user policy | Automatic coverage of all CRL/OCSP/PKI issuance policies |

**Total: 25 tests:** 9 extractor + 4 manager + 12 WebFlux. That is the count of `@Test` methods in the example, not a claim that Maven was executed.

## 13. Generating Local Certificates and Testing mTLS with curl

These commands target a **Linux/macOS shell or Git Bash** with OpenSSL and JDK `keytool` installed. They create a **self-signed CA lasting only a few days**, so **never** bring demo keys or CAs into production. Never commit `certs/*.key`, `certs/*.p12`, `certs/*.csr`, or `certs/ca.key`.

### 13.1. Creating the Demo Certificate Authority

```bash
mkdir -p certs

openssl req -x509 -newkey rsa:3072 -sha256 -nodes -days 7 \
  -subj "/CN=Local Demo CA" \
  -keyout certs/ca.key -out certs/ca.crt \
  -addext "basicConstraints=critical,CA:TRUE" \
  -addext "keyUsage=critical,keyCertSign,cRLSign"
```

Create a **learning-only** CA. The CA private key `ca.key` must be strongly protected: anyone holding this key can sign a new certificate with SAN `/users/admin`, and if the server trusts that CA, they can mint a client identity that Spring maps to admin. In production, use a controlled CA issuance workflow with CA keys in an HSM/offline and certificate issuance auditing.

### 13.2. Creating a Server Certificate with DNS SAN localhost

```bash
openssl req -newkey rsa:3072 -nodes \
  -keyout certs/server.key -out certs/server.csr \
  -subj "/CN=localhost"

cat > certs/server.ext <<'EOF'
basicConstraints=critical,CA:FALSE
subjectAltName=DNS:localhost,IP:127.0.0.1
extendedKeyUsage=serverAuth
keyUsage=digitalSignature,keyEncipherment
EOF

openssl x509 -req -in certs/server.csr \
  -CA certs/ca.crt -CAkey certs/ca.key -CAcreateserial \
  -out certs/server.crt -days 7 -sha256 \
  -extfile certs/server.ext
```

`subjectAltName=DNS:localhost,IP:127.0.0.1` lets `curl` verify the hostname when connecting to `https://localhost:8443`. **Never use** `curl -k`/`--insecure`: specify the trusted CA with `--cacert certs/ca.crt`.

### 13.3. Creating Client Certificates alice, admin, locked, stranger

```bash
for name in alice admin locked stranger; do
  openssl req -newkey rsa:3072 -nodes \
    -keyout "certs/$name.key" -out "certs/$name.csr" \
    -subj "/CN=$name/O=Learning"

  cat > "certs/$name.ext" <<EOF
basicConstraints=critical,CA:FALSE
subjectAltName=URI:spiffe://example.test/users/$name
extendedKeyUsage=clientAuth
keyUsage=digitalSignature
EOF

  openssl x509 -req -in "certs/$name.csr" \
    -CA certs/ca.crt -CAkey certs/ca.key -CAcreateserial \
    -out "certs/$name.crt" -days 7 -sha256 \
    -extfile "certs/$name.ext"
done
```

All four client certificates are signed by the demo CA and carry policy-compliant SAN URIs. **Only** `alice`, `admin`, and `locked` exist in the user service; `stranger` is absent from the directory. `locked` has an account that is locked, so TLS may succeed while Spring authentication rejects it.

Inspect SAN/EKU:

```bash
openssl x509 -in certs/alice.crt -text -noout
openssl verify -CAfile certs/ca.crt certs/alice.crt
```

Expect `openssl verify` output ending with `certs/alice.crt: OK`. Full certificate details include random serials/validity/keys, so there is **no fixed byte-for-byte stdout** for `x509 -text`.

### 13.4. Creating Server Keystore and Truststore

```bash
openssl pkcs12 -export \
  -inkey certs/server.key -in certs/server.crt \
  -certfile certs/ca.crt -name localhost \
  -out certs/server.p12 -passout pass:localpass

keytool -importcert -noprompt -alias local-demo-ca \
  -file certs/ca.crt -keystore certs/trust.p12 \
  -storetype PKCS12 -storepass localpass
```

`server.p12` holds the HTTPS server's private key. `trust.p12` holds the accepted CA certificate used to verify client certs. CA and client private keys must **never** appear in the server truststore.

On pure Windows PowerShell, translate the Bash script into equivalent PowerShell or run it inside Git Bash/WSL; do not paste Bash loops/heredocs verbatim into PowerShell 5.1.

### 13.5. Running Spring Boot and Making Requests

```bash
java -version
mvn -version
mvn clean test
mvn spring-boot:run
```

**Note:** `mvn clean test` does not require real CA files because tests override SSL and use mock `SslInfo`; `mvn spring-boot:run` requires `certs/server.p12` and `certs/trust.p12` before starting HTTPS.

Client `alice` accesses profile:

```bash
curl --cacert certs/ca.crt \
  --cert certs/alice.crt --key certs/alice.key \
  -i https://localhost:8443/api/me
```

If both handshake and account lookup succeed, expected body:

```text
user=alice
```

Client `alice` reads reports:

```bash
curl --cacert certs/ca.crt \
  --cert certs/alice.crt --key certs/alice.key \
  -i https://localhost:8443/api/reports
```

Expected body `reports OK`; calling `/api/admin` with the same cert must return **403 Forbidden** because Alice lacks `ROLE_ADMIN`.

Client `admin`:

```bash
curl --cacert certs/ca.crt \
  --cert certs/admin.crt --key certs/admin.key \
  -i https://localhost:8443/api/admin
```

Expected body `admin OK` (200) because the server trusts the CA, SAN maps to `admin`, and the user directory loads `ROLE_ADMIN`.

Client `stranger`:

```bash
curl --cacert certs/ca.crt \
  --cert certs/stranger.crt --key certs/stranger.key \
  -i https://localhost:8443/api/me
```

The `stranger` certificate is signed by the same demo CA and may pass TLS, **but** the application finds no user; Spring Security must reject the request. The exact status depends on the authentication entry point, not automatically a TLS failure.

Client **without a certificate**:

```bash
curl --cacert certs/ca.crt -v https://localhost:8443/health
```

Because `server.ssl.client-auth: need` is set, expect the handshake/request to be rejected at TLS. **Do not** infer from `permitAll("/health")` that no client cert is needed.

### 13.6. End-to-End Test Matrix

| Client Certificate | TLS CA Trusted? | Account | Authorities | `/api/me` | `/api/admin` |
| --- | --- | --- | --- | --- | --- |
| Alice | Yes | Enabled | READER | 200 | 403 |
| Admin | Yes | Enabled | READER, ADMIN | 200 | 200 |
| Locked | Yes | Locked | READER in directory | Authentication rejected | Authentication rejected |
| Stranger | Yes | Does not exist | None | Authentication rejected | Authentication rejected |
| No cert | Not presented | N/A | N/A | TLS handshake reject | TLS handshake reject |
| Cert from untrusted CA | No | N/A | N/A | TLS handshake reject | TLS handshake reject |
| Expired / non-clientAuth cert | Rejected by TLS policy | N/A | N/A | TLS reject | TLS reject |

These outcomes are **expected design behavior**, not measured logs from your system. If you change TLS providers, proxies, or mTLS policies, verify with Wireshark/OpenSSL debug and redacted app logs.

## 14. Protecting Behind a Reverse Proxy / API Gateway

mTLS is often terminated at an Ingress/Gateway:

```text
Client -- mTLS --> Gateway -- TLS? --> WebFlux Backend
                   |
                   +-- verify client CA/chain/status
                   +-- map cert -> trusted identity
                   +-- forward identity under strict policy
```

If the backend receives only internal HTTP traffic after TLS termination, `ServerHttpRequest.getSslInfo()` typically reflects the **gateway→backend TLS connection** or lacks the original client's peer certificate. Enabling `.x509()` on the backend here **will not automatically recover the end client's certificate**. You must decide:

1. **TLS passthrough:** pass the TLS connection straight through to WebFlux so Netty verifies the client cert directly and supplies the peer chain.
2. **Gateway terminates mTLS:** the gateway verifies the certificate and **forwards the authenticated identity** via a separate trusted mechanism: an authenticated proxy principal, a signed token/header with end-to-end protection, or another standardized mechanism. The backend verifies that proxy mechanism rather than trusting a raw header from the Internet.
3. **Double mTLS:** client→gateway and gateway→backend, noting that the certificate seen by the backend on the second hop **is the gateway's certificate**, not automatically the original client's cert.

Never allow external clients to send `X-Forwarded-Client-Cert: CN=admin` or `X-SSL-Client-S-DN: CN=admin` and treat it as authenticated. The gateway must strip client-supplied headers and enforce strict boundaries via network policy and cryptographic integrity. Without a verifiable chain of custody for the identity header, **never grant permissions from headers**.

### 14.1. Certificate Forwarding Is Not Certificate Verification

A PEM string forwarded in an HTTP header is just text; it does not prove the current request completed a TLS handshake using the matching private key. Use certificate forwarding only when the gateway has already verified TLS/key possession and protects headers against spoofing/tampering en route to the backend. Otherwise, an attacker can copy an admin's public certificate and attach it to a request; **public certificates are not secrets**.

### 14.2. Load Balancers and WebClient Client Certificates

When **your application** calls another service over mTLS using `WebClient`, you configure **client key material** on the Reactor Netty HTTP client and trust the target's server certificate. That is an **outbound mTLS client** use case, distinct from `ServerHttpSecurity.x509()`, which handles **inbound mTLS authentication**. A single server can act as both an mTLS server and an mTLS client, keeping keystores, identities, and trust domains separated by connection direction.

## 15. Certificates, Users, and Permissions: Production Risks

### 15.1. CA Issuance Is Part of the Authorization Boundary

If a CA can sign a cert for an attacker with SAN `spiffe://example.test/users/admin`, TLS will validate the signature and the extractor will map it to `admin`. Therefore, certificate issuance must strictly vet **who is permitted to receive each SAN URI**. Combine this with checking certificate subject/serial/fingerprint or binding specific certificate IDs to accounts when your threat model demands stronger binding.

Trusting a customer-operated CA or an overly broad truststore can create severe impersonation vulnerabilities. Never anchor an entire enterprise system on an uncontrolled CA.

### 15.2. Certificate Rotation and Key Incidents

Certificates and private keys have a lifecycle:

- Generate keys with a strong RNG; manage in an HSM/secret store when available.
- Issue certs with proper SAN/EKU/validity per CA policy.
- Distribute client private keys securely with strict file permissions.
- Rotate prior to expiration, with an overlap window if needed.
- Update and reload truststores according to Spring Boot/Netty operational capabilities.
- Revoke certificates upon device loss, key compromise, or employee departure.
- Remove accounts/roles promptly; an unexpired TLS cert does not mean an account remains authorized.

If a root or intermediate CA is compromised, locking individual accounts is not enough; revoke the CA/keys and execute a PKI incident response.

### 15.3. Revocation Is Not Automatic in Every JVM TLS Configuration

A certificate still within its validity window and signed by a trusted CA **may already be revoked**. Checking CRL/OCSP and fail-open/fail-closed behavior are **PKI/TLS operational controls that must be configured and tested separately**; never assume Spring Security `.x509()` automatically queries OCSP or CRLs on every request. When immediate revocation is required, consider a certificate-bound account registry or serial denylist at the trusted authentication layer alongside an incident response workflow. Never cache "valid certificate" indefinitely.

### 15.4. Roles Change Faster Than Certificate Lifetimes

A certificate may live for many days while user roles change hourly. `ReactiveUserDetailsService` can load current roles from a database or directory. If authorities are cached, enforce strict TTL/invalidation so `ROLE_ADMIN` is not retained after privilege revocation. Avoid baking roles into CN/SAN URIs, which would turn the CA into the manager of all business permissions.

### 15.5. TLS Does Not Replace CSRF/CORS

- **CSRF:** If browsers automatically present client certificates to a site with state-changing endpoints, evaluate CSRF just like any other ambient credential. mTLS does not replace CSRF tokens or origin checks.
- **CORS:** Controls cross-origin browser frontend access; CORS never proves certificate private-key ownership.
- **Authorization:** mTLS only establishes identity; APIs still require `hasRole`/`hasAuthority`/object-level checks.
- **Transport confidentiality:** still requires TLS 1.2+/TLS 1.3, sound ciphers, and client-side server hostname verification.
- **Sessions:** if a web app creates a login session after X.509, manage session lifecycle, logout, session fixation, and expiry explicitly.

### 15.6. Private Keys and Logging

Never log client private keys, server private keys, PKCS12 passwords, or full certificate chains containing sensitive data. Exposing a public certificate is different from exposing a private key, yet serials, SANs, subjects, and emails can still leak identity and correlate users. Log request IDs, issuer fingerprints or hashed certificate identifiers when needed, user IDs, outcomes, and reason categories under proper anonymization policies.

## 16. Common Issues and How to Troubleshoot

| Symptom | Common Cause | How to Debug |
| --- | --- | --- |
| TLS handshake fails before HTTP | Client missing cert, untrusted CA, wrong EKU, expired, key mismatch | `curl -v`, OpenSSL, server TLS logs |
| `/health` unreachable without cert | `client-auth=need` covers the entire port | Present a client cert, or use a separate health port with its own policy |
| `x509()` enabled yet no Authentication | HTTPS lacks mTLS, `SslInfo` has no peer certificate | Check Netty TLS config, proxy termination |
| Browser has client cert but API denies | SAN mismatches namespace, user missing/locked | Inspect cert SAN and directory status |
| CN parsing differs from expected | DN formatting/escaping, legacy extractor | Upgrade Spring Security, use `SubjectX500` or SAN |
| One cert maps to two identities | SAN has multiple URIs in the same namespace | Reject ambiguous certificates |
| Unexpected CA issues `admin` CN/SAN | Overly broad CA issuance/trust policy | Restrict CAs, name constraints, enrollment approval |
| User `alice` gets 403 on admin | Has READER role, lacks ADMIN | Check `UserDetails` authorities |
| Cert filename contains `ROLE_ADMIN` | Filenames are just local convention | Roles must come from directory, never filenames |
| Using `X-Client-Cert` header | Can be spoofed over HTTP | Read peer chain from trusted TLS or gateway-signed identity |
| mTLS at gateway, backend sees no client cert | TLS terminated upstream of backend | Use passthrough or trusted forwarding design |
| Valid server cert yet curl reports hostname mismatch | Server SAN missing `DNS:localhost` | Regenerate server SAN; never disable verification |
| Curl "works" with `--insecure` | Skipping server trust verification | Use `--cacert` with the proper CA |
| TLS verified yet `stranger` still denied | No `UserDetails` for subject | Intended policy; enroll user properly |
| Locked user record still holds unexpired cert | Account status is independent of cert expiry | Manager must deny |
| Expired cert still lets user in | Misconfigured trust validation/reverse proxy | Audit TLS certificate verification and chain |
| Wrong truststore password/path | Netty SSL initialization error | Check P12 path/password/type |
| Certless HTTP request gets 200 on sensitive path | Auth fallback or wrong `permitAll` | Use `need`, disable unused Basic/form, review chains |
| Mocked `WebTestClient` passes, real curl fails | Mock performs no TLS handshake | Run real mTLS tests per Section 13 |
| Load balancer returns 502/handshake alert | Hop-by-hop mTLS error | Separate client→gateway and gateway→backend |
| CORS error hides HTTP status | Browser missing CORS headers | Debug CORS separately; never disable mTLS |
| Account revoked yet session remains | Cache/session lifetime too long | Design session invalidation/account-status refresh |
| Multiple tenants share username `alice` | Identity key lacks issuer/tenant | Use composite identity mapping |
| Revoked cert still passes TLS | CRL/OCSP/revocation policy unconfigured | Add revocation controls & tests |
| All routes return 403 after enabling x509 | Role mapping/entry point or `UserDetails` lookup bug | Debug preauth, authorities, and chain order |

### 16.1. Debugging in the Right Order

1. **Did the TLS handshake succeed?** If not, do not debug Spring authorization first.
2. Did the client send a cert, and are chain/truststore/validity/EKU/key possession valid?
3. Did Spring Netty receive the peer chain in `SslInfo` (directly or via proxy)?
4. What identity did `X509PrincipalExtractor.extractPrincipal` return; are SAN/CN/namespace valid?
5. Did `ReactiveUserDetailsService.findByUsername` find the user; is the account disabled/locked/expired?
6. Did `ReactivePreAuthenticatedAuthenticationManager` produce an authenticated principal or error?
7. Does `Authentication.getAuthorities()` include `ROLE_READER`/`ROLE_ADMIN` per policy?
8. Check whether HTTP 403 stems from roles, CSRF, or another matcher; never equate every 403 with bad credentials.
9. Check rotation/revocation/cache/account status for intermittent failures.
10. Keep private keys/secrets out of all logs, retaining trace IDs and safe reason categories.

## 17. Exercises and Answers

**Q1.** Client has no certificate, server has `client-auth=need`, `/health` is `permitAll`. Is HTTP 200 guaranteed?  
**Answer:** No. TLS demands a certificate before Spring evaluates `permitAll`.

**Q2.** Does successful mTLS mean the account has `ROLE_ADMIN`?  
**Answer:** No. TLS verifies the certificate chain/key; account lookup and roles are a separate step.

**Q3.** What is `X509PrincipalExtractor` used for?  
**Answer:** Mapping an `X509Certificate` to a principal ID so the authentication manager can look up the user.

**Q4.** Should WebFlux use `HttpSecurity` or `ServerHttpSecurity`?  
**Answer:** `ServerHttpSecurity` and `SecurityWebFilterChain`.

**Q5.** Why not accept `X-Client-Cert: CN=admin` sent by an HTTP caller?  
**Answer:** Headers do not prove private-key possession and can be spoofed.

**Q6.** X.509 principal extracted from CN, but the user does not exist in the directory?  
**Answer:** The preauth manager must reject it rather than granting access just because CN parsed.

**Q7.** Where will a certificate from an untrusted CA absent from the truststore fail?  
**Answer:** At TLS handshake/validation before any WebFlux controller.

**Q8.** Valid cert for `locked`, account is locked. Outcome?  
**Answer:** TLS may succeed, while Spring pre-authentication rejects the account.

**Q9.** Which authority corresponds to `hasRole("READER")`?  
**Answer:** By default convention, `ROLE_READER`.

**Q10.** Why is a URI SAN better than hand-rolled regex parsing of CN?  
**Answer:** It provides an explicit namespace/format, checks the trust domain, and eliminates ambiguous mapping—though a sound CA issuance policy is still required.

**Q11.** One cert contains two URI SANs `/users/alice` and `/users/admin`?  
**Answer:** Under project policy, reject because there is no unique principal.

**Q12.** Should `SubjectDnX509PrincipalExtractor` still be used on Spring Security 6.5.10?  
**Answer:** No. Patch to 6.5.11+ and avoid the deprecated class per advisory CVE-2026-47838.

**Q13.** In production, if a CA key is compromised, is deleting the `admin` user enough?  
**Answer:** No. Handle the CA compromise, rotate/revoke trust anchors and issued certificates, and audit issuance.

**Q14.** If a browser uses a client cert, is CSRF still needed?  
**Answer:** Potentially yes; browsers can automatically present client certificates on state-changing requests, so the CSRF threat model still applies.

**Q15.** Why doesn't `WebTestClient` with fake `SslInfo` replace real mTLS tests?  
**Answer:** Fakes skip the TLS handshake, CA trust, key possession, hostname checks, and revocation.

**Q16.** A client holds an unexpired mTLS cert, yet its role was revoked. What must the app do?  
**Answer:** The directory/current authorization policy must deny or restrict access; never retain `ROLE_ADMIN` indefinitely.

**Q17.** An API gateway terminates mTLS and the backend sees only the gateway's cert. Does `.x509()` automatically recover the original client's cert?  
**Answer:** Not automatically; you need TLS passthrough or a separately protected identity-forwarding mechanism.

**Q18.** Should the client send its private key in an HTTP header for the backend to verify?  
**Answer:** Absolutely not. mTLS sends only the public certificate and cryptographic proof; the private key stays on the client.

**Q19.** Is having a single internal CA in the truststore enough to guarantee zero user impersonation?  
**Answer:** Not by itself. You must govern which identities/SANs the CA may issue, revocation, and user/role mapping.

**Q20.** In WebFlux, where do you read `Authentication` from?  
**Answer:** The Reactive Security Context on the **Reactor Context**, e.g., `ReactiveSecurityContextHolder.getContext()`.

## 18. Production Readiness Checklist

- [ ] Spring Boot/Framework/Security versions patched (6.5 branch on 6.5.11+ for CVE-2026-47838).
- [ ] TLS 1.2+/1.3 with clear server certificate, hostname SAN, and trusted client CAs.
- [ ] `server.ssl.client-auth: need` or intentional `want` policy chosen.
- [ ] Client key material protected; proper file permissions/HSM/rotation/secret management.
- [ ] Truststore holds exact trust anchors without unrestricted expansion.
- [ ] Client EKU/`clientAuth`, validity, chain, and revocation policies tested.
- [ ] Never trust PEM certificates or self-declared headers sent by HTTP callers.
- [ ] If TLS terminates at a gateway, identity forwarding is protected against spoofing.
- [ ] Standard principal extractor chosen; no regex parsing of Subject DN; namespaced SAN used when appropriate.
- [ ] Mapping uses unique identifiers with tenant/issuer-aware boundaries, free of ambiguity.
- [ ] CA issuance policy prevents any client from obtaining another user's or admin's SAN.
- [ ] Pre-authenticated account lookup verifies existence, enabled, non-locked, and non-expired status.
- [ ] Authorities/roles come from a trusted directory, never cert filenames or request headers.
- [ ] Endpoints restricted by role/authority and object/tenant ownership.
- [ ] CSRF/CORS/sessions/other auth mechanisms threat-modeled separately.
- [ ] Negative tests cover no cert, untrusted CA, expired cert, wrong SAN, unknown/locked user, missing role.
- [ ] Real TLS experiments executed, not just `WebTestClient` with fake `SslInfo`.
- [ ] Runbooks exist for cert renewal, revocation, CRL/OCSP, truststore rotation, and outages.
- [ ] Keys/secrets/certificate PII never appear in logs, traces, screenshots, or repos.
- [ ] Multi-instance, gateway, health checks, and zero-downtime rotation tested before production.

## 19. Conclusion and Official Documentation

**Formula to remember:**

```text
mTLS trust (certificate chain + private-key possession)
           ≠ identity mapping (CN/SAN -> username)
           ≠ authorization (user account + roles + resource policy)
```

`ServerHttpSecurity.x509(...)` in Spring WebFlux bridges a **TLS-verified client certificate** and **Spring Security `Authentication`**. `X509PrincipalExtractor` selects an identity under an explicit policy, `ReactivePreAuthenticatedAuthenticationManager` checks the account and loads authorities, and `AuthorizationWebFilter` enforces permissions. None of those parts replaces the others.

**Official sources / standards:**

- Spring Security 6.5 – Reactive X.509 Authentication: https://docs.spring.io/spring-security/reference/6.5/reactive/authentication/x509.html
- Spring Security 6.5 – ServerHttpSecurity.x509 API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html
- Spring Security 6.5 – X509Spec: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.X509Spec.html
- Spring Security 6.5 – ReactivePreAuthenticatedAuthenticationManager: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authentication/ReactivePreAuthenticatedAuthenticationManager.html
- Spring Security 6.5 – SubjectX500PrincipalExtractor: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/preauth/x509/SubjectX500PrincipalExtractor.html
- Spring Security CVE-2026-47838 (fixed in 6.5.11, avoid SubjectDn parser): https://spring.io/security/cve-2026-47838/
- Spring Boot – SSL, key/trust stores and client auth: https://docs.spring.io/spring-boot/reference/features/ssl.html
- Spring Boot – Common application properties, server.ssl.client-auth: https://docs.spring.io/spring-boot/appendix/application-properties/
- Spring Framework 6.2 – SslInfo: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/http/server/reactive/SslInfo.html
- Spring Security – Reactive WebTestClient testing authentication: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html
- Spring Boot 3.5.16 release/end of OSS support: https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/
- IETF RFC 5280 – X.509 PKI Certificate and CRL Profile: https://www.rfc-editor.org/rfc/rfc5280
- IETF RFC 8446 – TLS 1.3: https://www.rfc-editor.org/rfc/rfc8446
- OWASP – Transport Layer Security Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html
