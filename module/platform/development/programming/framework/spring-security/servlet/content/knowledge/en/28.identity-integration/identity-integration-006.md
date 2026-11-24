# X.509: Client Certificates and Mapping Subject to Accounts

**Scope:** Identity integration in **Spring Security Servlet / Spring MVC** applications, Java 17+, Spring Boot 3.x, and Spring Security 6.x. This lesson explains where **client** X.509 certificates are verified, how Spring Security extracts the **subject**, how to turn that identity into an account with access permissions, and what to watch for behind a reverse proxy. Examples run with embedded Tomcat and direct HTTPS; Spring WebFlux has its own reactive security APIs.

## 1. What Does X.509 Client Authentication Solve?

Normally HTTPS only requires the **server** to present a certificate so browsers/clients verify they are talking to a legitimate server. In **mutual TLS (mTLS)**, the server also requires the **client** to present its own certificate. The client proves possession of the **private key** matching the certificate's public key, while the server checks the trust chain, validity period, certificate usage rules, and applicable TLS constraints.

For example, an administrative system allowing access from employee machines provisioned with certificates:

1. The application receives a TLS connection.
2. The server requests a client certificate and validates it against a trusted **trust store** or CA.
3. Once TLS succeeds, the servlet container can attach the verified certificate chain to the request.
4. Spring Security uses `X509AuthenticationFilter` to retrieve the certificate, extract a principal from the subject, and authenticate that principal against the account store.
5. The application grants access only if **the account is valid and has sufficient permissions**.

Thus there are two separate questions: **"Is this certificate trustworthy at the TLS layer?"** and **"What is the identity bound to this certificate allowed to do in the application?"** mTLS solves the first layer, while Spring Security connects that identity to accounts/authorities for the next layer.

### 1.1 Distinguishing Server Certificates and Client Certificates

| Entity | Holds private key | Who verifies | Goal |
| --- | --- | --- | --- |
| **Server** certificate | TLS server / load balancer | Browser, curl, service client | Verify the server; protect the HTTPS channel. |
| **Client** certificate | Browser certificate store, device, or service caller | TLS server / inbound proxy | Verify device/client identity via PKI. |
| Application account | Directory/DB/`UserDetailsService` | Spring Security | Bind verified identity to account status and permissions. |

A valid client certificate **does not automatically** mean `ROLE_ADMIN`, `ROLE_USER`, or permission to read another person's data. Conversely, having an account name in the database is not enough when the client cannot prove possession of a valid private key.

### 1.2 Key Contents of an X.509 Certificate

Certificates typically contain attributes such as:

- **Subject distinguished name (DN):** identifies the subject, e.g., `CN=alice,OU=Engineering,O=Example,C=VN`.
- **Issuer DN:** the authority/organization that issued the certificate.
- **Serial number:** certificate serial assigned by the issuer; usually combined with issuer to identify a specific issuance.
- **Public key:** used when verifying proof of private key possession.
- **Validity:** `Not Before` and `Not After`, the certificate's validity window.
- **Subject Alternative Name (SAN):** may contain email, URI, DNS, IP, or other identifiers depending on the PKI profile.
- **Key Usage / Extended Key Usage (EKU):** constrains intended usage; client certificates are typically issued for `clientAuth`.
- **Signature/trust chain:** links the certificate to a root/intermediate CA or trust anchor trusted by the server per policy.

**Merely reading a subject string does not mean the certificate was verified.** The critical condition is that the subject comes from **a certificate verified by a trusted TLS component**, not an HTTP header string sent by the caller.

## 2. Flow from TLS to SecurityContext in a Servlet Application

```text
Client (browser, curl, service)
        │  HTTPS + client certificate
        ▼
TLS endpoint (embedded Tomcat / ingress)
        │  Verify chain, trust, validity, purpose
        │  and proof of private key possession
        ▼
Servlet request with verified certificate
        │  standard attribute "jakarta.servlet.request.X509Certificate"
        ▼
Spring Security Filter Chain
        │
        └── X509AuthenticationFilter
                 │ extract subject/principal
                 │ (e.g. CN=alice -> "alice")
                 ▼
            Pre-authentication provider
                 │ load UserDetails / account
                 ▼
            Authentication in SecurityContext
                 │ principal = alice
                 │ authorities = ROLE_READER
                 ▼
            Authorization (requestMatchers, @PreAuthorize, ...)
                 │
                 ▼
            Controller / Service
```

### 2.1 mTLS Is the TLS Endpoint's Job

When using **embedded Tomcat**, Spring Boot's `server.ssl.*` properties control the TLS connector. When `server.ssl.client-auth: need` is enabled, Tomcat requires a client certificate during the TLS handshake. If a certificate is rejected or a required certificate is missing, the connection can fail **before an HTTP request ever reaches Spring Security**. Therefore, this is usually a TLS/handshake failure, **not necessarily HTTP 401/403**.

Once the TLS handshake succeeds, the servlet container typically exposes a `java.security.cert.X509Certificate[]` array via request attribute `jakarta.servlet.request.X509Certificate`. Spring Security reads this via pre-authentication instead of asking the client for a password in the request body.

### 2.2 Spring Security Uses the Subject to Identify Accounts

`X509AuthenticationFilter` handles authentication based on client certificates. It extracts a principal from the certificate subject; a common default uses **Common Name (CN)**. Given subject:

```text
CN=alice,OU=Engineering,O=Example,C=VN
```

the expression:

```regex
CN=(.*?)(?:,|$)
```

extracts `alice` as the principal name in this simple DN case.

Next, a `UserDetailsService` can load the `alice` account, check whether the account is still permitted access, and supply authorities such as `ROLE_READER`. Those authorities are evaluated by `authorizeHttpRequests` or method security.

**Note:** the regex above is for **illustration**; DN strings can have escaping, varying RDN ordering, commas inside values, casing differences, and normalization rules. Moreover, **CNs can collide** across users or different CAs. In production systems, do not rely on CN alone unless PKI guarantees uniqueness and manages identity lifecycles.

### 2.3 Client-auth "need" vs. "want"

| TLS configuration | Primary behavior | Impact on Spring Security |
| --- | --- | --- |
| `server.ssl.client-auth: need` | Requires client to present a trusted certificate. | Without a valid cert, usually fails at TLS; even `permitAll` endpoints cannot bypass the TLS requirement. |
| `server.ssl.client-auth: want` | Requests a cert but allows connections without one. | If no cert is sent, X.509 authentication yields no cert identity; protected endpoints still need another auth mechanism. |
| `server.ssl.client-auth: none` | Does not request a client certificate. | No basis for an X.509 flow on this connector. |

Never use `want` as a way to "skip" authentication on sensitive endpoints. It only changes the **TLS-level** requirement, while the application must still enforce authorization policies. If public endpoints without certs and admin endpoints requiring certs must share a hostname, design separated connectors/ingress/filter chains with clear boundaries, because `client-auth: need` applies **to the TLS connector**, not just one URL.

## 3. Complete Example: Spring Boot 3 + Spring Security 6 + mTLS

Goal: run HTTPS at `https://localhost:8443`, allow only trusted client certificates to complete the TLS handshake, and map subject `CN=alice` to account `alice` with role `ROLE_READER`. Endpoint `GET /whoami` returns account/authority info and **never returns private keys or raw certificates**.

Create the project with Spring Initializr selecting **Gradle, Java 17+, Spring Boot 3.x, Spring Web, Spring Security**. Keep the Gradle wrapper (`gradlew` / `gradlew.bat`) generated by Initializr. If declaring dependencies manually for an existing Spring Boot 3.x project, two starters are required:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
```

Place the following Java files in package `com.example.x509demo`. This is a **Spring Boot application**, so run it via Maven/Gradle with Spring on the classpath; it is not a standalone `javac` program.

### 3.1 Configuring HTTPS and Client Truststore

**`src/main/resources/application.yml`**

```yaml
server:
  port: 8443
  ssl:
    enabled: true
    key-store: file:./server.p12
    key-store-type: PKCS12
    key-store-password: ${TLS_SERVER_STORE_PASSWORD}
    trust-store: file:./trusted-clients.p12
    trust-store-type: PKCS12
    trust-store-password: ${TLS_CLIENT_TRUSTSTORE_PASSWORD}
    client-auth: need
```

Meaning:

- `server.p12` holds the **server private key and certificate**, used to establish HTTPS.
- `trusted-clients.p12` holds **trusted client trust anchors/certificates** for the lab. In real deployments, you typically manage root/intermediate CAs and issuance policies rather than manually importing individual user certificates.
- `client-auth: need` forces clients to present a certificate during the TLS connection.
- Both passwords read from environment variables to keep secrets out of YAML. Never use demo passwords for production keys.
- `file:./...` resolves relative to the **process working directory at runtime**; in this example the `.p12` files sit at the project root.

**Asymmetric trust paths:** the client (browser/curl) must trust the **server certificate**, while the server must trust the **client certificate**. Adding a client cert to the server's truststore does not make browsers trust the server, and vice versa.

### 3.2 Configuring SecurityFilterChain to Map CN

**`src/main/java/com/example/x509demo/SecurityConfig.java`**

```java
package com.example.x509demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    UserDetailsService users() {
        // Demo account; password is NOT used for X.509 pre-auth.
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password("{noop}not-used-for-x509")
                .roles("READER")
                .build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            UserDetailsService users) throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/whoami").hasRole("READER")
                .anyRequest().authenticated()
            )
            .x509(x509 -> x509
                .subjectPrincipalRegex("CN=(.*?)(?:,|$)")
                .userDetailsService(users)
            );

        return http.build();
    }
}
```

Key parts to understand:

1. `.x509(...)` enables the client certificate authentication path in the **Servlet Security Filter Chain**.
2. `subjectPrincipalRegex(...)` defines how the principal is extracted from the subject DN. For instance, `CN=alice` becomes `"alice"`.
3. `userDetailsService(users)` loads the account and authorities for that principal. It **does not verify the TLS chain**; the TLS container must finish that step first.
4. `hasRole("READER")` checks authority `ROLE_READER`. A trusted certificate **is not enough** if the account is deleted/locked or lacks the required permission.
5. The password `{noop}not-used-for-x509` merely satisfies `UserDetails` construction for the demo; X.509 authentication uses certificate/private key and never sends this password. In production, fetch accounts and roles from a trusted identity store, enforce account-disable policies, and manage lifecycles.

**Important:** When you need to ensure a user remains valid after certificate changes or permission updates, examine caching/session behavior and session revocation explicitly; do not assume the certificate is re-verified on every HTTP request (TLS session resumption, connection reuse, and app caches may apply).

### 3.3 Controller Displaying the Authenticated Account

**`src/main/java/com/example/x509demo/WhoAmIController.java`**

```java
package com.example.x509demo;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WhoAmIController {

    @GetMapping("/whoami")
    public Map<String, Object> whoami(Authentication authentication) {
        return Map.of(
            "username", authentication.getName(),
            "authorities", authentication.getAuthorities()
                .stream()
                .map(GrantedAuthority::getAuthority)
                .sorted()
                .toList()
        );
    }
}
```

`authentication.getName()` returns the account name authenticated by Spring Security, **not necessarily the full subject DN**. Returning authorities helps observe the mapping, though real endpoints should not expose sensitive privilege structures unnecessarily.

**`src/main/java/com/example/x509demo/X509DemoApplication.java`**

```java
package com.example.x509demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class X509DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(X509DemoApplication.class, args);
    }
}
```

Match filenames precisely to public classes. Methods like `stream().toList()` use Java 16+ syntax/APIs, so **Java 17** satisfies them. The application does not need the controller to read certificates directly for login: Spring Security's filter handles that.

## 4. Generating Demo Certificate Pairs with keytool

The following commands are **only for learning and testing on a personal machine**. They create a **self-signed server certificate** and a **self-signed client certificate**, then explicitly trust that client certificate. Production requires a governed PKI/CA, certificates with accurate EKUs, controlled issuance/revocation/rotation procedures, and proper private key storage protection.

Run the commands in the **project root directory** (where `build.gradle` and `application.yml` referencing `file:./...` live). `keytool` ships with the JDK.

### 4.1 Generate Server Key/Certificate for localhost

```bash
keytool -genkeypair \
  -alias localhost \
  -keyalg RSA -keysize 3072 \
  -validity 30 \
  -storetype PKCS12 \
  -keystore server.p12 \
  -storepass changeit -keypass changeit \
  -dname "CN=localhost,OU=Learning,O=Example,C=VN" \
  -ext "SAN=dns:localhost,ip:127.0.0.1" \
  -ext "EKU=serverAuth"

keytool -exportcert \
  -alias localhost -keystore server.p12 \
  -storepass changeit -rfc -file server.crt
```

`server.p12` holds the server's private key: **never send this file to clients**. `server.crt` is the public certificate used with `curl --cacert` in dev environments. Self-signed server certificates are not trusted by browsers by default; browsers need an explicit trust anchor (add only to a test machine's trust store, never turn demo certificates into shared trust anchors).

### 4.2 Generate Client Certificate CN=alice

```bash
keytool -genkeypair \
  -alias alice \
  -keyalg RSA -keysize 3072 \
  -validity 30 \
  -storetype PKCS12 \
  -keystore alice.p12 \
  -storepass changeit -keypass changeit \
  -dname "CN=alice,OU=Learning,O=Example,C=VN" \
  -ext "EKU=clientAuth"

keytool -exportcert \
  -alias alice -keystore alice.p12 \
  -storepass changeit -rfc -file alice.crt
```

`alice.p12` holds the client's **private key** and certificate; **alice.crt** holds only the public certificate. Never copy `alice.p12` into repositories, frontend JavaScript, public Docker images, or logs.

### 4.3 Grant Trust for the Client on the Server

```bash
keytool -importcert \
  -alias alice \
  -file alice.crt \
  -keystore trusted-clients.p12 \
  -storetype PKCS12 \
  -storepass changeit \
  -noprompt
```

In this demo, `trusted-clients.p12` holds `alice`'s client certificate as a trust anchor. With a real PKI, the server usually trusts a controlled CA while account lookup determines which specific users are permitted access. **Trusting a client certificate** and **mapping an account** are two distinct configurations.

Inspect the local file if needed:

```bash
keytool -list -v \
  -keystore alice.p12 -storetype PKCS12 -storepass changeit
```

Verify `Owner: CN=alice,...`, issuer, validity, and matching EKU. Actual output contains specific fingerprints/metadata for the newly generated certificate; this lesson assumes no fixed fingerprint.

### 4.4 Launch the Application

Set the two environment variables referenced in YAML. On macOS/Linux:

```bash
TLS_SERVER_STORE_PASSWORD=changeit \
TLS_CLIENT_TRUSTSTORE_PASSWORD=changeit \
./gradlew bootRun
```

On **Windows PowerShell**, set the variables first, then run the wrapper:

```powershell
$env:TLS_SERVER_STORE_PASSWORD = "changeit"
$env:TLS_CLIENT_TRUSTSTORE_PASSWORD = "changeit"
.\gradlew.bat bootRun
```

The `changeit` password is only to make demo commands reproducible locally; never use it in production. If `server.p12` or `trusted-clients.p12` is missing or a password is wrong, Tomcat may fail to start HTTPS; that is a TLS configuration error, unrelated to Spring Security's user lookup.

## 5. End-to-End Testing with curl and Browser

### 5.1 With Valid alice Certificate

With a `curl` build whose TLS backend supports PKCS#12 (such as OpenSSL-backed builds), run:

```bash
curl -i \
  --cacert server.crt \
  --cert-type P12 \
  --cert alice.p12:changeit \
  https://localhost:8443/whoami
```

`--cacert server.crt` verifies the **server** certificate. `--cert-type P12 --cert alice.p12:changeit` loads the **client** certificate and private key. Never use `-k`/`--insecure` to "fix" trust errors in this lesson; commands should verify full HTTPS.

When both mTLS and account mapping succeed, the response contains HTTP **200 OK** and JSON equivalent to:

```json
{
  "username": "alice",
  "authorities": ["ROLE_READER"]
}
```

JSON key ordering may vary because `Map.of(...)` does not guarantee order. This is the **expected result under the sample config**, not a transcript recorded across all environments. If Windows `curl` uses another TLS backend (like Schannel), certificate/store import syntax may differ; check `curl -V` and that curl build's backend docs.

### 5.2 Without Sending a Client Certificate

```bash
curl -i --cacert server.crt https://localhost:8443/whoami
```

With `client-auth: need`, connections lacking a valid client certificate are usually **rejected at the TLS handshake**, before Spring Security processes HTTP. Depending on TLS version/curl, output may be a TLS alert or connection error; **do not insist on expecting HTTP 401**.

### 5.3 With a Certificate but Without Account Permissions

You can test adding a `CN=bob` client certificate trusted by the server **in a test environment**, while **not adding user `bob`** to `UserDetailsService`. mTLS can succeed, yet mapping the principal to an account fails. The HTTP result depends on the authentication entry point—possibly 401/403 or another configured auth response. This is an **application identity mapping error**, distinct from a PKI error on an untrusted certificate.

Even if `bob` exists without `ROLE_READER`, `/whoami` must be denied by `hasRole("READER")`. This demonstrates **valid certificate ≠ authorized**.

### 5.4 Desktop Browsers

When using Chrome/Edge/Firefox:

1. The browser must trust the corresponding **server certificate/CA**; self-signed demo certs need proper local trust.
2. Import client certificate `alice.p12` into the **personal certificate store used by the browser/OS**, protecting the private key. The browser may prompt to pick a certificate when requested by the server.
3. Open `https://localhost:8443/whoami`. If `alice` is selected and the handshake succeeds, the app maps the account just like `curl`.
4. On errors, check the Certificate/TLS panel in DevTools and Tomcat/Spring logs (with sensitive data redacted). Some browsers cache client certificate choices and reuse TLS sessions, so switching certs may require closing the session/browser context or testing independently with curl.

**Client certificates are not an arbitrary header set by JavaScript.** The private key must participate in the TLS handshake via the browser/OS or TLS library. Fetch APIs have no generic `clientCertificate: "alice"` option to construct mTLS from a string.

## 6. Subject DN Mapping: Strengths, Limits, and Production Design

### 6.1 Why Is CN Good for a Demo but Insufficient for Production?

Suppose two certificates are both issued by a trusted CA, one for `CN=alice,OU=Sales` and one for `CN=alice,OU=Contractor`. If config extracts only `CN=alice`, both map to the **same alice account**, even when business policy requires distinguishing them. Even with different issuers both inside the trust set, CNs can still collide.

Furthermore, DNs can contain escaped RDNs or normalization rules differing from a simple regex; renaming users or departments also changes subjects. High privileges must never be bound to CNs without uniqueness guarantees and trusted verification policies.

**Common production strategies:**

- **CA governance:** trust only CAs authorized to issue client certificates for the target app group; verify certificate profiles, EKUs, key usage, and revocation schedules. Never accept arbitrary public CAs just because a certificate is syntactically valid.
- **Unambiguous identifiers:** pick a stable PKI-managed certificate identity, such as an enterprise-standard SAN URI/otherName or issuer+serial details. Define how rotation/renewal transitions to a new cert while preserving accurate account mapping.
- **Backend mapping:** query a trusted directory/DB to bind certificate identity to account ID, active/disabled state, tenant, and roles; never auto-grant privileges from merely parsing a CN.
- **Never take authorities from clients:** `ROLE_ADMIN` or `tenantId` must originate from controlled policy/account stores, not caller-supplied text.
- **Monitoring and revocation:** manage expiration, revocation/lost private keys, cert replacement, role changes, and account deactivation; require session invalidation/re-auth when appropriate.
- **Verify trust level:** an issuer DN string alone is insufficient proof of "right CA"; rely on TLS trust validation and specific profiles/anchors.

If stronger mapping than CN regex is required, customize Spring Security's **X.509 principal extraction / pre-authenticated user-details resolution** to construct the principal from TLS-verified certificate fields and look up the account. Use proper DN/SAN parsers rather than ad-hoc regex string slicing. Preserve the trusted TLS validation path when swapping extraction mechanisms.

### 6.2 Distinguishing Account Identity from Certificate Issuance

Serial number + issuer identifies **a specific certificate issuance**, helpful for auditing and revocation, though renewal assigns a new serial. A stable SAN identity (per PKI profile) can be easier to bind to long-lived accounts, provided the CA controls it and the app validates semantics. A production mapping should define:

1. Which **User/Service ID** is the system's immutable identifier?
2. Which certificates are allowed to represent that ID?
3. On renewal/revocation/CA change/account lock, which mappings are updated or revoked?
4. How does the application verify current permissions after authenticating the certificate?

The certificate carries identity, whereas **authorization policy** is a separate decision based on account and resource.

## 7. Reverse Proxies, Load Balancers, and Trust Boundaries

The example above assumes the **TLS handshake terminates directly at embedded Tomcat**. In production, an ingress, WAF, or load balancer often terminates TLS:

```text
Client -- mTLS --> Ingress/LB -- HTTP/HTTPS --> Spring Boot
                        │                    │
                  Verifies cert        Servlet may NOT
                  at ingress           see X509Certificate[]
```

When TLS terminates at a proxy, the downstream servlet container typically **does not receive the raw client certificate directly** as with Tomcat mTLS. Thus, enabling `http.x509()` in the backend **is not enough** if requests lack a certificate attribute supplied by a trusted component.

There are two main architectural options:

- **TLS passthrough:** the proxy forwards TLS without terminating; Tomcat performs mTLS and sees the real client certificate. Requires infrastructure support and appropriate routing.
- **TLS termination and trusted identity forwarding:** the ingress verifies the client cert, then passes identity/certificate details over a **protected and authenticated backend channel** to the application; the backend must verify the sender and map that info via an explicit integration mechanism instead of blindly trusting arbitrary request headers.

**Critical security flaw:** letting Internet callers send `X-Client-Cert: CN=admin` and having the backend treat that string as an authenticated identity. HTTP headers can be **spoofed** if the backend is reachable directly or the proxy fails to strip client-sent headers.

To prevent spoofing:

1. The ingress must **verify the client certificate** against allowed CAs/policies and emit identity only after verification.
2. The proxy **strips/overwrites** all sensitive identity headers sent by clients; never merely "prepend a header" ahead of a caller-supplied one.
3. The backend accepts traffic exclusively from the trusted proxy, ideally via mTLS or a protected network channel; never expose a bypass route to Spring Boot.
4. Validate exact format/encoding of certificate DNs/headers; never parse untrusted strings loosely.
5. Place a trust-model-aligned **authentication adapter** to convert verified identity into `Authentication`, applying normal account mapping and authorization.
6. Monitor logging and audits around verified certificate identities; never log private keys, access tokens, or unnecessary personal details.

**Never treat `X-Forwarded-Proto`, `Forwarded`, or arbitrary "client-cert" headers as proof of X.509 authentication.** They can aid routing/URL generation, but never prove private key possession.

## 8. Combining X.509 with Sessions, CSRF, and Other Login Mechanisms

### 8.1 mTLS Authentication Does Not Replace Authorization

Spring Security populates `Authentication` after mapping the principal. Authorization still relies on request matchers/method security and service-level data checks. For example, `hasRole("READER")` only indicates the user holds the role; if an API reads an invoice by ID, the backend must still verify the user is authorized for **that specific invoice**.

### 8.2 mTLS Does Not Automatically Solve CSRF

When browsers automatically send cookies **or automatically select/remember client certificates** on TLS connections, client authentication acts as an **ambient credential** in the browser context. Another website can trigger requests from a victim's browser under certain conditions; therefore **never disable CSRF merely because the app uses X.509**.

In the sample configuration, Spring Security keeps default CSRF protection for state-changing methods. `GET /whoami` needs no CSRF token. If building a machine-to-machine API accepting only client certificates with **no browser/cookie credentials**, CSRF requirements may differ; evaluate separately and apply targeted security matchers/mechanisms rather than a blanket `csrf.disable()`.

### 8.3 Sessions and Certificates Have Different Lifecycles

Certificates expire, can be revoked, and TLS connections can be reused. Meanwhile, `SecurityContext`/sessions may retain authentication state depending on app configuration. When immediate revocation effectiveness is needed, design **session timeouts, re-authentication, account status checks, TLS revocation**, and revoke/rotate events—never assume certificates are re-checked on every HTTP request.

### 8.4 Multiple Authentication Mechanisms in One Application

An application may serve employees via X.509 and external users via OIDC, or services via mTLS and browsers via form login. Define explicit **endpoints, connectors, SecurityFilterChains, and authentication entry points** for each group. `client-auth: need` on a connector blocks clients without certificates before Spring runs, regardless of public controllers or `permitAll`. If the same hostname must serve both public browsers and mTLS, you generally need a properly separated ingress/connector/domain design.

**X.509 and OIDC are not interchangeable:** X.509 client certificates represent devices/services or PKI-backed user identities; OIDC delivers ID tokens and identity claims from an OpenID Provider. A valid certificate does not automatically grant OAuth2 scopes or OIDC roles, and an OIDC sign-in does not automatically provide a client certificate for mTLS.

## 9. Layer-by-Layer Error Diagnostics

| Symptom | Layer to check | Cause and remediation |
| --- | --- | --- |
| Server fails to start HTTPS | TLS configuration | Wrong path/password for `server.p12` or truststore, keystore lacks private key, unsuitable cert. Inspect startup logs safely. |
| Client gets TLS handshake error before any HTTP status | TLS client auth | Missing cert, untrusted client cert, expired, wrong EKU, or invalid chain. Check cert selection and server truststore. |
| curl reports certificate verify failed | Server verification | Client does not trust `server.crt` or SAN hostname mismatches. Use proper CA/cert trust and hostname; avoid `-k`. |
| mTLS succeeds yet request returns 401/403 | Spring authentication/authorization | Bad CN extraction, account not found, account disabled, or missing authority. Check user mapping and rules. |
| CN regex extracts wrong name | DN parsing | Subject contains escaped commas, complex structure, or unexpected RDNs. Use proper principal extractor/PKI identity parser. |
| User A's cert maps to User B's account | Identity binding | Comparing CN alone when CN is non-unique. Audit issuer, SAN/serial, and database/PKI mappings. |
| Spring sees no certificate behind ingress | TLS termination | Proxy verified cert without forwarding to Servlet container. Design trusted identity bridge or TLS passthrough. |
| Adding `X-Client-Cert` alone logs in | Broken trust boundary | Header can be spoofed. Block bypass, strip external headers, verify at proxy, protect backend hop. |
| GET works yet POST returns 403 | CSRF or permissions | With browsers/ambient credentials, valid CSRF token is required; do not lump every 403 into mTLS errors. |
| Expired/revoked cert still accesses session | Session/TLS lifecycle | Cache/session/connection reuse or unenforced revocation. Design session invalidation, revocation, and re-auth. |

### 9.1 Logging Layers to Observe

- **TLS/connector logs:** handshake causes, trust chains, certificate selection, hostname/server cert issues, revocation/validity failures.
- **Spring Security logs:** matched filter chain, principal after extractor, user lookup outcome, authorization decisions. Enable detailed logs **only in controlled debug environments**, then turn them off.
- **Application audit:** account ID, issuer/serial or normalized cert identifier, action, resource, outcome, request correlation. Avoid logging full subjects if unnecessary personal data is present.
- **Reverse proxy logs:** confirm client-auth is genuinely enforced at ingress and the backend cannot be called bypassing it.

When debugging, distinguish: **Did TLS even produce an HTTP request?** If not, do not edit `UserDetailsService`. If an HTTP request reached Spring with a null/wrong principal, check the attribute/certificate extractor/identity bridge. If the principal is right yet 403 occurs, check permissions and CSRF.

## 10. Process for Designing X.509 in Real Applications

| Question | Decision to document clearly |
| --- | --- |
| Who issues client certificates? | Internal CA, enterprise PKI, or authorized trusted issuer. |
| Who does the certificate identify? | Humans, machines, workloads, or devices; separate account/service identities may be needed. |
| Where does TLS terminate? | Tomcat directly or ingress/LB; who enforces PKIX/trust/revocation? |
| Where is the principal extracted from? | Demo CN vs. governed SAN/issuer+serial/identity profile. |
| How does the principal map to an account? | UserDetailsService or custom pre-auth mapping with active/roles/tenant status. |
| How do revocation/rotation work? | CA revocation, cert replacement, session invalidation, mapping updates, and auditing. |
| Are browsers involved? | If browsers use ambient credentials, check CSRF, sessions, and cert selection. |
| Are other identity sources present? | Separate filter chains/connectors/OIDC/APIs along clean boundaries. |

**Remember:** In Spring Security Servlet, X.509 authentication is **pre-authentication**: the **TLS endpoint** verifies the client certificate and proof of private key possession; **Spring Security** extracts the principal from the verified certificate, loads accounts/authorities, and enforces authorization. A `CN` regex suffices for learning the mechanism, whereas production demands governing **trust, unique identity mapping, revocation, rotation, sessions, and reverse-proxy trust boundaries**.
