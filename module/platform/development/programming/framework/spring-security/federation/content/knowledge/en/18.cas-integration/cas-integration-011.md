# Securing the HTTPS Connection Between the Application and the CAS Server

In **Central Authentication Service (CAS)**, an application using the **Spring Security CAS client** does not merely redirect the browser to the CAS server for user login. After receiving a **Service Ticket (ST)**, the application also sends a **server-to-server** request to CAS to validate the ticket. Therefore, HTTPS security for CAS involves **two distinct TLS clients**: the user's browser and the **JVM running the Spring application**.

A browser showing an HTTPS lock at `https://sso.example.org` **does not prove** that Portal's JVM trusts that certificate. Browsers and JVMs can use different truststores. Conversely, if the CAS client is configured to skip certificate or hostname checks, a man-in-the-middle (MITM) attacker can return forged `authenticationSuccess` XML, tricking the application into trusting a user who never authenticated at CAS.

**Objective:** establish proper CAS trust boundaries using HTTPS/TLS, PKIX certificate chains, Subject Alternative Names (SAN), truststores, callback URLs, reverse proxies, and negative testing. This article belongs to **CAS Integration**, using Spring Security Servlet, Apereo CAS, and Java 17+ examples. `.example` domains are illustrative placeholders, not live endpoints.

## 1. Three Core HTTPS Legs in CAS Login

~~~mermaid
sequenceDiagram
    participant U as Browser
    participant SP as Spring Security Portal
    participant CAS as CAS Server
    U->>SP: HTTPS GET /reports
    SP-->>U: Redirect to CAS login and service URL
    U->>CAS: HTTPS GET /cas/login?service=...
    CAS->>CAS: Authenticate user / reuse TGC
    CAS-->>U: Redirect to service with ST-...
    U->>SP: HTTPS GET /login/cas?ticket=ST-...
    SP->>CAS: HTTPS GET /cas/serviceValidate?ticket=...&service=...
    CAS->>CAS: Verify ST, service, timeout, and single-use
    CAS-->>SP: HTTPS XML authenticationSuccess / failure
    SP->>SP: Build Authentication, check local user/roles
    SP-->>U: Secure session cookie
~~~

What to understand:

1. **Browser -> SP:** browser verifies Portal's TLS certificate.
2. **Browser -> CAS:** browser verifies CAS's TLS certificate when visiting the login UI.
3. **SP -> CAS:** **Java HTTP client inside Spring** verifies the CAS certificate when validating the ST via `TicketValidator`. This is the back-channel path deciding whether the app may trust the XML response.

If using **CAS Proxy Authentication**, there is a fourth leg: **CAS -> SP** when CAS calls `pgtUrl` (the Proxy Granting Ticket callback). At that point CAS becomes the HTTPS client and must verify the SP's certificate.

### Certificate Verification Matrix

| Connection | HTTPS Client | HTTPS Server | Where Trust Must Be Configured |
| --- | --- | --- | --- |
| Browser -> Portal | Browser | SP / load balancer | Browser/OS trust store |
| Browser -> CAS Login | Browser | CAS / ingress | Browser/OS trust store |
| **Spring -> CAS Validator** | **SP JVM** | **CAS server** | **JVM or CAS client's TLS transport** |
| CAS -> SP proxy callback, if used | CAS HTTP client | SP proxy receptor | **CAS-side truststore** |
| Ingress -> SP/CAS backend | Reverse proxy | Backend | Proxy trust config, if backend uses TLS |

**Never use the SP's certificate to "solve" `PKIX` errors on SP -> CAS**, unless both genuinely share a verified CA. SP -> CAS must trust **CAS identity**; CAS -> SP must trust **SP identity**.

## 2. CAS Protocol: Ticket Validation and the Role of HTTPS

The CAS Protocol uses these elements:

- **Ticket Granting Ticket (TGT):** represents the SSO session at CAS; browsers typically reference it via the `TGC` cookie.
- **Service Ticket (ST):** short-lived, opaque value issued for **one specific service URL**, normally single-use.
- **`service` parameter:** callback URL for which CAS issued the ticket; must match during validation.
- **`/serviceValidate`:** CAS 2.0 endpoint returning an XML response.
- **`/p3/serviceValidate`:** CAS 3 variant returning additional attributes per service/attribute release configuration.
- **`/proxyValidate`:** endpoint for approved proxy flows; not needed by every app.

Distinct URLs:

~~~text
CAS server base:
  https://sso.example.org/cas

CAS login:
  https://sso.example.org/cas/login

CAS ticket validator:
  https://sso.example.org/cas/serviceValidate
  or https://sso.example.org/cas/p3/serviceValidate

Spring application's registered CAS service callback:
  https://portal.example.com/login/cas
~~~

An SP -> CAS validation request:

~~~http
GET /cas/serviceValidate?service=https%3A%2F%2Fportal.example.com%2Flogin%2Fcas&ticket=ST-DEMO HTTP/1.1
Host: sso.example.org
Accept: application/xml
~~~

CAS returns XML, for example:

~~~xml
<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">
  <cas:authenticationSuccess>
    <cas:user>employee-123</cas:user>
  </cas:authenticationSuccess>
</cas:serviceResponse>
~~~

**`ST-DEMO` and the XML above are illustrative only, not a real transaction.** An attacker can easily craft XML that looks like that. Spring must build `Authentication` only after a **standard ticket validator** actually sent the request over **HTTPS to a trusted CAS server**, checked ticket/service, and received and parsed a valid response. Never create authentication from a form parameter `user=employee-123` or an HTTP response that bypassed trust verification.

### Why Is HTTPS Still Essential Even When Tickets Are "Single-Use"?

A Service Ticket is still a sensitive credential. A network attacker could steal the ST before the SP validates it, or spoof the CAS validator endpoint to return a fake `authenticationSuccess`. Ticket binding, one-time usage, and TLS protect different invariants:

| Mechanism | Role |
| --- | --- |
| **HTTPS + PKIX + hostname** | Authenticates the real CAS endpoint and protects request/response integrity and confidentiality |
| **Service binding** | ST works only for the service to which it was issued |
| **One-time / TTL** | Limits ST replay and lifetime |
| **CAS registered-service policy** | Only approved services may participate in SSO |
| **Spring local authorization** | App/tenant permissions evaluated after CAS authentication |

Never disable `service` matching or accept old STs just because "HTTPS is already enabled."

## 3. What Does HTTPS Actually Verify?

When the CAS client connects to `https://sso.example.org/cas`, TLS must verify:

1. **Certificate chain:** the CAS certificate chains through required intermediate CAs to a **CA trust anchor** approved by the client.
2. **Validity:** the certificate is within `NotBefore` and `NotAfter`, with a trustworthy host clock.
3. **Server name matching:** the certificate contains **SAN `dNSName=sso.example.org`** or an identity matching HTTPS rules; never accept a certificate issued solely for another hostname.
4. **Signatures and PKI policy:** valid chain signatures, appropriate key usage and extended key usage, and permitted algorithms/key sizes.
5. **TLS protocol/cipher:** must not negotiate versions or ciphers disabled by the JDK/security baseline.
6. **Revocation (if mandated):** enforce OCSP/CRL policy and failure mode per PKI standards; do not assume all JDKs check revocation identically.
7. **Authentic target:** the connection goes strictly to the configured CAS base URL, never an arbitrary server chosen by a user request.

**A URL starting with `https://` is not enough on its own.** If code installs an `X509TrustManager` accepting any CA or a `HostnameVerifier` returning `true` unconditionally, HTTPS loses its ability to prove the server is the trusted CAS server.

### Certificate Chain and Hostname Are Two Separate Checks

Example:

~~~text
Target URL: https://sso.example.org/cas

Certificate A:
  Valid public CA chain: YES
  SAN: other.example.org
  Result: REJECT (hostname mismatch)

Certificate B:
  SAN: sso.example.org
  Trusted issuer/root: NO
  Result: REJECT (PKIX path building failure)

Certificate C:
  SAN: sso.example.org
  Trusted chain: YES
  Within validity window: YES
  TLS algorithms allowed: YES
  Result: may proceed to HTTP/CAS validation
~~~

No certificate by itself proves an ST is valid; Case C **only clears the TLS gate**, and the application must still verify the CAS ticket response.

### SAN, CN, and IP Addresses

Always use Subject Alternative Name rather than relying solely on `CN=sso.example.org` when issuing new certificates. If a client connects by IP address, the certificate needs a matching **IP SAN** per HTTPS rules. Never "fix" a hostname mismatch by disabling SNI or the hostname verifier and leaving it disabled in production.

When multiple vhosts sit behind a reverse proxy, `Server Name Indication (SNI)` lets the proxy select the matching host certificate; `openssl s_client -servername sso.example.org` is useful for diagnostics. If the proxy returns another site's default certificate, fix the SNI/vhost configuration.

## 4. A Truststore Is Not a Keystore

| Artifact | Contents | Purpose |
| --- | --- | --- |
| **SP JVM truststore** | Trusted CA certificates / certificates | SP verifies the CAS certificate during ticket validation |
| **CAS server keystore** | CAS private key + certificate chain | CAS or servlet container terminates inbound TLS |
| **CAS proxy/LB keystore** | Public hostname private key + certificate | Ingress terminates TLS in front of CAS |
| **SP inbound keystore** | SP private key + certificate | Browsers / CAS callbacks verify SP's HTTPS |
| **SP outbound client keystore** | SP client private key/certificate if mTLS | SP proves its identity to CAS server when mTLS is required |
| **CAS-side truststore** | Trusted CAs for CAS outbound clients | CAS verifies `pgtUrl` / upstream services when acting as an HTTPS client |

**`server.ssl.*` in Spring Boot** typically configures **inbound** TLS for the web server and does not automatically establish trust for **outbound `Cas20ServiceTicketValidator`**. Likewise, `spring.ssl.bundle.*` merely defines a bundle; **you must wire the bundle into the specific HTTP client** if the library does not auto-apply it.

### Default Truststore in Java 17

Oracle JSSE documents that when Java does not specify `javax.net.ssl.trustStore`, the JVM looks for `jssecacerts` and then `cacerts` under `java.home/lib/security`. Across containers and JDK distributions, exact paths and included CAs can differ from developer workstations.

If you set `-Djavax.net.ssl.trustStore=/path/cas-truststore.p12`, **the specified truststore can replace the default trust source** rather than merging all public roots. Thus calls to another public API may fail if the custom truststore contains only an internal CA. When setting a global truststore, consider the blast radius and trust needs of every outbound client.

**Important:** configuring a custom truststore path that does not exist can leave the default trust manager with zero trust anchors; verify the real file, permissions, and JVM arguments on the **exact pod/node**.

## 5. Creating a PKCS12 Truststore with an Approved CA

When CAS uses an internal CA, the PKI team distributes the root/intermediate certificate over a **trusted administrative channel** alongside its SHA-256 fingerprint for independent verification. Once approved:

~~~bash
keytool -importcert \
  -alias corporate-cas-root \
  -file corp-root-ca.pem \
  -keystore /etc/portal/security/cas-truststore.p12 \
  -storetype PKCS12
~~~

The command prompts for password and trust confirmation interactively, avoiding placing passwords in shell history. Verify it:

~~~bash
keytool -list -v \
  -keystore /etc/portal/security/cas-truststore.p12 \
  -storetype PKCS12
~~~

Check Subject, Issuer, Validity, Basic Constraints, SHA-256 fingerprint, and aliases. **Never import a certificate grabbed straight from an endpoint suspected of MITM without out-of-band verification.** Doing so can turn an attacker's key into a trusted root.

### Default Java JSSE Configuration

Example JVM options (supplied via an approved secret management method):

~~~text
-Djavax.net.ssl.trustStore=/etc/portal/security/cas-truststore.p12
-Djavax.net.ssl.trustStoreType=PKCS12
-Djavax.net.ssl.trustStorePassword=[securely injected value]
~~~

These are **sample options**, not CAS-specific properties automatically read by Spring Boot. Never place real passwords on public process command lines, in CI logs, or in repositories. Use protected runtime config or secret management appropriate to your environment, and review exposure since JVM options can show up in diagnostics.

**Note:** whether the Apereo CAS client uses the JVM's default `SSLContext`, its own SSL socket factory, or a custom HTTP transport depends on the version/adapter. Check the **actually running** implementation: never assume `javax.net.ssl.trustStore` took effect if a custom transport overrides it.

### Why Avoid Modifying JDK `cacerts` Casually?

Adding a CA to the global JDK `cacerts` affects every outbound HTTPS connection in the entire JVM or base image. Prefer a managed truststore or container secret deployed with the application, checksummed, and rollback-capable. If using an organization-managed shared truststore, enforce CA update lifecycles, file permissions, and node-wide consistency.

## 6. Spring Boot SSL Bundles and Auto-Configuration Limits

Modern Spring Boot allows defining named SSL bundles:

~~~yaml
spring:
  ssl:
    bundle:
      jks:
        cas-client:
          truststore:
            location: "file:/etc/portal/security/cas-truststore.p12"
            password: "${CAS_TRUSTSTORE_PASSWORD}"
            type: "PKCS12"
~~~

Inside a Spring application, `SslBundles` retrieves the bundle:

~~~java
SslBundle bundle = sslBundles.getBundle("cas-client");
SSLContext context = bundle.createSslContext();
~~~

**This is an API fragment**; it does not run standalone and requires Spring Boot/JSSE imports. You must pass that `SSLContext` into the **HTTP client actually used by the CAS `TicketValidator`** via the version-appropriate API/adapter. Defining a bundle while the CAS client keeps using the default JSSE truststore will not fix the error.

Distinguish:

- **`server.ssl.bundle`**: normally protects **inbound server TLS**.
- **`spring.ssl.bundle.jks.cas-client.truststore`**: defines trust material, without auto-wiring it into every CAS client.
- **`javax.net.ssl.trustStore`**: configures JVM-wide default JSSE trust managers, affecting HTTP clients that use defaults.
- **Per-client `SSLContext`**: minimizes blast radius, though it requires explicit wiring in the CAS client library.

If the application calls both internal CAS and public APIs, a managed per-client `SSLContext` can be cleaner than a narrow global truststore—provided the CAS HTTP transport actually uses it.

## 7. Spring Security CAS Components

Spring Security Servlet has its own CAS module, distinct from `oauth2Login` and `saml2Login`:

- `CasAuthenticationEntryPoint` builds the browser redirect to CAS login with `service`.
- `ServiceProperties` holds the **SP service callback URL**, e.g., `https://portal.example.com/login/cas`.
- `CasAuthenticationFilter` receives the ST at the callback and sends an unauthenticated token to `AuthenticationManager`.
- `CasAuthenticationProvider` verifies the ST via `TicketValidator` and builds the authenticated `Authentication`.
- `Cas20ServiceTicketValidator` from Apereo CAS client performs ticket validation with the CAS server.
- `CasAuthenticationToken` represents the authenticated result in Spring Security; request token class names vary across Security versions.
- `UserDetailsService` / `AuthenticationUserDetailsService` maps the verified principal to a local account and authorities.

Spring Security docs note that `CasAuthenticationFilter` normally watches `/login/cas` and `ServiceProperties.service` must align with the real callback URL.

### Two URLs Never to Swap

~~~text
Spring ServiceProperties.service:
  https://portal.example.com/login/cas
  (Application's URL, where the browser returns)

CAS validator base:
  https://sso.example.org/cas
  (CAS URL, where Java calls ticket validation)
~~~

**Never set `ServiceProperties.service` to `https://sso.example.org/cas/serviceValidate`**: that is the CAS-side validation endpoint, not the SP callback. If CAS issues an ST for a different service than the URI the SP sends during validation, CAS rejects it with `INVALID_SERVICE` or a similar error code.

### Illustrative JavaConfig Beans

~~~java
import org.apereo.cas.client.validation.Cas20ServiceTicketValidator;
import org.apereo.cas.client.validation.TicketValidator;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.cas.ServiceProperties;

@Configuration
public class CasHttpsBaseConfig {

    private static final String CAS_BASE =
            "https://sso.example.org/cas";
    private static final String SP_CALLBACK =
            "https://portal.example.com/login/cas";

    @Bean
    ServiceProperties serviceProperties() {
        ServiceProperties properties = new ServiceProperties();
        properties.setService(SP_CALLBACK);
        properties.setSendRenew(false);
        return properties;
    }

    @Bean
    TicketValidator casTicketValidator() {
        return new Cas20ServiceTicketValidator(CAS_BASE);
    }
}
~~~

**This is only a configuration fragment**, requiring the Spring Security CAS module, matching Apereo CAS client version, and remaining beans to complete auth: `CasAuthenticationEntryPoint`, `CasAuthenticationFilter`, `CasAuthenticationProvider`, `AuthenticationManager`, and a local user service. Putting it in an empty file alone does not create a working login flow. `.example` domains do not resolve live, and trust material must be configured for outbound HTTP transport.

JavaConfig details vary by version; consult Javadocs for your resolved `spring-security-cas` and CAS client. Spring Security 6/7 use `jakarta.servlet`, whereas older CAS samples used `javax.servlet` or legacy XML namespaces. Never copy 3.x code assuming compatibility.

### Bean Relationship Summary

~~~text
CasAuthenticationEntryPoint:
  loginUrl         = https://sso.example.org/cas/login
  serviceProperties = ServiceProperties

CasAuthenticationFilter:
  filterProcessesUrl = /login/cas
  authenticationManager = ProviderManager

CasAuthenticationProvider:
  ticketValidator = Cas20ServiceTicketValidator(CAS_BASE)
  serviceProperties = ServiceProperties
  authenticationUserDetailsService = local user mapping
  key = unique provider identifier

Spring outbound TLS:
  CAS hostname allowed and resolved to approved destination
  TLS trust manager validates chain and SAN
  HTTP transport validates CAS ticket over HTTPS
~~~

**Never disable ticket validation due to TLS errors.** If CAS protocol 3 attributes are required, use the library's version-supported CAS 3 validator while keeping HTTPS trust and hostname checks intact.

## 8. TLS at Reverse Proxies and Internal Networks

Typical topology:

~~~text
Browser / Spring CAS client
       | public HTTPS
       v
CAS ingress / reverse proxy / LB
       | backend HTTPS (when threat model requires)
       v
CAS server node

Browser
       | public HTTPS
       v
Portal ingress
       | backend HTTPS (when threat model requires)
       v
Spring servlet app
~~~

When TLS terminates at a proxy:

1. The **public CAS hostname** certificate normally sits on the proxy; that is the certificate the **Spring CAS client** sees.
2. Backend proxy -> CAS node may use HTTPS/mTLS or HTTP inside a private network; evaluate this choice against zero trust and your network threat model.
3. If the backend leg uses HTTPS, the proxy must **verify the backend server cert** rather than flipping on an arbitrary "verify off" mode.
4. Both CAS and SP must construct accurate public service URLs regardless of whether the backend listens on `http://pod:8080`.
5. `X-Forwarded-Proto`/`X-Forwarded-Host` headers are trustworthy only when ingress **strips/replaces** any Internet-supplied copies and restricts backend access to trusted proxies.

Spring Boot may configure:

~~~yaml
server:
  forward-headers-strategy: framework
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
~~~

**This configuration does not create a trust boundary on its own.** Network and proxy rules must be right; if the backend trusts a client-sent `X-Forwarded-Host: evil.example.net`, callbacks and login redirects can be hijacked.

A common failure case:

~~~text
Browser-facing SP: https://portal.example.com/login/cas
Internal app:      http://portal-app:8080/login/cas

CAS issued ticket for public HTTPS callback.
Spring validates using internal HTTP callback by mistake.
Result: INVALID_SERVICE or login loop.
~~~

The fix is configuring `ServiceProperties.service` and the registered service to the **public URL**, and auditing proxy headers, host, path, and routes. Never drop HTTPS on the public callback just to make strings match.

### Cookies and HSTS

- Session cookies should set `Secure` and `HttpOnly`, with `SameSite` chosen per browser flow.
- CAS TGC/session cookies are never shared directly with the SP; each app/domain owns its own session.
- `Strict-Transport-Security` instructs browsers to prefer HTTPS after receiving the policy; **HSTS does not replace TLS verification in the Java back-channel**.
- Enable HSTS `includeSubDomains`/preload only when you control every subdomain and have a rollout/rollback plan.
- Never transmit ST/TGC over redirects to HTTP or leak tickets into third-party URLs.

## 9. CAS Proxy Authentication: The Reverse HTTPS Direction

CAS supports Proxy Granting Tickets (PGT) when a service must call another service on behalf of a user. A PGT flow may look like:

1. Spring CAS client validates the ST while passing `pgtUrl=https://portal.example.com/login/cas/proxyreceptor`.
2. CAS checks service and allowed proxy policies.
3. **CAS itself opens an HTTPS connection to the SP proxy receptor**.
4. CAS verifies the SP certificate, calls the callback per protocol, and correlates the PGT with PGTIOU.
5. The application may then use the PGT/PT within permitted policies.

Unlike the SP -> CAS back-channel, **CAS must trust the SP's certificate** in this step. Apereo CAS 7.3.x notes that if the proxy callback endpoint has an invalid, untrusted self-signed, incomplete-chain, or expired cert, CAS can reject the callback.

**The PGT callback requires HTTPS and peer trust per the CAS protocol**—do not accept HTTP for convenience. Never set `acceptAnyProxy=true` just to make a sample work if policy forbids broad proxying. If the project does not use CAS proxying, do not expose PGT endpoints or enable PGT credential release.

### Certificate Ownership Matrix

| Case | Certificate Verified | Who Holds the Truststore |
| --- | --- | --- |
| Spring validates Service Ticket | CAS public server certificate | Spring JVM / CAS client |
| CAS calls PGT proxy receptor | SP public server certificate | CAS JVM / CAS HTTP client |
| Browser visits CAS login | CAS public certificate | Browser / OS |
| Browser visits SP portal | SP public certificate | Browser / OS |

A classic operations mistake: CAS -> SP callback fails because the SP cert is untrusted, yet developers keep editing only the SP-side truststore. Identify **request direction** before modifying certificates.

## 10. Is Mutual TLS (mTLS) Required for CAS?

**The CAS Protocol does not mandate mTLS by default.** Normally the SP verifies the CAS server's TLS cert. Enterprises may add mTLS on SP -> CAS, proxy -> backend, or CAS -> SP callbacks when required by their threat model.

If the token validation endpoint demands a client certificate:

- The SP holds a **keystore** with its client private key + certificate.
- CAS/ingress holds a **truststore** to verify the client certificate and policy.
- The SP **still** needs a truststore to verify the CAS server's certificate.
- Client certificates and server certificates have separate lifecycles, issuers, and KeyUsage extensions.
- The HTTP transport actually calling CAS must use an `SSLContext` initialized with the appropriate `KeyManager`s.

**Do not confuse `server.ssl.client-auth` in Spring Boot** with mTLS when Spring calls **outbound** to CAS: that setting applies to **inbound** connections hitting the Spring server. Outbound mTLS must be configured separately on the CAS client transport.

**mTLS does not replace Service Ticket verification.** A client certificate proves which machine/service is calling the CAS endpoint per policy, not which user logged in via the browser.

## 11. TLS 1.2/1.3, Cipher Suites, and Algorithms

JDK 17 supports TLS 1.2 and TLS 1.3. Modern deployments should disable TLS 1.0/1.1 and weak cipher suites; Java's `jdk.tls.disabledAlgorithms` affects allowed protocols and algorithms. Depending on JDK vendor and patch level, verify actual handshakes rather than guessing from documentation examples.

- Prefer TLS 1.3, allowing TLS 1.2 for compatibility per baseline.
- Never re-enable SSLv3/TLS 1.0/TLS 1.1 or 3DES/RC4 to work around login errors.
- Issue server certificates with SANs and PKI-compliant algorithms.
- Verify the full signature chain and cipher negotiation, not only the URL.
- Keep runtime JDK security patches and CAS client dependencies up to date.
- Test real TLS handshakes through LB/ingress in staging, not only config files.

**Never conflate TLS signing with SAML XML signatures:** the CAS Protocol relies on HTTPS + Service Ticket validation; if Apereo CAS also acts as an OIDC/SAML IdP, token/assertion validation follows those respective protocols.

## 12. Standalone Java 17: Checking CAS and SP Callback URLs Before Deployment

This Java 17 program **compiles and runs with no external libraries**, catching bad HTTPS configurations before any network call. It enforces scheme, host allowlist, port, exact path, and rejects userinfo, queries, or fragments in **configured base URLs**.

**It performs no TLS handshake, checks no certificates, and validates no CAS tickets**; an `ALLOW` result means only that the **URL policy structure is valid**. Never use this demo to replace `HttpsURLConnection`/`HttpClient` TLS checks.

Create file **`CasHttpsPolicyDemo.java`**:

~~~java
import java.net.URI;
import java.net.URISyntaxException;
import java.util.Locale;

public class CasHttpsPolicyDemo {

    static String check(String candidate, String host, String path) {
        final URI uri;
        try {
            uri = new URI(candidate);
        } catch (URISyntaxException ex) {
            return "DENY: malformed URI";
        }

        if (!"https".equalsIgnoreCase(uri.getScheme())) {
            return "DENY: HTTPS required";
        }
        if (uri.getRawUserInfo() != null) {
            return "DENY: userinfo forbidden";
        }
        if (uri.getRawQuery() != null || uri.getRawFragment() != null) {
            return "DENY: unexpected query or fragment";
        }
        if (uri.getHost() == null
                || !host.equals(uri.getHost().toLowerCase(Locale.ROOT))) {
            return "DENY: unapproved host";
        }
        if (uri.getPort() != -1 && uri.getPort() != 443) {
            return "DENY: unapproved port";
        }
        if (!path.equals(uri.getRawPath())) {
            return "DENY: unexpected path";
        }
        return "ALLOW: approved URL policy";
    }

    public static void main(String[] args) {
        System.out.println("Good CAS: " + check(
                "https://sso.example.org/cas", "sso.example.org", "/cas"));

        System.out.println("HTTP CAS: " + check(
                "http://sso.example.org/cas", "sso.example.org", "/cas"));

        System.out.println("Other host: " + check(
                "https://other.example.org/cas", "sso.example.org", "/cas"));

        System.out.println("Wrong port: " + check(
                "https://sso.example.org:8443/cas",
                "sso.example.org", "/cas"));

        System.out.println("Userinfo: " + check(
                "https://user:secret@sso.example.org/cas",
                "sso.example.org", "/cas"));

        System.out.println("Query on CAS base: " + check(
                "https://sso.example.org/cas?ticket=ST-DEMO",
                "sso.example.org", "/cas"));

        System.out.println("SP callback: " + check(
                "https://portal.example.com/login/cas",
                "portal.example.com", "/login/cas"));

        System.out.println("Wrong callback: " + check(
                "https://portal.example.com/other",
                "portal.example.com", "/login/cas"));
    }
}
~~~

Compile and run:

~~~bash
javac CasHttpsPolicyDemo.java
java CasHttpsPolicyDemo
~~~

**Exact stdout:**

~~~text
Good CAS: ALLOW: approved URL policy
HTTP CAS: DENY: HTTPS required
Other host: DENY: unapproved host
Wrong port: DENY: unapproved port
Userinfo: DENY: userinfo forbidden
Query on CAS base: DENY: unexpected query or fragment
SP callback: ALLOW: approved URL policy
Wrong callback: DENY: unexpected path
~~~

**Explanation:**

- Good CAS passes the URL policy, yet **still requires verifying the TLS certificate and real CAS response**.
- HTTP CAS is rejected for lacking TLS.
- Other host is rejected even if that host holds a valid certificate from some CA.
- Wrong port is rejected because the **exercise's** policy permits only default/443; an internal network might approve a custom HTTPS port explicitly.
- Userinfo blocks credentials embedded in URLs.
- Query on CAS base: configured base URLs must not include tickets/queries. The **real CAS `TicketValidator`** builds `?service=...&ticket=...` afterward.
- SP callback differs from CAS base; wrong paths must be fixed rather than loosening service regexes.
- `URI` checks neither PKIX, SANs, ciphers, validity, nor live network hosts. Never treat `ALLOW` as a security certificate.

## 13. Java 17 Real HTTPS Probe Without Disabling Certificate Verification

To test directly from the **actual JDK 17/JVM environment**, use `HttpClient` with **default JSSE TLS validation**. The program below has **no fixed stdout** since output depends on the live server. Run it only against an organization-approved CAS login/test endpoint without any Service Ticket.

File `CasTlsProbe.java`:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import javax.net.ssl.SSLSession;

public class CasTlsProbe {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println("Usage: java CasTlsProbe <approved-https-url>");
            System.exit(2);
        }

        URI url = URI.create(args[0]);
        if (!"https".equalsIgnoreCase(url.getScheme())
                || url.getHost() == null
                || url.getRawUserInfo() != null) {
            throw new IllegalArgumentException("HTTPS URL required");
        }

        // Run only against an admin-approved host.
        // Default JSSE: no trustAll or hostname bypass.
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();

        HttpRequest request = HttpRequest.newBuilder(url)
                .timeout(Duration.ofSeconds(10))
                .GET()
                .build();

        HttpResponse<Void> response =
                client.send(request, HttpResponse.BodyHandlers.discarding());

        System.out.println("HTTP status: " + response.statusCode());
        SSLSession tls = response.sslSession().orElseThrow();
        System.out.println("TLS protocol: " + tls.getProtocol());
    }
}
~~~

Run against a real test CAS host:

~~~bash
javac CasTlsProbe.java
java CasTlsProbe https://sso.your-approved-test-domain.example/cas/login
~~~

Because the domain is illustrative, substitute a real managed URL. If the certificate is untrusted, the SAN is wrong, or the handshake fails, the program must fail—never add `-k` or a bypass. HTTP 200/302 and a TLS protocol prove only that the HTTPS endpoint is reachable; **they do not prove an ST was validated by CAS**. Run validator integration tests next.

## 14. Verification Tools on the Exact Network and JVM

### `openssl s_client`

~~~bash
openssl s_client \
  -connect sso.example.org:443 \
  -servername sso.example.org \
  -verify_return_error \
  -showcerts
~~~

Inspects handshake/chain and SNI. `-verify_return_error` tells OpenSSL to fail if the certificate cannot be verified against OpenSSL's trust settings. **OpenSSL may use a different CA store than Java**, so an OK result here does not guarantee the JVM agrees.

### `curl`

~~~bash
curl -I --max-time 10 https://sso.example.org/cas/login
~~~

Checks HTTP/TLS using libcurl's trust store. Never use `curl -k` or `--insecure` to declare security healthy. Target an endpoint without tickets or cookies. `curl` never replaces a CAS `TicketValidator` integration test.

### `keytool`

~~~bash
keytool -printcert -sslserver sso.example.org:443 -rfc
keytool -list -v \
  -keystore /etc/portal/security/cas-truststore.p12 \
  -storetype PKCS12
~~~

`printcert` inspects the public endpoint's certificate, while `list` inspects the app's trust anchors. Never mistake simply printing a certificate for verifying hostnames and CA chains inside the app.

### JSSE Debug

In a secure staging environment you may use:

~~~text
-Djavax.net.debug=ssl,handshake,trustmanager
~~~

Logs can reveal hostnames, certificates, and internal details; limit duration, restrict access, and redact sensitive data before sharing with support. If the truststore works on a laptop yet fails in a pod, inspect `java.home`, image version, volume mounts, and actual JVM options on the pod.

## 15. Error Symptoms and Remediation

| Symptom | Possible Cause | Fix |
| --- | --- | --- |
| `PKIX path building failed` | JVM does not trust the CAS CA/chain | Check trusted CAs, intermediate chain, and active runtime truststore |
| `unable to find valid certification path` | Missing trust anchor or empty/wrong truststore | Supply approved CA; check file path/mount/password |
| `No subject alternative names present` | CAS cert lacks a matching SAN | Reissue cert with the proper hostname SAN |
| `No name matching sso.example.org found` | Hostname / SNI / certificate mismatch | Fix CAS URL, DNS/LB SNI, or cert; never disable the verifier |
| `CertificateExpiredException` | Leaf or intermediate cert expired | Renew and roll out properly |
| `CertificateNotYetValidException` | Cert not yet valid or clock skew | Check NTP and validity dates; never disable date checks |
| `handshake_failure` | Cipher/TLS version, client-auth, or policy mismatch | Fix TLS baseline or mTLS config; never enable weak ciphers |
| CAS login page loads yet SP loops | SP -> CAS ticket validator hits TLS/network failure | Test from JVM/container and CAS validation, not browser alone |
| CAS `INVALID_SERVICE` | `ServiceProperties.service` mismatches callback | Align public URL, registry, and proxy |
| CAS `INVALID_TICKET` | Ticket expired/consumed or wrong issuer/service | Inspect ticket lifecycle; never allow replay |
| CAS PGT proxy callback fails | CAS -> SP certificate untrusted | Fix SP certificate and CAS-side truststore |
| Only one node fails | Uneven truststore/JDK/certificate config | Compare rollout, config, and SSL sessions across nodes |
| Enabling custom truststore breaks another API | Custom truststore replaced public default roots | Include needed trust anchors or use per-client `SSLContext` |
| HTTPS 302 succeeds yet user is not logged in | HTTP success does not replace ticket validation | Inspect CAS response, Spring provider, and local account/roles |
| Spring issues HTTP redirect instead of HTTPS | Wrong trusted forwarded headers or public host | Fix ingress/proxy and service URL |
| TLS passes yet user gets 403 | Local authorization works or role/tenant is wrong | Check business policy; do not blame TLS |

**Never fix TLS errors by disabling certificate validation or downgrading ticket validation to HTTP.** TLS connection errors must be fixed at trust/chain/hostname/protocol layers; CAS service errors at URL/ticket layers; authorization errors at local permissions.

## 16. Anti-Patterns to Eliminate

### A. Trust-All Certificate

~~~java
// BAD PATTERN — never use:
public void checkServerTrusted(
        java.security.cert.X509Certificate[] chain,
        String authenticationType) {
    // no-op: every server certificate is accepted
}
~~~

An `X509TrustManager` that checks nothing turns HTTPS into an encrypted pipe to any attacker. Never use it in production or treat it as a safe temporary workaround.

### B. Always-True `HostnameVerifier`

~~~java
// BAD PATTERN — never use:
javax.net.ssl.HostnameVerifier insecure =
        (hostname, session) -> true;
~~~

A certificate signed by a valid CA for a different hostname must never be accepted for `sso.example.org`. If the hostname is wrong, fix the certificate or URL. Never install an insecure global default verifier.

### C. Running `curl -k` to "Prove HTTPS Works"

~~~bash
# Wrong if used as a security TLS verification:
curl -k https://sso.example.org/cas/login
~~~

`-k` skips certificate verification. Use it only in controlled diagnostics to isolate network/HTTP differences—never report its success as security verification.

### D. Overly Broad CAS Service Registry

~~~text
^https?://.*
~~~

This pattern permits arbitrary unmanaged services. For a specific Portal, register an anchored regex matching the exact HTTPS hostname and path:

~~~text
^https://portal[.]example[.]com/login/cas$
~~~

Service ticket security relies on **restricting the CAS server to issue STs only to approved services**.

### E. Taking the CAS URL from a User Request

A query like `?casServer=https://untrusted.example.net` must never change the `TicketValidator` base URL at runtime. Allowing it enables **SSRF**, ST theft, or tricking the app into trusting a rogue CAS server. The CAS URL must be configured and managed server-side.

### F. HTTP for Ticket Validation or PGT Callbacks

~~~text
http://sso.example.org/cas/serviceValidate?ticket=ST-...
http://portal.example.com/login/cas/proxyreceptor
~~~

These paths expose credentials and callback identities. The CAS proxy protocol mandates HTTPS for PGT callbacks and evaluates peer trust. Never downgrade to HTTP to "bypass PKIX errors."

### G. Blindly Importing a Certificate from a Failing Server

If you fetch a certificate with `openssl` from a potentially MITM'd path and immediately import it as a trust anchor without PKI verification, you may **trust an attacker's key**. Verify the fingerprint/CA through an independent channel with clear ownership and auditing.

## 17. Protecting Service Tickets and Browser Sessions Beyond TLS

HTTPS alone does not fix ST appearance in redirect URLs:

- Never log raw `?ticket=ST-...` queries in access logs, APM, analytics, or error reporting.
- Never paste real STs into support tickets, shell history, or chat.
- Set an appropriate `Referrer-Policy` and avoid third-party resources on callbacks carrying STs.
- Protect SP session cookies with `Secure`, `HttpOnly`, proper path/domain, and `SameSite` matched to browser flow.
- Use exact HTTPS callbacks; never let a proxy downgrade redirects to HTTP.
- CAS TGC/session cookies belong to the CAS domain and must never be shared with or read directly by the SP.
- Establish local `Authentication` only after CAS ticket validation; never trust a query username.
- CAS STs are normally single-use to prevent replay at the protocol layer; never attempt replay to fetch identity.
- When the app uses local roles/tenants, check disabled/locked users and authorization after CAS login.

**CAS principal attributes** can contain PII. Never dump raw CAS XML `authenticationSuccess`/attributes into production debug logs; log only event IDs, service identifiers, and sanitized errors.

## 18. Comprehensive Staging Integration Tests

| Test | Scenario | Expected Result |
| --- | --- | --- |
| Browser -> CAS | HTTPS login, valid certificate | Browser verifies the exact CAS host |
| Browser -> SP | HTTPS Portal, valid certificate | Browser connects securely |
| **SP -> CAS TLS** | JVM truststore holds valid CA | Handshake and hostname verification PASS |
| Wrong CA | CAS presents cert from untrusted CA | SP must reject |
| Wrong SAN | Valid cert yet for another hostname | SP must reject |
| Expired certificate | CAS cert expired | SP must reject |
| Missing intermediate | Server omits chain and client cannot build path | TLS fails |
| Weak TLS | CAS offers only disabled legacy TLS/weak ciphers | Handshake fails |
| Wrong service | ST issued for Portal A, validated by Portal B | CAS rejects |
| ST replay | Validate already-consumed ticket | CAS rejects |
| Fake CAS XML | No real ticket validation occurred | No `Authentication` created |
| Browser receives ticket | ST redirected over HTTPS | SP receives and processes properly |
| Wrong Java truststore mount | Container missing file | TLS fails; never auto-enables trustAll |
| CAS certificate rotation | New cert under trusted CA | Clean rollout and stable monitoring |
| CA rotation | Trust anchors change | Only approved CAs trusted |
| Proxy HTTPS termination | Internal HTTP backend | Public service callback remains HTTPS |
| Forwarded header spoof | External request sends forged host/proto | Ingress strips/replaces; no open redirect |
| PGT callback HTTPS | CAS Proxy enabled properly | CAS verifies SP certificate |
| PGT callback wrong cert | Invalid SP certificate | CAS rejects proxy callback |
| Wrong mTLS client cert | Policy requires mTLS | CAS/ingress rejects |
| Disabled local user | CAS authenticates yet SP user is locked | Local app denies per policy |
| Multi-node | Load-balanced across CAS/SP nodes | Truststore and callbacks consistent |

**Negative tests must run in staging/test CAs**, never swapping production certificates to induce failures. Use a lab CAS server, test truststores, and Spring integration tests with a real `TicketValidator`. Unit tests mocking `CasAuthenticationToken` alone prove neither HTTPS trust nor CAS protocol security.

### Minimal E2E Test Procedure

1. Register `https://portal.example.com/login/cas` in the CAS service registry with a tight HTTPS regex.
2. Verify the CAS public certificate, CA chain, and SAN from inside the JVM container.
3. Log in via test browser through CAS and obtain a Service Ticket without logging the raw value.
4. Spring invokes `Cas20ServiceTicketValidator` against the CAS base over HTTPS.
5. Observe real CAS ticket validation XML bound to the exact service and consumed once.
6. Spring creates the session, principal, and authorities per local policy.
7. Test wrong service URL, spent ST, untrusted CA, and wrong SAN; all must fail.
8. If using PGT workflows, test CAS -> SP callbacks with both valid and invalid SP certificates.
9. Verify forwarded headers, cookies, and HTTPS redirects never leak STs.
10. Mark PASS only when both TLS trust and CAS authentication/authorization succeed.

## 19. Certificate Rotation and Long-Term Operations

To prevent widespread CAS SSO outages when certificates near expiration:

1. Identify where TLS actually terminates: CAS process, ingress, or LB.
2. Track public hostnames, SANs, issuers/CAs, chains, and expiration dates.
3. For CA rollovers, approve the new CA via PKI and distribute trust anchors to JVMs ahead of cutover per schedule.
4. When renewing a leaf certificate under an already-trusted CA, still verify SANs, key usage, intermediate chain, and hostname.
5. Ensure all SP pods share identical trust material and JDK security baselines.
6. Verify server private keys are never committed to repos or exposed in CAS metadata/logs.
7. Monitor counts of `SSLHandshakeException`, PKIX path errors, hostname mismatches, timeouts, and `INVALID_SERVICE` per app.
8. Retire old CAs once the overlap window closes rather than keeping obsolete trust anchors forever.
9. Run negative tests after certificate or truststore updates.
10. Maintain rollback plans, owners, change records, and notifications to CAS-consuming SP clients.

**Avoid arbitrary leaf pinning**: pinning a static leaf certificate without a key rotation plan easily breaks logins upon renewal. A reviewed, tightly scoped internal trusted CA is often preferable; choose based on your threat model.

## 20. Frequently Asked Questions

**Q:** Chrome opens CAS HTTPS with no error, yet the backend hits `PKIX path building failed`?

**A:** Browsers and the Java JVM use different truststores. Inspect the CA, chain, cert, SAN, and the **actual** JVM runtime rather than relying on the browser.

**Q:** Is setting `server.ssl.key-store` enough for the SP to trust CAS?

**A:** No. That primarily serves inbound HTTPS. The outbound CAS validator needs the HTTP client's truststore/`SSLContext`.

**Q:** We configured `spring.ssl.bundle.jks.cas-client.truststore` yet it still fails?

**A:** Defining a bundle does not guarantee the Apereo CAS validator uses it automatically. Verify that the client adapter/transport actually wired the bundle.

**Q:** Should we import the CAS private key into Spring's truststore?

**A:** No. The SP needs only the trusted public CA/certificate to verify CAS. The CAS private key must remain secret on CAS/ingress.

**Q:** The CAS cert has a valid CA, yet the SAN mismatches—can we disable hostname checking?

**A:** No. Reissue the certificate or configure the right hostname and public DNS.

**Q:** Is `ServiceProperties.service` the CAS validation URL?

**A:** No. It is the **Spring app's** callback URL. The CAS validator takes the CAS base URL separately.

**Q:** Does HTTPS replace ticket validation?

**A:** No. TLS protects the channel to the CAS server, while `TicketValidator` and the CAS server decide whether the ST is valid, service-matched, unexpired, and unconsumed.

**Q:** Does CAS require mTLS everywhere?

**A:** Not by default. mTLS is an optional service-authentication layer per policy; it does not replace the CAS ticket protocol.

**Q:** Who checks the certificate when CAS calls the SP's PGT callback?

**A:** CAS acts as the HTTPS client, so **CAS-side** trust material must trust the SP certificate.

## 21. Deployment Checklist

- [ ] Distinguished Browser -> SP, Browser -> CAS, SP -> CAS, and CAS -> SP proxy callback TLS legs.
- [ ] HTTPS enforced for CAS base, CAS login, and SP service callback.
- [ ] CAS client uses standard trust manager/hostname verifier and approved CAs.
- [ ] CAS certificate has accurate SAN, complete chain, valid dates, and strong algorithms.
- [ ] Truststore matches file/JVM/container; unverified CAs are never imported.
- [ ] Neither trustAll, always-true `HostnameVerifier`, HTTP validation, nor `curl -k` is used to verify security.
- [ ] Inbound keystores, outbound truststores, and mTLS client keystores are kept separate.
- [ ] Spring Boot SSL Bundles, if used, are explicitly wired into the active HTTP transport.
- [ ] `ServiceProperties.service` is the SP callback, while `TicketValidator` points to the CAS base.
- [ ] CAS registered service regex permits only the exact HTTPS host/path.
- [ ] Reverse proxy / forwarded headers are trusted only from controlled ingress.
- [ ] SP/CAS cookies use `Secure`/`HttpOnly` with proper session lifecycles.
- [ ] STs and CAS XML never appear verbatim in logs or telemetry.
- [ ] ST one-time/service matching and local user/role/tenant authorization remain enforced.
- [ ] Wrong CA, wrong hostname, expired certificate, and wrong-service tests fail closed.
- [ ] Certificate/CA rotation has an owner, timeline, monitoring, and rollback plan.
- [ ] If using CAS Proxy PGT, CAS trusts the SP certificate and the callback uses HTTPS.
- [ ] Verified compatibility across exact Java, CAS client, Spring Security, and Boot versions.

## 22. Official References

1. [Spring Security — CAS Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html): `CasAuthenticationEntryPoint`, `ServiceProperties`, `CasAuthenticationProvider`, HTTPS ticket validation.
2. [Spring Security — CasAuthenticationFilter Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/web/CasAuthenticationFilter.html): Service Ticket callback and `/login/cas`.
3. [Spring Security — ServiceProperties Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/ServiceProperties.html): service callback semantics.
4. [Apereo CAS 7.3 — CAS Protocol](https://apereo.github.io/cas/7.3.x/protocol/CAS-Protocol.html): ST, TGT/TGC, CAS 2/3 validation endpoints.
5. [Apereo CAS — CAS Protocol Specification](https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html): service matching, ticket validation, HTTPS PGT callbacks.
6. [Apereo CAS 7.3 — Proxy Authentication](https://apereo.github.io/cas/7.3.x/authentication/Configuring-Proxy-Authentication.html): callback SSL validation when CAS is the HTTPS client.
7. [Apereo CAS — Troubleshooting SSL/Certificates](https://apereo.github.io/cas/development/installation/Troubleshooting-Guide.html): PKIX path, SAN, and hostname errors.
8. [Oracle Java 17 — JSSE Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html): truststores, keystores, HTTPS hostname checks, TLS configuration.
9. [Oracle Java 17 — JDK Providers](https://docs.oracle.com/en/java/javase/17/security/oracle-providers.html): TLS versions and disabled algorithms.
10. [Spring Boot — SSL Bundles](https://docs.spring.io/spring-boot/reference/features/ssl.html): `spring.ssl.bundle.*` and `SslBundles`.
11. [OWASP — Transport Layer Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html): TLS configuration and certificate lifecycles.

**Takeaway:** securing CAS SSO requires proper HTTPS on **both the front channel and the back channel**. Most critically in Spring Security, **`TicketValidator` must call CAS over real HTTPS, verifying the PKIX certificate chain and SAN hostname**, alongside **single-use STs and service binding**. A JVM truststore is not an inbound keystore; browser TLS does not prove Java TLS; never disable certificate checks to paper over misconfigurations.