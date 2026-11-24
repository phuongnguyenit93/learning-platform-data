# HTTPS Between Browser, Proxy, Application, and Identity Provider in Spring Security WebFlux

## 1. Why Must HTTPS Be Protected on Every Hop?

A **reactive** Spring Security application rarely terminates TLS connections directly from the browser: the browser calls a reverse proxy or load balancer; the proxy forwards to Spring Boot WebFlux (Reactor Netty); the application in turn calls an Identity Provider (IdP) for OAuth2/OpenID Connect, JWK Set retrieval, or token introspection. **External HTTPS does not automatically protect the hops behind it.**

The goal of this lesson is to understand precisely **who establishes TLS with whom, who is authorized to assert the original scheme/host, how the application constructs OAuth2 URLs, and how to test that the entire flow cannot be downgraded to HTTP**.

After this lesson, you will be able to:

1. Diagram TLS flows across browser, proxy, WebFlux, and IdP; pinpoint decryption and re-encryption points.
2. Choose TLS termination, TLS re-encryption, or mutual TLS (mTLS) according to the trust boundary.
3. Safely configure `Forwarded`/`X-Forwarded-*` so WebFlux sees the public HTTPS URL without trusting arbitrary client-sent headers.
4. Properly configure OAuth2/OIDC redirect URIs, session cookies, HSTS, HTTPS redirects, and TLS connections from the application to the IdP.
5. Diagnose real-world failures: redirect loops, `redirect_uri_mismatch`, lost callback sessions, certificate handshake failures, missing HSTS, and spoofed forwarded headers.

**Context:** Java 17+, Spring Boot 3.x with Spring Security 6.x and WebFlux/Reactor Netty. Nginx snippets illustrate one specific architecture; when using Gateway API, Kubernetes Ingress, Envoy, Traefik, or cloud load balancers, apply the same trust boundary principles using their corresponding mechanisms. Do not use Servlet `HttpSecurity`/`ForwardedHeaderFilter` to solve reactive application issues.

## 2. Distinguishing the Four Connections

Assume the public address is `https://app.example.com`, the internal upstream address is `https://app.internal.example:8443`, and the IdP is `https://login.example.com`.

```text
                           (A) TLS: app.example.com
+-----------+  HTTPS  +---------------------+
| Browser   | ------> | Edge proxy / LB     |
+-----------+         | terminates TLS A    |
      |               | sanitizes forwarded |
      |               +----------+----------+
      |                          |
      |               (B) TLS: app.internal.example
      |                          |
      |                          v
      |               +---------------------+
      |               | Spring Boot WebFlux  |
      |               | SecurityWebFilterChain|
      |               +----------+----------+
      |                          |
      |               (C) TLS: login.example.com
      |                          |
      |                          v
      |               +---------------------+
      +--- (D) HTTPS --> Identity Provider  |
          browser       OAuth2/OIDC         |
          front-channel +--------------------+
```

**The four connections play distinct roles:**

| Hop | Who is TLS client → TLS server? | Sensitive Data | Mandatory Checks |
| --- | --- | --- | --- |
| A. Browser → proxy | Browser → public proxy | Session cookie, Bearer token, OAuth authorization code in callback URL | Trusted certificate, DNS/SAN matching hostname, HTTP→HTTPS redirect, HSTS |
| B. Proxy → WebFlux | Proxy → internal application | Cookie, Authorization header, body, forwarded info | TLS re-encryption, upstream certificate verification; restrict access to proxy only |
| C. WebFlux → IdP | Application HTTP client → token/JWKS/introspection/userinfo endpoint | `client_secret`, authorization code, refresh/access token, JWK | HTTPS, valid IdP CA chain and hostname, timeouts, no trust-all |
| D. Browser → IdP | Browser → IdP login/authorize page | Password, MFA, consent, `state`, `code_challenge` | IdP HTTPS with valid certificate, redirect URI validation, no tokens issued over HTTP |

**Important:** an HTTPS arrow only protects **that specific hop**. Once the proxy decrypts TLS A, the request is in plaintext inside proxy memory; if hop B forwards over HTTP, anyone able to observe the network between those two components can read the data. Connection D is established **directly by the browser** to the IdP; connection C is initiated by the **backend** and has its own certificate/CA trust configuration.

OAuth2 flows must be categorized properly:

- **OAuth2 Login/OIDC Client:** browser redirects to IdP on D, IdP redirects back to public callback on A, backend exchanges `code` for tokens with IdP on C.
- **JWT Resource Server:** browser/client sends Bearer JWT to API on A/B, Resource Server may fetch public JWKs from IdP via C to verify signatures; browser login is not strictly required.
- **Opaque Token Resource Server:** backend calls the introspection endpoint via C to validate tokens; an OAuth2 login callback does not need to exist.

One application can serve multiple roles, but each endpoint and corresponding `SecurityWebFilterChain` must be clearly defined; do not conflate a client's redirect URI with a Resource Server's verification endpoints.

## 3. TLS Termination, Re-encryption, and mTLS

### 3.1. Common Topologies

**Model 1 – Termination at proxy; proxy → application is HTTP:**

```text
Browser --HTTPS--> Proxy --HTTP--> App
```

Easy to operate, but the hop behind the proxy is **unencrypted**. Acceptable only when infrastructure/policy proves the internal network is trustworthy and the risk scope is approved. Do not treat "same VPC" or "same Kubernetes cluster" as proof of TLS.

**Model 2 – TLS re-encryption (recommended for sensitive environments):**

```text
Browser --HTTPS--> Proxy --HTTPS--> App
```

There are two independent TLS sessions: the proxy's public certificate and the application's internal certificate. The proxy must **verify** the upstream certificate, including CA, expiration, and hostname/SAN. Merely using `https://` in `proxy_pass` while disabling upstream verification still risks rogue server injection.

**Model 3 – mTLS for the internal hop:**

```text
Browser --HTTPS--> Proxy --mTLS--> App
```

The application requires the proxy to present a client certificate; the proxy still verifies the application's server certificate. mTLS adds mutual authentication between workloads; it does not replace OAuth2/OIDC user authentication or authorization. Forwarding browser client-certificate authentication via custom headers is a separate problem and requires its own designed trust boundary.

### 3.2. Rules for Certificates

- The certificate for `app.example.com` must be valid for the **public hostname**. The upstream certificate for `app.internal.example` must be valid for the name the proxy checks for upstream TLS, which need not match the public hostname.
- Prefer TLS 1.3; TLS 1.2 may be retained when needed for compatibility with cipher suites evaluated as secure. Disable legacy TLS versions and weak ciphers per organizational standards.
- Automate certificate renewal, monitor expiration, and verify the full certificate chain; provision private keys via a secret manager or permission-restricted storage, avoiding commits to repositories/container images.
- Hardcoded certificate pinning easily causes outages during rotation; for most server-to-server applications, use proper CA trust, hostname verification, and managed certificate issuance/rotation policies.
- Verify the **SNI + SAN + DNS** relationship; an upstream DNS name mismatching the certificate commonly causes `SSLHandshakeException`/`certificate_unknown`.

## 4. Configuring the Reverse Proxy: Handling HTTPS and Trust Boundaries

### 4.1. The Proxy Must Authoritatively Generate Public Request Metadata

When a browser requests:

```http
GET /oauth2/authorization/company HTTP/1.1
Host: app.example.com
```

the proxy may forward to `https://app.internal.example:8443`, while Spring needs to know the external user used `https://app.example.com`. Common headers:

```http
X-Forwarded-Proto: https
X-Forwarded-Host: app.example.com
X-Forwarded-Port: 443
X-Forwarded-For: <client IP address determined by proxy>
```

RFC 7239 standardizes the variant:

```http
Forwarded: for=<client>;proto=https;host=app.example.com
```

**Never trust values self-reported by the browser.** An attacker can send `X-Forwarded-Host: attacker.example` or `Forwarded: proto=http;host=attacker.example`. If the edge proxy preserves those headers, WebFlux may construct redirect/password-reset/callback URLs using the untrusted hostname, causing open redirects, host-header injection, or information disclosure.

At the **trusted network boundary**, the proxy must strip/overwrite **the entire family** of `Forwarded` (RFC 7239) and `X-Forwarded-*` variants. Do not clear just one header name and let another variant slip through. If multiple proxies exist, each hop must have explicit rules establishing the source of truth for host, scheme, port, and client IP; do not blindly take the first list element that a client might inject.

### 4.2. Nginx Example with Re-encryption

The configuration below illustrates **a standalone edge proxy** receiving public traffic; use valid internal domains/certificates that have been issued. Certificate paths are deployment configuration paths, not files pre-created by this lesson.

```nginx
server {
    listen 80;
    server_name app.example.com;
    return 308 https://app.example.com$request_uri;
}

server {
    listen 443 ssl;
    server_name app.example.com;

    ssl_certificate     /etc/nginx/tls/public-fullchain.pem;
    ssl_certificate_key /etc/nginx/tls/public-key.pem;
    ssl_protocols TLSv1.2 TLSv1.3;

    location / {
        proxy_pass https://app.internal.example:8443;

        # Re-encrypt to the application and actually verify the internal certificate.
        proxy_ssl_server_name on;
        proxy_ssl_name app.internal.example;
        proxy_ssl_verify on;
        proxy_ssl_trusted_certificate /etc/nginx/tls/internal-ca.pem;
        proxy_ssl_verify_depth 2;

        # Use only the deployed canonical public host.
        proxy_set_header Host app.example.com;
        proxy_set_header Forwarded "";
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Host app.example.com;
        proxy_set_header X-Forwarded-Port 443;
        proxy_set_header X-Forwarded-For $remote_addr;

        # Strip unused variants from the request sent to the app.
        proxy_set_header X-Forwarded-Prefix "";
        proxy_set_header X-Forwarded-Ssl "";
    }
}
```

**Explanation:** `proxy_ssl_verify on` and the internal CA are two critical settings for upstream TLS; `proxy_ssl_name` must match the application's certificate. `$remote_addr` represents the peer IP observed by Nginx; if a CDN/LB sits in front, configure a trusted proxy chain before treating it as the user IP.

The example intentionally pins a fixed public host; with multiple virtual hosts, build a corresponding host allowlist/routing policy instead of passing an arbitrary `Host` as a trusted redirect target. Protect port `8443` so only authorized proxies/peers can connect; nginx config is only one piece, while firewall/network policy/TLS certificates must still operate properly.

**Note on 308:** an initial HTTP request still occurs before the browser is redirected; never send credentials in HTTP URLs. Use HSTS cached by browsers or a preload policy after thoroughly evaluating all subdomains to reduce first-request exposure.

## 5. Making Spring Boot WebFlux Understand the External Scheme and Host

### 5.1. `ForwardedHeaderTransformer`, Not a Servlet Filter

WebFlux uses `org.springframework.web.server.adapter.ForwardedHeaderTransformer` to process headers already sanitized by a trusted proxy. In Spring Boot 3.x, the convenient configuration is:

```yaml
server:
  forward-headers-strategy: framework
```

`FRAMEWORK` instructs Spring Framework to process forwarded headers; in a reactive application, the corresponding mechanism is `ForwardedHeaderTransformer`. `NATIVE` relies on the web server's capabilities and must be verified against the exact server in use; `NONE` ignores forwarded headers. Do not arbitrarily declare an extra `ForwardedHeaderTransformer` bean if Boot already configures the same responsibility and you have not verified overlapping effects.

**Prerequisite:** the application only receives forwarded headers emitted by an identified trusted proxy; a network policy blocks direct external access to the app. `ForwardedHeaderTransformer` **does not authenticate** whether a header came from a valid proxy or an attacker. When there is no trusted proxy and headers should not be applied, use `NONE` or a `removeOnly` transformer to strip headers instead of applying untrusted data.

Effects to verify after configuration:

- `ServerHttpRequest.getURI()` reflects public `https://app.example.com/...` when requests actually arrive through a valid proxy.
- Spring Security's generated redirects/links use the proper public host and scheme.
- HTTPS redirects in the filter chain **do not create an infinite loop** by mistaking a browser's HTTPS request for HTTP behind TLS termination.
- Logs, redirects, and cookies do not leak internal hostnames or port `8443`.

### 5.2. If the Application Also Enables HTTPS on the Internal Port

Example `application-prod.yml` for Spring Boot 3.x:

```yaml
server:
  port: 8443
  forward-headers-strategy: framework

  ssl:
    enabled: true
    key-store: ${APP_TLS_KEYSTORE}
    key-store-type: PKCS12
    key-store-password: ${APP_TLS_KEYSTORE_PASSWORD}

  reactive:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: lax
```

`APP_TLS_KEYSTORE` is the PKCS#12 path supplied by the deployment environment. If the private key has its own password, configure `server.ssl.key-password` accordingly. The certificate in the keystore must have a SAN matching the upstream hostname the proxy verifies. Keystore passwords go through secret injection; do not put literal secrets in Git.

`server.reactive.session.cookie.*` applies to Boot-managed reactive session cookies; if the application uses Spring Session or a custom `WebSessionIdResolver`, verify the cookie serializer/resolver actually emitting `Set-Cookie`. Do not mistakenly use `server.servlet.session.cookie.*` for WebFlux.

**Alternative:** if TLS terminates at the proxy and traffic to the application uses HTTP under an approved architecture, omit the internal SSL listener above; forwarded headers must still be managed and the HTTP hop risk documented. This lesson uses TLS re-encryption as the target configuration.

## 6. Configuring Spring Security Reactive: HTTPS Redirect and HSTS

Spring Security protects requests at the application layer, yet it **does not open a TLS port itself**; TLS is the web server/proxy's responsibility. When the application needs to actively redirect HTTP requests to HTTPS, use `ServerHttpSecurity.redirectToHttps()`.

A syntactically complete Java 17+ configuration for a **WebFlux OAuth2 Login application** (saved at `src/main/java/example/https/SecureLoginApplication.java` in a Spring Boot project with WebFlux and OAuth2 Client):

```java
package example.https;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class SecureLoginApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecureLoginApplication.class, args);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public").permitAll()
                        .anyExchange().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .redirectToHttps(Customizer.withDefaults())
                .build();
    }

    @RestController
    static class DemoController {
        @GetMapping("/public")
        Mono<String> publicPage() {
            return Mono.just("HTTPS boundary demo");
        }

        @GetMapping("/private")
        Mono<String> privatePage() {
            return Mono.just("Only authenticated users");
        }
    }
}
```

Minimum Gradle Groovy dependencies for a Spring Boot example with dependency management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()
}
```

The example only runs successfully when a certificate/keystore and OAuth2 client registration with a real or trusted test IdP are provided (see section 7). Run command in a Gradle project with wrapper:

```bash
./gradlew bootRun --args='--spring.profiles.active=prod'
```

Windows PowerShell uses `.\gradlew.bat bootRun --args='--spring.profiles.active=prod'`. Over HTTPS, `GET /public` returns the **exact** body `HTTPS boundary demo`; unauthenticated access to `/private` triggers OAuth2 login as configured. This is an **OAuth2 Login** application, not a JWT Resource Server sample; if the application only accepts Bearer JWTs, replace `.oauth2Login(...)` with `.oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))` in a separate configuration and provide `issuer-uri`.

### 6.1. Avoiding HTTPS Redirect Loops

When the browser uses HTTPS but proxy → app is HTTP, if the app only sees `http://internal-host:8080` without processing a trusted `X-Forwarded-Proto: https`, `.redirectToHttps(...)` can repeatedly issue 3xx responses. The right fix is:

1. Proxy normalizes scheme/host/port and strips spoofed headers.
2. WebFlux enables the appropriate forwarded-header strategy when requests arrive via a proxy.
3. HTTPS redirect is placed at the edge or in Spring Security after accurate request URI resolution.
4. Use `curl`/browser to inspect the `Location` chain; do not fix it by disabling TLS verification or allowing infinite redirects.

In architectures that already redirect HTTPS at the edge, the edge can remain the source of 80→443 redirects while keeping accurate HTTPS scheme detection at the application for OAuth callbacks and cookies.

### 6.2. HSTS Only Matters on Public HTTPS Responses

Spring Security supports **HTTP Strict Transport Security** and enables HSTS by default when secure-request conditions are met. Example header:

```http
Strict-Transport-Security: max-age=31536000
```

`includeSubDomains` affects **all** subdomains; `preload` requires compliance with preload policies before submission. Do not add these directives just to look "stronger" if any subdomain still serves HTTP or certificate rollback readiness is not established.

If the proxy emits HSTS instead of the application, ensure a centralized policy and avoid conflicting duplicate headers. Inspect the header at the **public HTTPS address**, not only on the internal port. Browsers ignore HSTS on HTTP responses; HTTP→HTTPS redirection alone does not fully protect the initial request.

## 7. HTTPS in the OAuth2 Login / OpenID Connect Flow

### 7.1. Authorization Code Flow Through a Proxy

```text
1. Browser -> https://app.example.com/private
2. App -> 302 /oauth2/authorization/company
3. Browser -> https://app.example.com/oauth2/authorization/company
4. App -> 302 https://login.example.com/.../authorize
          ?response_type=code
          &client_id=...
          &redirect_uri=https%3A%2F%2Fapp.example.com%2Flogin%2Foauth2%2Fcode%2Fcompany
          &state=... [&code_challenge=...]
5. Browser -> HTTPS IdP /authorize; user signs in
6. IdP -> Browser -> 302
          https://app.example.com/login/oauth2/code/company?code=...&state=...
7. Browser -> HTTPS app callback (via proxy)
8. App -> HTTPS IdP token endpoint (backend POST + code, client auth, PKCE verifier if applicable)
9. App establishes session per policy, returns HTTPS response/cookie
```

Steps 4 and 6 are **front-channel via the browser**. Step 8 is **back-channel app → IdP**. Never place `client_secret`, refresh tokens, or access tokens in browser query strings. `state` must be validated against the transaction, PKCE S256 is best practice for authorization code flow; for OIDC, handle `nonce` and issuer per the client library's role/capabilities.

### 7.2. Redirect URI Must Match Exactly

In Spring Security WebFlux, the default callback is:

```text
/login/oauth2/code/{registrationId}
```

With `registrationId=company`, configure the IdP with the exact registered URI:

```text
https://app.example.com/login/oauth2/code/company
```

Supplementary `application-prod.yml` example:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company-idp
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: openid,profile
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
        provider:
          company-idp:
            issuer-uri: https://login.example.com/realms/company
```

The provider section relies on OIDC discovery: the issuer URI must **match the metadata and actual `iss` claim** of the IdP; the authorize/token/JWK endpoints published by the IdP must also be verified and use HTTPS. `example.com` URLs here are illustrative names; in deployment, replace them with your real DNS/certificate/issuer. Client secrets are only injected via a secret store or protected environment variables.

With metadata from a trusted proxy, `{baseUrl}` resolves to `https://app.example.com`, not the upstream hostname or port. If `redirect_uri=http://app.internal.example:8443/...` or `redirect_uri=http://app.example.com/...` appears, inspect trust/scheme/port at the proxy and `server.forward-headers-strategy` first. Do not relax IdP policy to allow wildcard redirect URIs or HTTP callbacks in production to mask this bug.

### 7.3. Session Cookies and Cross-Site Callbacks

If the application uses OAuth2 Login and stores sessions server-side, the browser must send the cookie back to match the OAuth2 `state` on callback. Example safe header for a session cookie:

```http
Set-Cookie: SESSION=<id>; Path=/; Secure; HttpOnly; SameSite=Lax
```

- `Secure` sends the cookie only over HTTPS.
- `HttpOnly` reduces the risk of JavaScript reading the cookie; it does not prevent all XSS.
- `SameSite=Lax` usually works for OAuth2 code callbacks via **top-level GET navigation**, even when the IdP is cross-site.
- `SameSite=Strict` can prevent the browser from sending the cookie when returning from a cross-site IdP; `state`/session gets lost.
- When using `response_mode=form_post` (cross-site POST), `Lax` may not be sent; you must design `SameSite=None; Secure` cookies along with appropriate CSRF/session binding, accounting for browser third-party cookie restrictions.
- Restrict `Domain`; a cookie scoped only to the public host is usually safer than sharing across all subdomains. Check `Path`, lifetime, and session store when running multiple instances.

For APIs that only accept Bearer tokens from `Authorization`, server-side session cookies may be unnecessary. Even then, Bearer tokens must travel over HTTPS and must not leak via URLs, logs, referrers, or observability systems.

## 8. HTTPS from WebFlux to IdP: Proper Trust Store and Hostname

### 8.1. Endpoints Typically Called by the Backend

| Purpose | Example URL | Requirements |
| --- | --- | --- |
| OIDC discovery | `https://login.example.com/realms/company/.well-known/openid-configuration` | Trusted CA/hostname; verify `issuer` |
| Token exchange / refresh | `https://login.example.com/realms/company/protocol/openid-connect/token` | HTTPS, client authentication, never log code/secret/token |
| UserInfo | HTTPS endpoint published by IdP metadata | Send access token per contract, verify issuer/subject |
| JWK Set | HTTPS `jwks_uri` | Fetch public keys from trusted source; still verify JWT signature and claims |
| Opaque introspection | HTTPS introspection URI | Backend credentials, verify `active`, timeouts and error policy |

TLS authenticating the IdP server **does not replace** validating `iss`, `aud`, `exp`, `nbf`, signature, `nonce`, or `active` status. TLS protects **the transport to the right peer**; OAuth2/OIDC validation protects **the meaning of the token and authority**.

If using a private CA or internal IdP certificate, configure the Java/Netty HTTP client to trust **the exact approved CA**. Do not use `InsecureTrustManagerFactory`, `trustAll`, `curl -k`, skip hostname verification, or build an "accept all" `SSLContext` to fix TLS errors. The JVM has its own trust store; `curl` or `openssl` succeeding on the host does not guarantee Java trusts the same CA. Avoid inadvertently altering the process-wide trust store when only one HTTP client needs a dedicated trust bundle.

### 8.2. Resource Server: URIs Always HTTPS

For a JWT Resource Server, example configuration (in the Resource Server's **separate profile/context**):

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/company
```

For an opaque-token Resource Server:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.com/realms/company/protocol/openid-connect/token/introspect
          client-id: ${INTROSPECTION_CLIENT_ID}
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
```

Endpoint names and paths must come from the **actual IdP's** metadata/documentation. Both configurations only describe the authentication mechanism; use `.oauth2ResourceServer(oauth2 -> oauth2.jwt(...))` **or** `.opaqueToken(...)` depending on token type, and protect routes via `SecurityWebFilterChain`.

Do not switch `issuer-uri` to HTTP merely because deployment is inside a cluster; do not let firewall/DNS policies inadvertently allow calling an attacker-controlled IdP name. When the IdP has a certificate failure, the application must fail closed for authentication requiring network checks rather than disabling TLS verification or granting temporary access.

### 8.3. Timeouts, Retries, and Sensitive Data

TLS handshakes can fail due to CA, hostname, expired certificate, incompatible TLS version/cipher, SNI, or missing mTLS client certificate. Diagnose the specific cause and keep connection/response timeouts bounded. Use bounded retries for transient errors when logic permits; never fall back to HTTP or untrusted endpoints. Avoid recording token endpoint request bodies, `Authorization`, access tokens, refresh tokens, or client secrets in access logs, distributed tracing, or exception responses.

## 9. Risks Beyond TLS That HTTPS Alone Does Not Solve

**CSRF:** HTTPS does not stop cross-site requests carrying cookies. For browser sessions/logins, keep Spring Security's appropriate CSRF protection (unless there is a clear token architecture and justification), and verify OAuth `state`/PKCE/nonce. Do not disable CSRF globally to work around callback errors whose root cause is `SameSite` cookies or redirect URIs.

**XSS and mixed content:** HTTPS does not eliminate malicious JavaScript. All CSS, JS, fonts, images, API calls, and WebSockets must use HTTPS/WSS; an appropriate Content Security Policy helps reduce risk. `http://` assets on an HTTPS page can be blocked by browsers or create insecure content loading risks.

**CORS:** redirecting the browser to the IdP authorization endpoint **does not require** CORS between the app and the IdP; that is a top-level navigation. CORS applies when JavaScript wants to access cross-origin APIs. Never open `Access-Control-Allow-Origin: *` combined with credentials to "fix" login. Backend calls to token/introspection/JWKS over HTTPS are not subject to browser CORS.

**Token replay:** Bearer tokens can be replayed if leaked from logs, history, or clients; TLS mitigates eavesdropping, but you must restrict token scope/lifetime and consider sender-constrained tokens/mTLS/DPoP per system requirements.

**Open redirect and host spoofing:** do not take unvalidated `returnUrl`, `redirect_uri`, or `X-Forwarded-Host` to build arbitrary `Location` headers. The IdP must match redirect URIs exactly; the application must restrict accepted redirect hosts/targets.

## 10. Testing in the Deployed Environment

Run the following commands from a host with proper DNS and access to the environment; examples use illustrative domains and must be replaced with real ones.

### 10.1. Verify Browser → Proxy

```bash
# HTTP should redirect to canonical HTTPS (at the edge).
curl -sS -D - -o /dev/null http://app.example.com/public

# HTTPS must verify the certificate; do not add -k.
curl -sS -D - -o /dev/null https://app.example.com/public

# Inspect certificate chain and SNI.
openssl s_client -connect app.example.com:443 \
  -servername app.example.com -verify_return_error </dev/null
```

Expected results for the sample config: HTTP requests receive `308` and `Location: https://app.example.com/public`; HTTPS `/public` receives `200` and public content on GET; the certificate is valid for the hostname and trusted CA. Check `Strict-Transport-Security` on HTTPS responses when HSTS is enabled. Never add `-k` to QA scripts because it hides certificate failures.

### 10.2. Verify Proxy → Application

- Nginx is using `proxy_pass https://...` and `proxy_ssl_verify on`; the upstream certificate has SAN `app.internal.example` and chains to the configured CA.
- In logs/metrics, there are no 502/525/SSL handshake errors between proxy and app.
- Firewall/network policies prevent the Internet from reaching `:8443` directly and bypassing forwarded-header sanitization.
- If the upstream certificate is temporarily replaced in testing with a wrong-name/expired certificate, the connection must **fail**; never automatically skip verification to keep traffic flowing.

### 10.3. Test OAuth2 URLs and Spoofed-Header Resistance

```bash
# The /oauth2/authorization/company endpoint typically returns 302 to the IdP.
curl -sS -D - -o /dev/null \
  https://app.example.com/oauth2/authorization/company

# Intentionally send spoofed forwarded host/proto from outside.
curl -sS -D - -o /dev/null \
  -H 'Forwarded: proto=http;host=attacker.example' \
  -H 'X-Forwarded-Proto: http' \
  -H 'X-Forwarded-Host: attacker.example' \
  https://app.example.com/oauth2/authorization/company
```

What to observe: `Location` points to the **trusted IdP**; the (URL-encoded) `redirect_uri` parameter contains only `https://app.example.com/login/oauth2/code/company`, with no `http://`, `attacker.example`, or `app.internal.example`. If the app does not use OAuth2 Login, test the same principle on routes that actually generate absolute redirects/links.

### 10.4. Verify Cookies and Callbacks

Check `Set-Cookie` after session creation and successful callback: it must include `Secure`, `HttpOnly`, and the designed `SameSite`/Path/Domain. Run a real browser flow because `curl` does not accurately reproduce SameSite cookie policies. Observe network traffic in the browser: HTTPS authorize → HTTPS callback → HTTPS backend token exchange → app creates session → protected page loads. Losing the session after callback is usually related to SameSite, Domain, Path, or session store—not because HTTPS failed.

### 10.5. Verify App → IdP

From the backend runtime environment, verify IdP DNS/SNI/cert chain; then run **integration tests using the application's actual HTTP client** to verify the Java trust store, timeouts, and error handling. Simulate an untrusted certificate, hostname mismatch, IdP 5xx, or network loss: authentication must fail safely, with no HTTP fallback or token-check bypass. Never extract or print real tokens to terminal/CI logs.

## 11. Operational Failure Matrix and Troubleshooting

| Symptom | Common Cause | Verification and Fix |
| --- | --- | --- |
| 301/302/307/308 redirect loop | Browser uses HTTPS but app thinks request is HTTP | Check `X-Forwarded-Proto`, transformer, and HTTPS redirect placement |
| IdP reports `redirect_uri_mismatch` | Callback has `http`, internal host, port 8443, or wrong path | Check `Location` and exact registered URI at the IdP |
| Browser callback fails with invalid state/session | `Secure`/`SameSite`/Domain/Path cookie mismatch; unshared session across instances | Check browser cookie jar, callback route, session store; preserve `state` binding |
| Browser certificate warning | Expired cert, broken chain, SAN mismatch | Verify public cert with SNI/hostname and standard CA |
| Proxy returns 502 right after enabling upstream HTTPS | Wrong upstream SNI/CA/SAN or app not yet listening TLS on 8443 | Check `proxy_ssl_*`, keystore, Netty listener, CA, and DNS |
| Backend cannot call IdP | Java trust store missing CA, hostname mismatch, wrong outbound proxy, TLS version | Check SSL handshake stacktrace, DNS/SNI; configure proper trust, never trust-all |
| HSTS header missing | Tested HTTP only; app does not see secure request; edge not emitting header | Check public HTTPS response, forwarded scheme, and layer owning HSTS |
| `Location` contains attacker host | Proxy does not overwrite `Forwarded`/`X-Forwarded-Host` | Strip/overwrite at edge, enforce allowed hosts, block direct app access |
| API requests cannot authenticate during IdP outage | Introspection/JWKS requires network while IdP/CA unavailable | Check timeout/cache policy, surface incident; **never** fail-open |
| Cookie missing `Secure` | Misconfigured cookie policy or cookie emitter bypassing Boot settings | Check WebFlux `server.reactive.session.cookie.*` and actual resolver/session framework |

### A Before–After Scenario

**Before:** browser calls `https://app.example.com`, edge forwards to `http://app:8080`, passes through browser-supplied `X-Forwarded-Proto`; Spring does not know the public address. `/oauth2/authorization/company` generates `redirect_uri=http://app:8080/login/oauth2/code/company`. The IdP rejects it, or the browser is redirected incorrectly. Attackers can also spoof the host.

**After:** edge accepts only valid public HTTPS, normalizes `Host=app.example.com`, `X-Forwarded-Proto=https`, `X-Forwarded-Host=app.example.com`, and blocks spoofed `Forwarded`; proxy → app uses verified TLS; `server.forward-headers-strategy=framework` lets WebFlux infer the exact public URI. The IdP receives `redirect_uri=https://app.example.com/login/oauth2/code/company`, callback returns over HTTPS; backend exchanges the code over HTTPS with an IdP having a valid CA/SAN. Each point is independently testable without disabling certificate verification.

## 12. Production Deployment Checklist

- [ ] Public domain serves sensitive resources only over HTTPS; HTTP is redirected cleanly; certificate full chain, SAN, SNI, and expiration are verified.
- [ ] Proxy → WebFlux TLS is protected per the approved trust boundary; if HTTPS, **upstream certificate verification is enabled**; internal app port is unreachable from the Internet.
- [ ] Proxy strips untrusted `Forwarded` and `X-Forwarded-*` values and emits canonical host/scheme/port.
- [ ] Spring WebFlux processes forwarded headers properly via `server.forward-headers-strategy`; no Servlet filter added to fix reactive issues.
- [ ] HTTPS redirect does not loop infinitely and does not expose internal hostnames/ports in absolute links.
- [ ] HSTS is present on public HTTPS responses; `includeSubDomains`/`preload` are used only after evaluating full-domain impact.
- [ ] OAuth2/OIDC uses HTTPS IdP issuer and callback URI **matching registration exactly**; `state`, PKCE/nonce are applied per flow.
- [ ] Session cookies have appropriate `Secure`, `HttpOnly`, SameSite, Path, and Domain; browser callback works behind the proxy.
- [ ] WebFlux → IdP connections (discovery/token/JWKS/introspection/userinfo) verify CA and hostname; no trust-all or HTTP fallback exists.
- [ ] Client secrets, keystore passwords, private keys, Bearer tokens, and authorization codes do not appear in Git, unintended URLs, or access logs.
- [ ] Tests cover forwarded-header spoofing, redirect URI, certificate mismatch, IdP TLS failure, and timeouts; failures never produce an unintended authenticated principal.

## Authoritative Resources for Further Study

- Spring Boot 3.3 — [Common Application Properties (forward headers, reactive session cookies, SSL)](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/).
- Spring Boot — [Running Behind a Front-end Proxy Server](https://docs.spring.io/spring-boot/reference/how-to/webserver.html#howto.webserver.configure-behind-a-proxy).
- Spring Security 6.5 — [Reactive HTTP: redirect to HTTPS, HSTS, proxy](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/http.html).
- Spring Security 6.5 — [Reactive Security HTTP Response Headers](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/headers.html).
- Spring Security 6.5 — [OAuth2 Login core configuration, redirect URI](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/login/core.html).
- Spring Framework — [ForwardedHeaderTransformer JavaDoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/server/adapter/ForwardedHeaderTransformer.html).
- IETF — [RFC 7239: Forwarded HTTP Extension](https://www.rfc-editor.org/rfc/rfc7239); [RFC 9700: OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700).
- IETF — [RFC 6797: HTTP Strict Transport Security](https://www.rfc-editor.org/rfc/rfc6797).

**Target outcome:** ability to prove from **outside to inside** that browser, proxy, WebFlux, and IdP all communicate over appropriately protected transports; OAuth2 URLs/cookies reflect the exact public HTTPS hostname; and all certificates and forwarded headers are validated against the proper trust boundaries.