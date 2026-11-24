# Mapping X.509 Certificate Identities to Accounts and GrantedAuthority in Spring Security

## 1. The Problem: A Valid Certificate Is Not Enough to Know What a User May Do

In the **mutual TLS (mTLS)** model, a client presents an X.509 digital certificate to the server. The TLS server checks the certificate against trust policies, validity period, key usage, and corresponding PKI conditions. Spring Security can then take the identity verified at the TLS layer to look up the **application account** and load its set of **`GrantedAuthority`** instances.

Three questions must be distinguished:

1. **Is the certificate accepted?** This is primarily the responsibility of TLS/container, with trust stores and certificate verification rules.
2. **Which account does the certificate represent?** This is *certificate identity mapping*: selecting an identifier from the certificate and matching it against the application's registry/directory.
3. **What is the account permitted to do?** This is *authority mapping*: loading the account's current roles/permissions into `GrantedAuthority` objects.

For example: a client uses a certificate issued by a corporate CA with SAN URI `spiffe://company.example/service/report-reader`. After mTLS authentication, the application maps that URI to account `svc-report-reader` and loads the `REPORT_READ` permission. The certificate **does not automatically grant** `ROLE_ADMIN` or `REPORT_READ` simply because the Subject contains a plausible-looking name.

### Processing Flow Diagram

```text
HTTPS client + X.509 client certificate
                |
                v
[TLS server / reverse proxy / servlet container]
  Verifies trust chain, validity, CA / EKU policy,
  matches names and revocation per deployment config
                |
                v
X509AuthenticationFilter  (Spring Security Servlet)
  -> retrieves client certificate verified by container
  -> X509PrincipalExtractor: selects identity key
                |
                v
PreAuthenticatedAuthenticationToken
                |
                v
PreAuthenticatedAuthenticationProvider
  -> UserDetailsService / AuthenticationUserDetailsService
  -> identity key => app/directory resolves account
  -> account enabled? roles/permissions?
                |
                v
UserDetails + Collection<GrantedAuthority>
                |
                v
Authenticated Authentication -> SecurityContext
                |
                v
Authorization: hasAuthority / hasRole / @PreAuthorize
```

**Trust boundary:** Spring Security X.509 here is a **pre-authentication** mechanism. It trusts that the TLS layer is responsible for verifying the certificate before creating the input identity. Merely reading a DN string or HTTP header and treating the client as authenticated breaks this assumption.

## 2. Certificate Fields Usable as Identity Keys

X.509 supports multiple identity sources. No single field suits every organization; choose based on CA policy and account lifecycle.

| Source | Meaning | Pros / Cons |
| --- | --- | --- |
| **Subject DN** (`X500Principal`) | Distinguished name string, e.g., `CN=svc-report,OU=Services,O=Example` | Quick CN extraction; uniqueness or immutability not guaranteed; must parse DN properly |
| **Subject Alternative Name (SAN) DNS/email/URI** | Alternative identifier, e.g., `URI:spiffe://company.example/service/report-reader` | Fits service identities if CA controls namespaces; do not arbitrarily trust any SAN |
| **Issuer DN + serial number** | Pair identifying a certificate within an issuer's scope | Suits allowlisting specific certificates; renewing a cert typically yields a new serial |
| **SHA-256 certificate fingerprint** | Hash of the full DER certificate | Pins an exact certificate; must be updated on renew/reissue |
| **Internal account name** | `accountId`/`userId` managed by the application | Durable business identifier; requires a registry mapping certs to accounts |

**Important points:**

- `CN` is just one attribute of Subject. Two different certificates can share the same CN; a CA issuing duplicate CNs does not create unique accounts automatically.
- `subject.getName(X500Principal.RFC2253)` yields a relatively consistent DN representation; **do not use `split(",")` or naive regexes to parse DNs** because commas/special characters can be escaped. When inspecting an RDN, use `javax.naming.ldap.LdapName` and check proper ordering/data types.
- SAN URI (e.g., SPIFFE ID) or SAN email works **only when the CA/organization controls issuance policy for those values**, enforces normalization rules, and prevents tenant/namespace overlap.
- Issuer + serial must be bound to an **accepted trust domain/CA**. An Issuer DN string by itself is not cryptographic proof; TLS must verify the signature and certificate path.
- A certificate serves as mTLS proof only while valid. Using it as an account key must not bypass account lock status, revocation, permission revocation, and lifecycle governance.

Example of two certificates with the same CN but different issuers:

```text
Certificate A:
  Subject = CN=report-bot,O=Example
  Issuer  = CN=Internal Client CA,O=Example
  Serial  = 2A

Certificate B:
  Subject = CN=report-bot,O=Example
  Issuer  = CN=External Partner CA,O=Partner
  Serial  = 19

Same CN; different issuer + serial pairs.
The registry must not treat A and B as the same account
just because both contain CN=report-bot.
```

## 3. Spring Security Classes Involved in Mapping

In a **Servlet / Spring MVC** application with Spring Security 6.x:

| Class / Interface | Role |
| --- | --- |
| `X509AuthenticationFilter` | Reads certificate chain from servlet request, extracts principal, creates pre-auth token |
| `X509PrincipalExtractor` | `Object extractPrincipal(X509Certificate cert)`, determines identity key from certificate |
| `PreAuthenticatedAuthenticationToken` | Carries principal and pre-auth credentials for internal authentication |
| `PreAuthenticatedAuthenticationProvider` | Uses user-details service to load account/authorities |
| `UserDetailsService` | `loadUserByUsername(String)`: looks up account from the selected identity key |
| `AuthenticationUserDetailsService<PreAuthenticatedAuthenticationToken>` | Variant receiving the full pre-auth token if the app needs details beyond username |
| `UserDetails` | Represents the application account with `getUsername()`, status flags, and authorities |
| `GrantedAuthority` / `SimpleGrantedAuthority` | A single permission, typically a role or permission name |
| `SecurityContext` | Holds `Authentication` for the current request processing |

Spring Security's `http.x509(...)` creates the required filter/provider. By X.509 convention, the servlet layer supplies the certificate via the `jakarta.servlet.request.X509Certificate` request attribute. This is container-provided data **after TLS has authenticated the client certificate**; Java code should never treat an uncontrolled HTTP header as an equivalent trusted source.

### Distinguishing Principal and GrantedAuthority

Example after authentication:

```text
Authentication.getName()            -> "svc-report"
Authentication.getPrincipal()       -> UserDetails(internal account)
Authentication.getAuthorities()     -> [REPORT_READ, ROLE_SERVICE]
Certificate SAN URI                 -> "spiffe://company.example/service/report"
```

The certificate identifier can differ from the application account name. One principal may have multiple valid certificates rotating concurrently while pointing to one account; conversely, never map bulk unauthorized certificates to a privileged account.

Authority syntax rules:

- `hasAuthority("REPORT_READ")` checks for the **exact** authority `REPORT_READ`.
- `hasRole("ADMIN")` with the default prefix configuration checks for `ROLE_ADMIN`.
- `ROLE_ADMIN` is an ordinary authority, not a special status automatically read from Subject.
- Never turn arbitrary SAN/CN strings into `ROLE_<value>` or admin rights. You must have allowlists/translation rules and an independent, governed authority source.

## 4. Designing a Certificate -> Account Binding Table

A real system typically maintains at least two datasets:

**Certificate binding table:**

| identity_key | account_id | status |
| --- | --- | --- |
| `issuer=CN=Example Client CA,O=Lab;serial=2a` | `svc-report` | active |
| `issuer=CN=Example Client CA,O=Lab;serial=31` | `svc-report` | active (certificate being rotated) |
| `spiffe://company.example/service/billing` | `svc-billing` | active |

**Account and permissions table:**

| account_id | enabled | permissions |
| --- | --- | --- |
| `svc-report` | true | `REPORT_READ`, `ROLE_SERVICE` |
| `svc-billing` | true | `INVOICE_CREATE`, `ROLE_SERVICE` |
| `svc-retired` | false | no authorities granted at authentication time |

Workflow in the mapping service:

1. Read the identity key verified by TLS and produced by the extractor.
2. Require **exactly one** active binding within the corresponding trust domain; reject ambiguous results.
3. Fetch the current account and check enabled/locked/expired flags per policy.
4. Load the account's roles/permissions from a trusted source and convert them to `GrantedAuthority`.
5. Return `UserDetails`. If no binding exists, the account is locked, or required data is missing, **reject authentication** (fail closed).
6. The application continues checking each endpoint via `authorizeHttpRequests`, `hasAuthority`, and/or method security.

**Never embed arbitrary certificate permissions directly into an account** unless the certificate profile has trustworthy permission constraints, is CA-signed, has clear mapping policies, and is audited. In most applications, permissions live in internal databases/IAM/directories; the certificate simply identifies who is connecting.

## 5. Runnable Java 17 Example: Mapping an Identity Key to Account and GrantedAuthority

The following standalone example **does not create a TLS connection and does not pretend to verify certificates**. It tests the business logic **after** TLS verification: certificate key -> account -> authorities, including unrecognized certificates. You can use it to understand mapping before integrating Spring Boot.

Project `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.security:spring-security-core:6.3.5'
}

application {
    mainClass = 'demo.CertificateAccountMappingDemo'
}
```

Create `src/main/java/demo/CertificateAccountMappingDemo.java`:

```java
package demo;

import java.math.BigInteger;
import java.security.cert.X509Certificate;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

import javax.security.auth.x500.X500Principal;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

public class CertificateAccountMappingDemo {

    // A certificate registration key, not an Authentication object.
    public record CertificateKey(String issuerDn, String serialHex) {

        public static CertificateKey from(X509Certificate certificate) {
            String issuer = certificate.getIssuerX500Principal()
                    .getName(X500Principal.RFC2253);
            String serial = certificate.getSerialNumber()
                    .toString(16).toLowerCase(Locale.ROOT);
            return new CertificateKey(issuer, serial);
        }

        public static CertificateKey of(String issuerDn, BigInteger serial) {
            return new CertificateKey(
                    new X500Principal(issuerDn).getName(X500Principal.RFC2253),
                    serial.toString(16).toLowerCase(Locale.ROOT));
        }
    }

    public record LocalAccount(
            String accountId,
            boolean enabled,
            Set<String> permissionNames) {}

    public record BoundIdentity(
            String accountId,
            List<GrantedAuthority> authorities) {}

    public static BoundIdentity resolve(
            CertificateKey certificate,
            Map<CertificateKey, LocalAccount> bindings) {

        // The registry must be managed by an authoritative source,
        // do not take roles directly from client-asserted CN/SAN.
        LocalAccount account = bindings.get(certificate);
        if (account == null || !account.enabled()) {
            throw new SecurityException("Unknown or disabled account");
        }

        List<GrantedAuthority> grants = account.permissionNames().stream()
                .sorted()
                .<GrantedAuthority>map(SimpleGrantedAuthority::new)
                .toList();

        return new BoundIdentity(account.accountId(), grants);
    }

    public static void main(String[] args) {
        CertificateKey known = CertificateKey.of(
                "CN=Example Client CA,O=Lab", new BigInteger("42"));

        Map<CertificateKey, LocalAccount> bindings = Map.of(
                known,
                new LocalAccount("svc-report", true,
                        Set.of("REPORT_READ", "ROLE_SERVICE")));

        BoundIdentity principal = resolve(known, bindings);
        System.out.println("principal=" + principal.accountId());
        System.out.println("authorities=" + principal.authorities().stream()
                .map(GrantedAuthority::getAuthority).toList());
        System.out.println("canReadReports=" + principal.authorities().stream()
                .anyMatch(a -> a.getAuthority().equals("REPORT_READ")));

        try {
            CertificateKey unknown = CertificateKey.of(
                    "CN=Example Client CA,O=Lab", new BigInteger("43"));
            resolve(unknown, bindings);
        } catch (SecurityException rejected) {
            System.out.println("unknown=rejected");
        }
    }
}
```

Run with installed Gradle: `gradle run`. If the project has a Wrapper, use `./gradlew run` (Linux/macOS) or `gradlew.bat run` (Windows). **The Java program's stdout** is exact as follows; Gradle may print additional logs outside stdout:

```text
principal=svc-report
authorities=[REPORT_READ, ROLE_SERVICE]
canReadReports=true
unknown=rejected
```

**Code explanation:**

- `CertificateKey.from(X509Certificate)` can be used with a **certificate object verified by TLS/container** in a real application; in `main`, `CertificateKey.of(...)` merely constructs a sample key to run mapping logic and **does not prove a valid certificate**.
- `issuerDn + serialHex` is an example of binding a **specific certificate**. When issuing a renewed certificate, the serial may change; the new approved binding must be added before removing the old binding.
- Key not found or account disabled: throws `SecurityException`. The Spring integration layer translates this state into an appropriate authentication failure; never assign a default role to proceed.
- The permission list is sorted so stdout and tests have deterministic ordering. `SimpleGrantedAuthority` holds the **exact permission name** granted by the application.
- `resolve` operates on a trusted registry and **does not verify trust chains, signatures, or revocation**. Those belong to PKI/TLS configuration and integration testing.

### Additional Mapping Test Scenarios

Unit tests should cover all four cases:

| Input | Account Registry | Expectation |
| --- | --- | --- |
| Issuer + serial matching active binding | enabled, has `REPORT_READ` | Return exact account + `REPORT_READ` |
| Matching issuer, different serial | no binding | Reject |
| Valid cert key, disabled account | disabled | Reject |
| One account with multiple registered cert keys | 2 active keys pointing to one account | Both resolve to same account, permissions come from account |

Additionally, test `null`/empty inputs, permission changes, and registry outage cases to verify whether the system fails closed or uses controlled caching.

## 6. Integration with Spring Boot 3.x / Spring Security 6.x (Servlet)

Spring Security supports `HttpSecurity.x509` configuration. In 6.x, you can set an `X509PrincipalExtractor` returning an identity key and a `UserDetailsService` mapping that key to an internal account. The following example illustrates a system with one approved client. It uses `issuer + serial` similar to the standalone Java example.

**Dependencies** of the Boot application:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
```

**Spring Security Configuration** (file `src/main/java/demo/CertificateSecurityConfig.java`):

```java
package demo;

import javax.security.auth.x500.X500Principal;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class CertificateSecurityConfig {

    @Bean
    UserDetailsService certificateAccounts() {
        // Example of a single approved certificate. In a real system,
        // retrieve the registry/roles from a database or centrally managed IAM.
        return certificateKey -> {
            if (!"CN=Example Client CA,O=Lab#2a".equals(certificateKey)) {
                throw new UsernameNotFoundException(
                        "No account bound to certificate");
            }
            return User.withUsername("svc-report")
                    .password("{noop}not-used-by-preauthentication")
                    .authorities("REPORT_READ", "ROLE_SERVICE")
                    .build();
        };
    }

    @Bean
    SecurityFilterChain apiSecurity(
            HttpSecurity http, UserDetailsService certificateAccounts)
            throws Exception {

        return http
                .authorizeHttpRequests(access -> access
                        .requestMatchers("/api/reports/**")
                            .hasAuthority("REPORT_READ")
                        .anyRequest().authenticated())
                .x509(x509 -> x509
                        .x509PrincipalExtractor(cert ->
                                cert.getIssuerX500Principal()
                                        .getName(X500Principal.RFC2253)
                                + "#" + cert.getSerialNumber().toString(16))
                        .userDetailsService(certificateAccounts))
                .build();
    }
}
```

**Key distinctions when reading the code:**

1. `x509PrincipalExtractor` only produces the key `CN=Example Client CA,O=Lab#2a`. It **does not choose roles itself** and does not validate signatures itself.
2. `certificateAccounts()` selects the exact permitted account/authorities from the example registry. Certificate absent from registry => throws `UsernameNotFoundException` => authentication fails.
3. `UserDetails` returns application username `svc-report`; consequently `Authentication.getName()` is typically `svc-report` rather than the Issuer/serial string.
4. `password("{noop}not-used-by-preauthentication")` here is a placeholder string because the `User` builder requires a password field; X.509 pre-auth **does not check this password**. Never turn it into a real credential or store client passwords in the mapper.
5. `.hasAuthority("REPORT_READ")` only allows reading reports when the actual account holds that authority. A valid certificate lacking the permission is still rejected at authorization.
6. The code uses the Spring Security **6.x** API. In modern versions, prefer an explicit extractor instead of relying on regex CN capture; APIs and deprecations may change when upgrading to Spring Security 7.x.

This is a compilable configuration file when the Boot app has the corresponding dependencies; it is **not a standalone Java program with `main`**. The application must have `@SpringBootApplication`, endpoints/controllers, and real TLS configuration to receive certificates from browsers/clients.

### Server-Layer mTLS Configuration

The TLS layer needs the **server's** certificate/keystore, a trust store containing **allowed client** CAs/certificates, and client certificate requirement mode:

```yaml
# application.yml (resource paths and variable names depend on deployment)
server:
  port: 8443
  ssl:
    enabled: true
    key-store: classpath:server.p12
    key-store-type: PKCS12
    key-store-password: "${SERVER_KEYSTORE_PASSWORD}"
    trust-store: classpath:client-trust.p12
    trust-store-type: PKCS12
    trust-store-password: "${CLIENT_TRUSTSTORE_PASSWORD}"
    client-auth: need
```

- `server.p12` must hold the server's private key/certificate; `client-trust.p12` holds trusted anchors or client certificates per design.
- `client-auth: need` requires the client to send a TLS-accepted certificate. With `want`, the client might omit a cert; behavior/authorization must be explicitly defined, never assumed to pass.
- The file above is only a sample config: **you must generate/provision the keystore, truststore, and environment variables** before running live. Never commit keys, passwords, or production private certificates.
- If TLS terminates at an ingress/gateway, the Spring Boot backend will not automatically have the certificate in the servlet request attribute as in direct termination. You must design a protected integration between proxy and backend; see Section 9.

### Getting the User in a Controller

In a Spring MVC app configured as above:

```java
// Handler snippet to place inside a @RestController class with appropriate mapping.
@GetMapping("/api/reports/me")
public Map<String, Object> me(Authentication authentication) {
    return Map.of(
            "account", authentication.getName(),
            "authorities", authentication.getAuthorities().stream()
                    .map(GrantedAuthority::getAuthority).toList());
}
```

You must import `java.util.Map`, `org.springframework.security.core.Authentication`, `org.springframework.security.core.GrantedAuthority`, and `org.springframework.web.bind.annotation.GetMapping`. The endpoint returns the account/authorities established by Spring Security, rather than reading raw DN from the request and inferring permissions itself. Avoid exposing certificate fingerprints, issuer/serial, or sensitive data in public responses unless genuinely needed.

## 7. Using SAN URI, Email, or CN Instead of Issuer + Serial

### 7.1. SAN URI for Service Identity

A service may be issued a certificate with a SAN URI, such as:

```text
subjectAltName:
  URI:spiffe://company.example/service/report-reader
```

A custom `X509PrincipalExtractor` can extract this type of URI and return the exact string as the key. Proper sequence:

1. Accept only SAN URI matching X.509 type 6.
2. Accept only a specific trust domain/prefix, exact format, and expected identity count.
3. Never use `contains("report")` or grab an arbitrary suffix to infer a role.
4. Look up the `SAN URI -> accountId` registry, then load permissions from the account management system.
5. Constrain trusted CAs with policies allowing them to issue only the SAN URIs they are authorized to issue. If any CA in the trust store is allowed to issue `spiffe://company.example/...`, the namespace can be spoofed within that CA's scope.

A **logic-illustrative** extractor snippet (must handle `CertificateParsingException` and configure an appropriate provider in a real project):

```java
// Illustrative helper method (not a standalone class).
String extractExpectedServiceUri(X509Certificate certificate)
        throws CertificateParsingException {

    var sans = certificate.getSubjectAlternativeNames();
    if (sans == null) {
        throw new IllegalArgumentException("Missing SAN");
    }
    var uris = sans.stream()
            .filter(entry -> entry.size() >= 2)
            .filter(entry -> Integer.valueOf(6).equals(entry.get(0)))
            .map(entry -> entry.get(1))
            .filter(String.class::isInstance)
            .map(String.class::cast)
            .filter(uri -> uri.startsWith("spiffe://company.example/service/"))
            .distinct()
            .toList();

    if (uris.size() != 1) {
        throw new IllegalArgumentException("Expected exactly one service URI");
    }
    return uris.get(0);
}
```

To use as an `X509PrincipalExtractor` lambda, catch `CertificateParsingException` and translate it into an appropriate authentication error; never arbitrarily pick the first element when multiple SAN URIs exist. This snippet only checks syntax/prefix in the application; it does not replace TLS trust, CA policy, or identity provisioning checks.

### 7.2. CN Only for Strictly Controlled Models

The Spring Security 6.x API provides a convenience configuration:

```java
.x509(x509 -> x509
        .subjectPrincipalRegex("CN=(.*?)(?:,|$)")
        .userDetailsService(certificateAccounts))
```

Here, the regex group takes CN as the key passed to `UserDetailsService`. This is helpful for understanding the mechanism and for environments trusting only a small controlled set of certificates, but **CN is not a globally unique key**. With DNs containing escaped values, multiple RDNs, or CAs issuing duplicate CNs, regexes easily fail to express the intended identity policy. When relying seriously on certificate identity, consider SAN URI, canonical ID, or issuer+serial/fingerprint paired with CA policy.

### 7.3. Email SAN Requires Account Binding

Emails can change or be reassigned to another person, especially in enterprise systems. If email SAN is needed to select an account, treat the email as a **CA-verified and lifecycle-managed identity**; never extract email by parsing arbitrary Subject DN strings, nor infer permissions from a domain like `@example.org`.

## 8. UserDetailsService and Authority Sources

`UserDetailsService` in the example receives the extracted key and performs mapping. Think in two steps:

```text
certificate identity (input) --> binding --> canonical account id
canonical account id --> account policy / IAM groups --> GrantedAuthority
```

In a real system:

- Allow one account to have multiple certificate bindings during controlled rotation.
- Keep account status, permissions, and certificate bindings in an auditable authoritative source.
- Map external groups/claims to application authorities through an **allowlist**; roles should appear only when explicitly backed by policy.
- If the directory/DB is unavailable, never silently grant `ROLE_USER` or retain admin privileges from an infinite cache.
- Permissions can change while a certificate is still valid. Define permission reload frequency, cache TTL, session/security context handling, and revocation mechanisms.
- `AuthenticationUserDetailsService<PreAuthenticatedAuthenticationToken>` is another extension point when mapping requires context from the pre-auth token. Do not confuse it with `UserDetailsService`, which only receives a username; use the actual API matching the data type you need to process.
- Never use `DaoAuthenticationProvider` to compare passwords in this mTLS flow: permissions are loaded based on the TLS-authenticated identity, with no user username/password login.

**If loading permissions from AD/LDAP:** X.509 identifies which account the certificate belongs to; the directory service can provide attributes or groups. A controlled group -> `GrantedAuthority` mapping step is required. `memberOf` does not automatically equal `ROLE_ADMIN`, nested groups have specific rules, and permissions should reflect the account's latest state.

## 9. Reverse Proxy / Ingress: An Easily Overlooked Trust Boundary

Two deployment models have different implications:

**(A) mTLS terminates directly at Spring Boot/Tomcat.** The container verifies the certificate and places `X509Certificate[]` onto the servlet request; Spring Security `X509AuthenticationFilter` uses this source.

**(B) mTLS terminates at a gateway/ingress.** The backend sees HTTP or a *new* TLS connection from the gateway, not the original client's certificate directly. If the gateway passes identity via HTTP headers, the application must:

1. Block direct backend access from unauthorized clients.
2. Require the gateway to strip client-sent identity headers before inserting verified metadata.
3. Protect gateway -> backend (e.g., internal mTLS and network policies), identifying the trusted gateway.
4. Distinguish clearly whether forwarded data is a *verified certificate identity* or merely a raw client-asserted header.
5. Use a backend authentication component fitting the gateway model; **do not assume Spring Security `x509()` automatically reads forwarded certificate headers**.

A dangerous example is a backend trusting `X-Client-Cert-Subject: CN=admin` that any internet client could send directly to the backend. Without route blocking, header stripping, and channel protection, that is an identity spoofing vulnerability.

## 10. Common Errors and Fixes

**Error 1 — Enabled `http.x509()`, yet requests have no principal.** Check whether the server truly requires client certificates, whether TLS terminates at the backend, whether the chain is accepted by the container, and whether the request has `jakarta.servlet.request.X509Certificate`. Spring Security does not create certificates for clients.

**Error 2 — Valid certificate exists, but rejected after TLS.** This may be an **account mapping** error: the extractor generates a key not matching the registry format; the account does not exist/is disabled; authorities are missing; or the endpoint requires a different authority. Distinguish handshake errors from HTTP 401/403 using sanitized logs.

**Error 3 — Same CN, yet the system lets an unknown user log into an old account.** Duplicate CNs or another CA in the same truststore may issue identical names. Choose an unambiguous identity key; restrict CA/namespace and bind certificates to accounts via a registry.

**Error 4 — Treating `X509PrincipalExtractor` as signature/CA verification.** The extractor only returns an identity from `X509Certificate`; TLS/container must prove the chain, key usage, validity, and other PKI conditions. Never treat certificate objects constructed in unit tests as verification proof.

**Error 5 — Granting `ROLE_ADMIN` because a cert has SAN `ADMIN`.** Subject/SAN data should never directly become a role. Permissions must come from approved policies, active accounts, or certificate profiles with genuinely strict controls.

**Error 6 — Rotating a certificate breaks permissions even though the account still exists.** Issuer+serial or fingerprint changes upon renewal. Support new certificate registration, brief overlap, revoking old bindings, and auditing rotation events. Never relax policy to “any cert with same CN” as a quick fix.

**Error 7 — Locked account can still access while certificate remains valid.** Check enabled/locked/expired whenever refreshing the principal, review cache/session handling, and handle revocation/locking appropriately. Certificate lifetime and account lifetime are two separate lifecycles.

**Error 8 — Assuming mTLS automatically guarantees revocation.** CRL/OCSP checks typically depend on specific TLS/PKI configuration and execution. If strict revocation is required, test the actual revocation policy; do not assume every Java server checks OCSP automatically.

**Error 9 — Confusing 401/403 with TLS handshake failure.** If the client lacks a cert when `client-auth: need`, the connection may fail **before HTTP**, yielding no 401/403 response. Only when TLS succeeds and account/authority is denied is it an application security case.

**Error 10 — Authorities mismatching `hasRole`.** `hasRole("REPORT")` typically checks `ROLE_REPORT`, whereas `hasAuthority("REPORT_READ")` checks exact `REPORT_READ`. Use a consistent convention and test actual permissions.

**Error 11 — Parsing DN with `split(",")`.** DNs can contain escapes, multiple RDNs, and non-fixed field order. Use `X500Principal`/`LdapName` or design standard issuer+serial/SAN keys instead of brittle custom string parsers.

**Error 12 — Copying Servlet code into WebFlux.** `HttpSecurity` and `X509AuthenticationFilter` in the examples are **Servlet/MVC**. For Reactive WebFlux, filters and security configuration differ; do not plug Servlet filters into `ServerHttpSecurity`.

## 11. What Must End-to-End Testing Prove?

Mapper unit tests prove mapping logic; **mTLS integration tests** confirm trust boundaries and behavior when certificates arrive over the network.

| Test | Expectation and Evidence |
| --- | --- |
| Client sends no cert when server has `client-auth: need` | TLS handshake fails or connection is rejected before HTTP |
| Client sends self-signed cert rejected by truststore | TLS rejects; never reaches application mapping |
| Client sends trusted cert with unbound key | Mapping fails; no Authentication granted privileges |
| Client cert bound, but account disabled | Rejected at account lookup step |
| Valid cert and account with `REPORT_READ` | `/api/reports/**` endpoint succeeds when handled by controller |
| Valid cert and account with only `INVOICE_CREATE` | Reports endpoint returns 403 due to insufficient permissions |
| Account switches to newly registered cert | Same canonical account, proper permissions, old cert deactivated on schedule |
| Permissions changed/revoked in IAM | Verify new requests and caches/sessions do not retain stale permissions past allowed TTL |
| Gateway sends spoofed client identity header | Backend rejects data not arriving from trusted gateway channel |

When testing with `curl`, you need **client certificate file, private key, trusted CA, and a configured HTTPS server**. A command like the following is only an example once valid certificates are in place:

```bash
curl --cert client.crt --key client.key \
  --cacert server-ca.crt \
  https://localhost:8443/api/reports/me
```

The .crt/.key files are illustrative and are not provided by the Java snippet. You must issue a client cert matching the issuer/serial bound in the registry and a server cert with a SAN for the accessed hostname. Never use `-k` to skip server TLS verification as a production “fix”.

### Pre-Production Review Checklist

1. Do the trust store and CA policy accept only the intended client identities?
2. Does the identity key based on SAN/issuer+serial/fingerprint truly distinguish tenants, CAs, and rotation workflows?
3. Which authoritative system owns certificate bindings, and can they be audited and revoked?
4. Are disabled accounts rejected even if their certificates are not yet expired?
5. What is the trusted source of permissions; is there any way subject/SAN could accidentally grant elevated privileges?
6. Have direct TLS and gateway-terminated paths been tested matching the actual deployment path?
7. Does logging of issuer/serial/fingerprint follow data minimization and proper access control?
8. Do tests distinguish TLS handshake failure, authentication failure, and authorization denial?

## 12. Official Reference Documentation

- Spring Security — X.509 client certificate authentication: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/x509.html
- Spring Security — Pre-Authentication Scenarios: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/preauth.html
- Spring Security API — `X509Configurer`: https://docs.spring.io/spring-security/site/docs/6.5.0-M1/api/org/springframework/security/config/annotation/web/configurers/X509Configurer.html
- Spring Security API — `X509AuthenticationFilter`: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/authentication/preauth/x509/X509AuthenticationFilter.html
- Spring Security API — `X509PrincipalExtractor`: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/authentication/preauth/x509/X509PrincipalExtractor.html
- Spring Security — Servlet Authentication Architecture: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html
- Spring Boot — SSL configuration: https://docs.spring.io/spring-boot/reference/features/ssl.html

**Key takeaway:** a certificate can prove that a client holds the corresponding private key in a TLS session and was issued by a valid CA, yet **application accounts and GrantedAuthority remain the result of controlled mapping**. Control all three boundaries: trusted certificate, binding to a valid account, and current application-granted permissions.
