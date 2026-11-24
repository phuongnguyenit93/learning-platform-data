# HTTPS, TLS certificates, and the limits of transport protection

> **Main point:** HTTPS uses TLS to protect data **in transit between the two ends of a TLS connection** and helps clients verify server identity via digital certificates. HTTPS **does not by itself authenticate users, perform business authorization, protect data after decryption, or make a vulnerable application secure**. In Spring Security applications, TLS is a mandatory foundation for properly transporting cookies, sessions, passwords, authorization headers, and tokens.

## 1. What should you understand and be able to do after this lesson?

- Distinguish HTTP, HTTPS, TLS, "SSL certificate," and X.509 certificates; understand the three main goals: **confidentiality, integrity, and server authentication**.
- Explain conceptually how a TLS handshake works, including hostname checking, certificate chains, and trust stores; know why seeing a padlock icon alone is not enough to conclude a website's content is trustworthy.
- Identify TLS boundaries when an application sits behind a load balancer/CDN/reverse proxy, when the proxy decrypts and forwards HTTP, and when multiple internal services exist.
- Configure Spring Boot to run HTTPS locally with a self-signed certificate, verify the certificate with `curl`, and contrast verified testing with `-k` skipping verification.
- Understand that HTTPS does not solve IDOR, XSS, SQL injection, CSRF, token leakage in logs, malware on endpoints, phishing websites with valid certificates, or data exposure where TLS has already terminated.

## 2. How do HTTP and HTTPS differ?

HTTP defines methods, URLs, headers, bodies, status codes, and request/response exchange semantics. When using plain HTTP on an untrusted network, anyone able to observe or modify traffic on the wire can read content and tamper with packets.

HTTPS = **HTTP running over a TLS-protected channel**, typically on port 443. With HTTP/1.1 and HTTP/2, TLS usually runs over TCP; HTTP/3 integrates TLS 1.3 with QUIC/UDP. "HTTPS" does not mean all traffic uses TCP.

| Capability | HTTP without TLS | HTTPS with properly configured and verified TLS |
| --- | --- | --- |
| Hide request/response content in transit | No | Yes, between the two TLS endpoints |
| Detect modification of data in transit | No cryptographic protection in HTTP | Yes, via TLS record integrity checks |
| Verify the server owns the connected domain | No | Yes, **if** the client verifies certificate, trust chain, and hostname |
| Automatically know who the logged-in user is | No | No; requires session, OAuth2/OIDC, Basic, mTLS, or appropriate mechanism |
| Automatically ensure the user can view a profile | No | No; requires server-side authorization |
| Automatically block SQL injection, XSS, CSRF, SSRF | No | No; must be handled at the application layer |
| Encrypt data after the server decrypts it | No | No; requires separate storage/processing policies |

Example:

```http
GET /account/balance HTTP/1.1
Host: bank.example
Cookie: SESSION=example-session-id
```

With a valid HTTPS connection, the HTTP path, headers, and body are protected by TLS while in transit between client and TLS endpoint. This prevents someone merely sniffing Wi-Fi traffic from directly reading the cookie or balance. However, the browser still knows the full URL; the server/proxy receiving and decrypting the request still sees it; malware in the browser, application logs, or XSS vulnerabilities can expose data at other points.

**Important:** A URL starting with `https://` only expresses the **intent to use TLS**. Actual security also depends on the connection negotiating successfully, the certificate being verified, the hostname matching, the endpoint being trustworthy, and all parties handling data safely.

## 3. What does TLS protect?

### 3.1. Confidentiality

TLS negotiates session keys and uses symmetric encryption for application data. With modern configurations, an observer capturing only encrypted packets generally cannot read the HTTP content. TLS 1.3 uses authenticated encryption ciphers (AEAD); algorithm and version selection must be properly configured by server/client.

This protection **ends at each TLS endpoint**. If a browser connects over HTTPS to a CDN, and the CDN sends plain HTTP to the backend, anyone controlling the CDN → backend segment can see the decrypted content. Protecting that segment too requires onward TLS or a managed network channel suited to the risk model.

### 3.2. Integrity

TLS detects tampering with encrypted records in transit. An intermediary cannot arbitrarily alter `amount=100` to `amount=100000` inside an authenticated session and pass integrity checks. However, a **valid client** can still submit an unauthorized amount itself. The server must validate values, ownership, state, and business rules.

### 3.3. Server authentication

The client checks the X.509 certificate provided by the server to verify that the server it connected to is authorized to use the requested domain name within a PKI system trusted by the client. In a typical web HTTPS connection, the **client does not automatically present a certificate**; mTLS is an additional configuration. HTTPS protects passwords/tokens in transit, but does not replace user authentication and authorization.

### 3.4. Information that may still be observable

TLS does not guarantee hiding all metadata: destination IP address, record count/timing/size, standard DNS queries, and in many setups the hostname in SNI can still be observed. Mechanisms like encrypted DNS and Encrypted ClientHello (ECH) can reduce some exposure depending on support and configuration; plain HTTPS **does not mean every access trace is hidden**. The specific URL path/query contents are encrypted inside the HTTP exchange, though DNS services, endpoint operators, or decrypting proxies can observe data within their scope.

## 4. How do the TLS handshake and digital certificates work?

### 4.1. Basic flow with TLS 1.3

```text
Client / Browser                                  Server / HTTPS endpoint
     |  ClientHello: supported versions, groups,  |
     |  key share, SNI, ALPN...                   |
     |------------------------------------------->|
     |               ServerHello: params, key share|
     |<-------------------------------------------|
     |   [EncryptedExtensions, Certificate,       |
     |    CertificateVerify, Finished ...]        |
     |<-------------------------------------------|
     |  Verify hostname, trust chain, signature   |
     |  Finished, establish session keys          |
     |------------------------------------------->|
     |          HTTP request (encrypted)          |
     |------------------------------------------->|
     |          HTTP response (encrypted)         |
     |<-------------------------------------------|
```

This is a conceptual diagram for a full TLS 1.3 handshake. TLS 1.2, session resumption, and HTTP/3 differ in details. In practice, handshake messages may be packaged and sent across different flights/records.

1. **ClientHello** announces supported versions, key groups, cipher suites, and usually SNI (the target server hostname). ALPN may be used to negotiate protocols like `h2` or `http/1.1`.
2. **ServerHello** selects parameters and exchanges key material so both sides derive session keys. Ephemeral key exchange mechanisms (such as ECDHE) in modern TLS support **forward secrecy**: later compromise of the certificate's private key does not automatically decrypt previously recorded sessions.
3. The server presents its certificate and proves possession of the corresponding private key. The client checks the certificate and chain against its trust store, matches the requested host identity, validity period, and relevant constraints.
4. Both sides verify `Finished` messages to confirm the handshake was not altered and they hold identical keys; HTTP traffic then flows over the TLS channel.
5. Sessions can be resumed to reduce handshake round-trips. In TLS 1.3, **if 0-RTT early data is enabled**, it carries replay risk; sensitive/non-idempotent operations must avoid allowing 0-RTT or enforce dedicated replay protection. The example below does not enable this feature.

**Do not equate TLS with "encrypting only with the public key":** the public/private key pair in the certificate primarily participates in authentication/signing, while HTTP traffic is protected using **symmetric session keys**, which perform much better.

### 4.2. What does an X.509 certificate contain?

A server TLS certificate typically contains:

- **Subject Alternative Name (SAN):** the list of DNS names/IPs the certificate may represent. Modern hostname matching relies on SAN; one should not rely solely on `CN`.
- Server's **public key**, signature algorithm, issuer, serial number, `Not Before` and `Not After` timestamps.
- Extensions expressing intended usage (e.g., server authentication) and X.509 constraints.

The corresponding **private key** stays on the server or in a key management system; it **does not** appear in the public certificate. Keeping the private key secret matters more than hiding certificate contents. PEM certificate files can be public; private keys and keystore files containing private keys must be protected.

### 4.3. Trust chain and hostname verification

```text
Client trust store
  Trusted Root CA
       |
       +-- Intermediate CA
                |
                +-- Certificate of api.example.com (SAN: api.example.com)
                                   |
                           Client calls https://api.example.com
                           + verify signature/chain/expiry/usage
                           + hostname matches SAN
```

A server may send its server (leaf) certificate and intermediates. The client builds a chain to a trust anchor that the **client** trusts; the root does not necessarily have to be sent by the server. Beyond signature chains, verification must satisfy hostname, validity period, and key usage/extension constraints. Revocation checks (OCSP/CRL) have varying support across clients/policies, so do not assume **every** client immediately rejects a revoked certificate.

Risk examples:

- A certificate valid for `shop.example.com` is **not** valid for `payment.example.net` if the SAN does not contain that name, even if both share the same operator.
- Browser warnings like "certificate expired" or "hostname mismatch" are trust-boundary failures, not UI errors to click past casually.
- A **self-signed** certificate is not inherently cryptographically flawed, but clients must explicitly establish trust; production typically uses a CA trusted by target clients or a managed internal PKI.
- A site having a valid certificate only proves control of the identifier per the issuance mechanism; it **does not confirm the site is a real bank, a reputable business, or harmless content**. Phishing sites can still use HTTPS.

### 4.4. "SSL certificate" and certificate lifecycle

"SSL certificate" is a common colloquial term, but the protocol used in modern deployments is **TLS**. Legacy SSL versions are obsolete; prefer TLS 1.3 and TLS 1.2 with strong configurations compatible with needs. Do not re-enable SSLv3/TLS 1.0/1.1 to "fix" an outdated client without evaluating risks.

Operations do not end after buying or generating a certificate: you must manage private keys, verify domains and chains, automate issuance/renewal, monitor expiration dates, update configs when changing proxies, revoke/replace compromised keys, and avoid putting private keys/keystores with real passwords into Git, images, or logs.

## 5. Where does TLS terminate in a Spring Boot architecture?

### 5.1. TLS directly in the application

```text
Browser  -- HTTPS/TLS -->  Spring Boot embedded server
                            (TLS private key on server)
                            |
                            +--> Spring Security filter chain
                            +--> Controller / Service / Database
```

The application holds its own certificate/keystore and HTTPS port. This model is easy to learn and fits some deployments, though production often uses a gateway/ingress responsible for TLS certificate lifecycle.

### 5.2. TLS termination at a proxy or CDN

```text
Browser --HTTPS--> Load balancer / CDN / reverse proxy
                     | Decrypts TLS, sees HTTP path/header/body
                     |
                     +--Internal HTTP--> Spring Boot
                            or
                     +--HTTPS/TLS------> Spring Boot
```

**Only the browser → proxy segment is protected by the first TLS layer.** If proxy → app runs HTTP, data on that leg is plaintext; you must evaluate the internal network, eavesdropping risks, compliance requirements, and sensitivity to decide whether to use onward HTTPS or mTLS. Backend HTTPS connections also need proper backend identity verification, avoiding "encryption enabled without authentication."

When a proxy terminates TLS, Spring Boot may see the incoming connection as HTTP and treat `request.isSecure()` as `false`. `Forwarded`/`X-Forwarded-Proto` headers help the app know the original scheme **only when properly set/overwritten by a trusted proxy**. If an Internet-facing server lets clients submit `X-Forwarded-Proto: https` and trusts it blindly, an attacker can influence redirects, absolute URLs, cookie policies, or defenses depending on "secure request."

With Spring Boot, `server.forward-headers-strategy` can be set per infrastructure (`native`/`framework`) to process forwarded headers, but enable it only after ingress normalizes headers, direct unauthorized backend access is blocked, and trusted proxies are defined. Never assume client-sent headers prove a TLS connection was secure.

### 5.3. TLS and mTLS

- Standard HTTPS authenticates the server to the client. Users still must log in via sessions, OAuth2/OIDC, tokens, or an appropriate mechanism.
- **mTLS** adds a step where the client presents a certificate so the server authenticates the client identity at the TLS boundary. It is useful for service-to-service or managed devices.
- A client certificate does not automatically mean "allowed to view this invoice"; you still need to map certificate identity to a principal and check permissions/owner/tenant in the service.
- If mTLS terminates at a proxy, the backend must receive client info over a trusted channel and must never accept spoofed headers from the Internet. Every certificate-trust decision must align with real network boundaries.

## 6. Runnable example: Spring Boot HTTPS and certificate verification

This example demonstrates at once:

1. A Spring Boot server listening on HTTPS directly on port `8443`.
2. A self-signed certificate used **only on the learning machine** with SANs for `localhost` and `127.0.0.1`.
3. The client verifying certificate/hostname using `curl --cacert`; if untrusted, the connection fails before valid HTTP requests are exchanged.
4. Spring Security requiring login for a private endpoint. TLS authenticates the server, Basic Auth authenticates the user, and authorization governs which endpoint can be called.

**Illustrative versions:** Java 17, Spring Boot **3.3.13** (a real release, though the 3.3.x branch reached end of open-source support on June 19, 2025). This pinned version helps reproduce the lesson; production projects must pick a supported Spring Boot line and current patches. Passwords `changeit` and `demo-pass` are for local examples only.

### 6.1. Project structure

```text
tls-demo/
├── pom.xml
├── localhost.crt                       # public certificate for curl to trust locally
└── src/main/
    ├── java/demo/tls/HttpsDemoApplication.java
    └── resources/
        ├── application.properties
        └── tls/local-keystore.p12       # contains PRIVATE KEY, local use only
```

### 6.2. Maven dependencies

Create `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>tls-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
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

### 6.3. Generate a self-signed certificate for local use

Before running, create the `src/main/resources/tls` directory via IDE or terminal; open a terminal in `tls-demo`. Run the following JDK `keytool` command on **one line** (works in PowerShell or Bash):

```bash
keytool -genkeypair -alias localdev -keyalg RSA -keysize 3072 -validity 30 -storetype PKCS12 -keystore src/main/resources/tls/local-keystore.p12 -storepass changeit -keypass changeit -dname "CN=localhost" -ext "SAN=dns:localhost,ip:127.0.0.1"
```

This command generates a private key and a public certificate with SAN. To export **only the public certificate** for the client:

```bash
keytool -exportcert -rfc -alias localdev -keystore src/main/resources/tls/local-keystore.p12 -storepass changeit -file localhost.crt
```

Inspect the certificate details:

```bash
keytool -list -v -alias localdev -keystore src/main/resources/tls/local-keystore.p12 -storepass changeit
```

When printed, you should see `Owner: CN=localhost`, `Issuer: CN=localhost` (self-signed), SAN containing DNS `localhost` and IP `127.0.0.1`, and an expiration period of about 30 days from creation. Exact text formatting depends on the JDK version.

**Security boundary:** the `.p12` file holds the private key; `localhost.crt` only holds the public certificate. In real projects, private keys/keystores must be protected via proper access permissions, a secret manager, or infrastructure key stores; do not commit them to repositories. Self-signed local certificates are unsuitable for public deployment, and illustrative passwords must never be used in production.

### 6.4. Configure HTTPS in Spring Boot

Create `src/main/resources/application.properties`:

```properties
server.port=8443
server.ssl.enabled=true
server.ssl.key-store=classpath:tls/local-keystore.p12
server.ssl.key-store-type=PKCS12
server.ssl.key-store-password=changeit
server.ssl.key-alias=localdev
server.ssl.enabled-protocols=TLSv1.3,TLSv1.2
```

`server.ssl.*` configures Spring Boot's / embedded servlet container's **server connector**. They set up TLS on port 8443; they do not create an HTTP listener on port 8080 and **do not automatically create an HTTP → HTTPS redirect**. Redirecting from HTTP port 80 to 443 must be configured at the proxy/ingress or via a separate HTTP connector if operationally warranted.

### 6.5. Complete Java code

Create `src/main/java/demo/tls/HttpsDemoApplication.java`:

```java
package demo.tls;

import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class HttpsDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(HttpsDemoApplication.class, args);
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/status").permitAll()
                .requestMatchers("/private").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("demo-pass"))
                .roles("USER")
                .build()
        );
    }
}

@RestController
class TlsController {
    @GetMapping("/status")
    Map<String, Object> status(HttpServletRequest request) {
        return Map.of(
            "scheme", request.getScheme(),
            "secure", request.isSecure()
        );
    }

    @GetMapping("/private")
    String privateMessage(Authentication auth) {
        return "Hello " + auth.getName();
    }
}
```

**Why are both TLS and Spring Security needed?**

- TLS protects requests/responses **over the HTTPS connection to the server** and verifies the server certificate on the client side.
- `HttpSecurity.authorizeHttpRequests` decides which endpoints are public and which require authentication. It does not provide HTTPS if the server/proxy has not configured TLS.
- `httpBasic` authenticates the user. Basic Auth only Base64-encodes credentials and **does not encrypt credentials on its own**; HTTPS is essential when transmitting Basic Auth. Production typically needs stronger authentication mechanisms, access control, rate limits, and MFA when needed.
- `Map.of` helps observe scheme and secure status on the server side. It is useful for illustration when the app receives TLS directly, though behind a reverse proxy you must consider forwarded headers/trust boundaries.
- With Spring Security Servlet, default security headers usually include HSTS on HTTPS responses; the application still needs to verify headers in the actual deployment infrastructure, especially when TLS terminates at a proxy.

### 6.6. Run and test

Requires **JDK 17+**, Maven 3.6.3+, and a terminal in the project directory:

```bash
mvn spring-boot:run
```

On Linux/macOS/Git Bash use `curl`. On Windows PowerShell 5.1, use `curl.exe` instead of PowerShell's `curl` alias.

**Case A — client explicitly trusts the local certificate:**

```bash
curl -i --cacert localhost.crt https://localhost:8443/status
```

Once the application has started and the certificate is valid, expect HTTP status **200** with JSON containing `"scheme":"https"` and `"secure":true`. JSON key order and headers may vary; byte-for-byte matching is unnecessary.

**Case B — no trust configured for the self-signed certificate:**

```bash
curl -i https://localhost:8443/status
```

On a machine that does not yet trust the local root/certificate, the connection is usually rejected due to failing trust chain verification (e.g., curl error 60). That is **proper protective behavior**, not a reason to disable certificate verification in the application.

**Case C — hostname does not match SAN:**

```bash
curl -i --cacert localhost.crt --resolve wrong.example.test:8443:127.0.0.1 https://wrong.example.test:8443/status
```

`--resolve` only forces the client to the loopback IP, while the TLS hostname remains `wrong.example.test`. Since the certificate only has SANs `localhost` and `127.0.0.1`, the request must **fail hostname verification**. If curl uses a system proxy, disable the proxy for local test names via appropriate environment configuration.

**Case D — TLS works, yet the API still requires login:**

```bash
curl -i --cacert localhost.crt https://localhost:8443/private
curl -i --cacert localhost.crt -u alice:demo-pass https://localhost:8443/private
```

Expect the first command to receive **401** per the HTTP Basic challenge; the second command receives **200** and body `Hello alice`. Both requests traverse valid TLS; they differ in having credentials accepted by the server. Being able to view `/private` does not mean the user is authorized to read all business data in a real application.

**Case E — plain HTTP on a TLS-only port:**

```bash
curl -v http://localhost:8443/status
```

No JSON is returned over plain HTTP; the server may close the connection or return a protocol error because it requires TLS. This does **not** demonstrate an HTTP → HTTPS redirect. To verify redirects, test a separately configured HTTP listener/proxy.

**Warning about `-k`/`--insecure`:** `curl -k` skips certificate verification and can turn an encrypted connection into a connection to the **wrong server** without the client detecting it. Only use it for narrow diagnostics in test environments, never as a "fix" for applications or production scripts. For local self-signed certs, use `--cacert localhost.crt` as shown above.

## 7. HSTS, HTTPS redirects, and secure cookies

### 7.1. HTTP → HTTPS Redirect

A public deployment usually receives HTTP requests on port 80 and redirects to HTTPS with **301/308** (code depends on design); the client then connects to the new HTTPS URL. Redirecting is a server/proxy decision and **does not protect the initial HTTP request** by itself: if a client sends a password/token over HTTP before the redirect, it may already be exposed. Generate links, form actions, API base URLs, and callback URLs with HTTPS from the outset; avoid accepting requests containing credentials over HTTP.

### 7.2. HTTP Strict Transport Security (HSTS)

Example header:

```http
Strict-Transport-Security: max-age=31536000; includeSubDomains
```

After the browser receives a valid HSTS header over HTTPS, the browser is instructed to automatically upgrade future visits to that host to HTTPS for `max-age`. Depending on policy, `includeSubDomains` extends scope to subdomains; `preload` involves submitting the host to browser preload lists and carries separate operational requirements. **Do not enable includeSubDomains/preload recklessly** if any subdomain does not support HTTPS yet.

Limitations of HSTS:

- An HSTS HTTP header sent over **plain HTTP** is not treated as a trusted signal to activate the policy.
- Standard HSTS only takes effect **after the browser has learned the policy** from a valid HTTPS connection. Preload can protect the first visit for domains included in the list with supporting browsers.
- HSTS does not turn an invalid certificate into a valid one, does not protect the app from XSS/authorization flaws, and is not a user authentication mechanism.
- Browsers and custom HTTP clients may handle HSTS differently; `curl` should not be considered a full simulation of browser HSTS behavior.

Spring Security supports writing the HSTS header on secure responses (when the request is recognized as HTTPS), but **does not configure the TLS server or infrastructure-wide redirects itself**. In architectures with a reverse proxy, inspect HSTS on the response that **the browser actually receives**.

### 7.3. Cookies and tokens

For logins using session cookies, set appropriate attributes:

- `Secure`: browser only sends the cookie over secure connections per cookie rules.
- `HttpOnly`: restricts JavaScript from directly reading the cookie; does not stop XSS from making requests on the user's behalf.
- `SameSite`: helps reduce certain cross-site cookie-sending cases, but does not fully replace CSRF protection for every application.
- Limit `Domain`/`Path`, lifetime, rotation, and session fixation per risk model. Use the `__Host-` cookie prefix when Secure, Path, and no-Domain requirements fit.
- Do not put access tokens, passwords, or session secrets in query strings because queries can appear in history, access logs, analytics, exceptions, and observability systems after TLS termination.

If the frontend holds bearer tokens where JavaScript can read them, HTTPS only protects the token in transit; malware/XSS on the origin can still access the token. Storage strategy, XSS defense, and token lifetime/revocation must be evaluated separately.

### 7.4. Mixed content, WebSockets, and external links

A page loaded over HTTPS that calls scripts, images, iframes, or APIs over HTTP can hit **mixed content**. Browsers may block or auto-upgrade certain content types depending on standards/policies; do not rely on auto-upgrade to guarantee all dependencies are safe. Use HTTPS URLs for resources; when using WebSockets from an HTTPS page, choose `wss://` when the connection must be encrypted. Audit file download links, webhook callbacks, redirects, and backend connections individually.

## 8. Which risks does HTTPS not protect against?

| Scenario | Does HTTPS solve it? | Corresponding mitigation |
| --- | --- | --- |
| Third party sniffing requests between browser and TLS endpoint | **Yes**, if TLS verifies properly | Strong TLS, hostname/certificate verification, key protection |
| Attacker modifying responses in the middle of a valid TLS connection | **Detected/blocked** at TLS layer | Configure appropriate protocol versions/cipher suites |
| Logged-in user reading another user's document by changing an ID | **No** | Server-side authorization by user/action/resource/tenant |
| SQL injection via query/form | **No** | Prepared statements, parameter binding, validation |
| XSS in HTML returned over HTTPS | **No** | Context-aware output encoding, HTML sanitization, appropriate CSP |
| CSRF from a browser with session cookies | **No** | CSRF tokens/cookie design and appropriate Origin/Fetch Metadata checks |
| Lookalike phishing site with deceptive domain and valid cert | **No** | Verify real domains, anti-phishing controls, brand monitoring |
| Reverse proxy decrypts TLS then sends plaintext to backend | **Does not protect post-proxy leg** | HTTPS/mTLS between hops or controlled trusted network |
| API key/password/token written into logs or crash dumps | **No** | Masking, log restriction, secret management, retention |
| Compromised server private key | **Cannot self-heal** | Incident response, rotate keys/certificates, revoke where possible |
| Malware-infected client/server machine | **No** | Endpoint security, hardening, patching |
| Authorized user intentionally abusing data after decryption | **No** | Least privilege, audit, data minimization, monitoring |
| Replay of a valid business transaction | **Not guaranteed automatically** | Idempotency, nonce/expiry if needed, state machine, transactions |
| Data sitting in databases, backups, uploaded files | **No** | Encryption at rest when needed, access control, storage permissions |
| DoS/resource exhaustion attacks | **Not comprehensively** | Rate limits, quotas, WAF/edge capacity, timeouts, circuit breakers |

Clear example: `POST https://api.example.com/transfer` travels over TLS so nobody can alter it in transit, yet a validly logged-in attacker can still send a negative amount or transfer from an account they do not own if the backend lacks validation/authorization. **TLS did its job; the bug lies in business logic.**

Similarly, the browser displays a padlock when visiting a phishing website issued a certificate for the attacker's own domain. The certificate proves "connected to the exact domain in the address bar per PKI," **not that the domain belongs to the organization the user has in mind**.

## 9. Common implementation mistakes

### 9.1. Disabling certificate verification "just to make it work"

Wrong: `curl -k` in production pipelines, HTTP clients using trust-all managers, or disabling hostname verification. This destroys server identity guarantees and invites man-in-the-middle attacks. Right: issue proper certificates, send full intermediates, configure trust stores/internal CAs, and ensure SANs match connection names. Never embed "trust any certificate" as a default.

### 9.2. Enabling HTTPS only at the outer door, forgetting downstream hops

Software sees `https://` on the external URL and assumes proxy → service and service → database/message broker connections are all encrypted. Right: draw the entire data flow diagram, mark TLS termination points, and specify credentials, CAs, mTLS/hostname verification, and access rights on **each connection** needing protection.

### 9.3. Using forwarded headers without a trust boundary

Wrong: letting Internet clients send `X-Forwarded-Proto: https` or `X-Forwarded-Host` and having Spring trust them immediately. Right: ingress overwrites/strips client-sent headers, direct backend access is blocked, trusted proxies are configured, and redirects/cookies/security headers are checked via integration tests behind the proxy.

### 9.4. Letting server certificates expire or misconfiguring SANs

Wrong: checking only that a `.p12` file exists without checking chain/hostname/expiry, or renewing while forgetting to reload the proxy. Right: automate issuance/renewal, monitor expiry, verify handshakes post-deploy, test against actual production hosts, and maintain rollback/rotation procedures.

### 9.5. Thinking HTTPS already solves sessions and CSRF

Wrong: assuming passwords/tokens traveling over HTTPS is enough even if cookies lack proper flags, tokens are logged, session expiry is missing, the app has XSS, or POST endpoints lack CSRF protection. Right: keep web/app defenses independent, test permissions and sessions, and verify cookies/CSRF according to the authentication method.

### 9.6. Enabling HSTS/preload before subdomains are ready

Wrong: applying `includeSubDomains` for an organization with many internal HTTP-only services, making browsers unable to reach them. Right: inventory DNS/subdomains, align on a unified HTTPS strategy, test rollouts, and treat preload as a lifecycle decision that is hard to undo quickly.

### 9.7. Confusing data encryption with verifying the right server

Wrong: seeing TLS-encrypted traffic while trusting all certificates; an attacker can establish a separate TLS session with the client and decrypt that session's traffic. Right: verify chain, SAN, validity period, cert purpose, and trust policy; encryption and **endpoint authentication** are both required simultaneously.

## 10. Checklist when taking HTTPS/Spring Security to production

1. **All entry points:** do site, API, admin, file uploads, WebSockets, and auth callbacks actually use HTTPS/WSS? Does any HTTP endpoint receive secrets before redirecting?
2. **TLS termination:** at CDN, ingress, app, or service mesh? Does every hop need TLS? Are hostname verification and client/server trust properly configured at the backend?
3. **Certificates:** do SANs match real names, is the chain complete, is the private key protected, and are auto-renewal and expiry alerts in place?
4. **Protocols:** TLS 1.3 preferred and TLS 1.2 only when needed; weak protocols/ciphers removed; compatibility verified with valid clients.
5. **Redirect/HSTS:** HTTP → HTTPS implemented at the right layer; HSTS safe for subdomains too; browser effectiveness and readiness checked?
6. **Forwarded headers:** does backend only trust headers normalized by trusted ingress; is proxy bypass blocked; do URLs/cookies/redirects render the right scheme?
7. **Cookies/tokens:** Secure, HttpOnly, SameSite, lifetimes, revocation; no credentials written to URLs, logs, or telemetry?
8. **Application:** are Spring Security authentication/authorization, CSRF where needed, validation, and XSS/SQL injection/IDOR defenses still covered by tests?
9. **Failure cases:** are wrong-hostname, expired, or untrusted certificates rejected by clients? Has anyone slipped `-k` or trust-all into production?
10. **Operations:** is there monitoring for handshake errors, certificate expiry, key rotation, misdirected redirects, post-proxy config checks, and key-compromise incident procedures?

A `MockMvc` test seeing `isSecure() == true` on a mocked request **does not prove** the real server has TLS open or a valid cert. To test transport, use a **real network connection** from a client trusting the appropriate CA (curl/browser/HTTPS integration test); to test user/resource policies, additionally use Spring Security tests at the controller and service layers. The two test groups have different goals.

## 11. Core knowledge summary

1. **HTTPS = HTTP over TLS**, protecting confidentiality and integrity of data in transit within the scope of **both ends of a TLS connection**.
2. X.509 certificates, trust chains, SAN hostnames, validity periods, and signature checks let clients verify servers; encrypting while disabling verification is **not enough**.
3. When TLS terminates at a proxy/CDN, **every downstream hop** must be evaluated. Forwarded headers must be set by trusted components.
4. HSTS and redirects help browsers use HTTPS more consistently; they do not configure TLS by themselves and do not replace auth, authorization, CSRF, or secure coding.
5. HTTPS is a **transport-layer defense**. Resource access rights, transaction validity, stored data safety, and endpoint protection remain the responsibility of the application and infrastructure.

## References

- [Spring Security — HTTP Security Response Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html)
- [Spring Boot — Configure SSL](https://docs.spring.io/spring-boot/how-to/webserver.html#howto.webserver.configure-ssl)
- [MDN — Transport Layer Security](https://developer.mozilla.org/en-US/docs/Web/Security/Transport_Layer_Security)
- [MDN — Strict-Transport-Security](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Strict-Transport-Security)
- [OWASP — Transport Layer Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html)
- [Spring Boot 3.3.13 release (2025-06-19)](https://spring.io/blog/2025/06/19/spring-boot-3-3-13-available-now/)
