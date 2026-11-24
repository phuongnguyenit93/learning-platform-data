# Public Address, HTTPS, and Callbacks Behind a Reverse Proxy

> **Module:** Spring Security – federation. **Parent topic:** Deployment and Operations. **Problem:** A Spring Boot/Spring Security application runs internally at `http://127.0.0.1:8080` or `http://portal-service:8080`, while users and the Identity Provider (IdP) only see `https://portal.example.org`. If the reverse proxy, Spring, and the IdP are inconsistent on **scheme, host, port, path, and callback**, SAML2, OAuth2/OIDC, CAS, and Kerberos/SPNEGO can fail even when credentials and signatures are valid. This article designs a canonical public origin, trust boundaries for `Forwarded`/`X-Forwarded-*`, TLS termination, fixed URLs, and a verification plan. Examples target **Java 17, Spring Boot 3.5.x, Spring Security 6.5.x, and Nginx**; adapt them to your actual architecture and test in an HTTPS environment with an IdP sandbox.

## 1. Learning Outcomes

After this lesson, you should be able to:

1. Distinguish the **public URL** seen by the browser/IdP from the **internal URL** of the servlet container, and explain why Spring may incorrectly generate `http://portal-service:8080/...`.
2. Diagram the **Browser → Edge/TLS → Reverse proxy → Spring Security → IdP → callback → Spring Security** flow along with trust boundaries.
3. Define **one canonical public origin** consisting of scheme/host/port and a clear policy for context path; never construct URIs from arbitrary Internet `Host` or `X-Forwarded-Host` values.
4. Configure the proxy to **strip/overwrite client-sent Forwarded/X-Forwarded*** headers, accept only headers set by a trusted proxy, and restrict direct access to the backend.
5. Configure `server.forward-headers-strategy=framework` or `native` appropriately for the context; understand `ForwardedHeaderFilter` and avoid processing headers twice.
6. Verify **OAuth2/OIDC redirect_uri** `{baseUrl}/login/oauth2/code/{registrationId}`, `state`, PKCE, and `nonce` after deploying HTTPS.
7. Verify **SAML2 Entity ID, ACS URL, SLO callback, metadata**, `Destination`/`Recipient`/`Audience`, and signatures when behind a proxy.
8. Verify **CAS service identifier, pgtUrl HTTPS callback**; distinguish CAS callbacks from OIDC and SAML.
9. Verify **Kerberos/SPNEGO HTTP/FQDN** and `WWW-Authenticate: Negotiate` through an edge proxy without confusing the internal host with the SPN.
10. Handle **TLS termination, HTTPS backhaul/mTLS, HSTS, Secure/HttpOnly/SameSite cookies, CSRF, session affinity/shared state, and multi-node deployments**.
11. Run **standalone Java 17** code to validate a callback URL allowlist, distinguish origin/path/URI-shape failures, and produce exact stdout.
12. Design preflight/test matrix/rollout/rollback, and monitor redirects and callback errors without **logging SAML assertions, authorization codes, tokens, or session cookies**.

**Prerequisites:** HTTP request/response/redirect, TLS/X.509, reverse proxy/load balancer, Spring MVC request URL, Spring Security login endpoints, OAuth2 Authorization Code, SAML2 SP/IdP, CAS service tickets, Kerberos SPN, Docker/Kubernetes networking.

## 2. Problem: Public URL Differs from Internal URL

Example architecture:

~~~text
Browser / IdP
       |
       | HTTPS https://portal.example.org
       | TLS cert CN/SAN=portal.example.org
       v
[Nginx / LB / Ingress]   <-- TRUST BOUNDARY 1
       |
       | HTTP http://portal-service:8080
       | Host / Forwarded / X-Forwarded-* set by proxy
       v
[Spring Boot JVM]        <-- TRUST BOUNDARY 2
       |
       +-- OAuth2 authorization request
       |     -> redirect_uri=https://portal.example.org/login/oauth2/code/corporate
       |
       +-- SAML AuthnRequest / SP metadata
       |     -> ACS=https://portal.example.org/login/saml2/sso/corporate
       |     -> SLO=https://portal.example.org/logout/saml2/slo
       |
       +-- CAS service validation
       |     -> service=https://portal.example.org/login/cas
       |
       +-- SPNEGO Negotiate
             -> HTTP/portal.example.org@EXAMPLE.ORG
~~~

**What the user/IdP must see:** `https://portal.example.org`. **What the JVM may see if misconfigured:** `http://portal-service:8080`. If the application uses a request-derived base URL without handling the reverse proxy properly, it may generate:

~~~text
Incorrect:
  OAuth redirect_uri=http://portal-service:8080/login/oauth2/code/corporate
  SAML ACS=http://portal-service:8080/login/saml2/sso/corporate
  SAML SP entityID=http://portal-service:8080/saml2/service-provider-metadata/corporate
  CAS service=http://portal-service:8080/login/cas
  Location: http://portal-service:8080/login

Correct:
  OAuth redirect_uri=https://portal.example.org/login/oauth2/code/corporate
  SAML ACS=https://portal.example.org/login/saml2/sso/corporate
  SAML SP entityID=https://portal.example.org/saml2/service-provider-metadata/corporate
  CAS service=https://portal.example.org/login/cas
  Location: https://portal.example.org/login
~~~

The SAML signature and TLS certificate may be completely valid yet the IdP still rejects due to **URI mismatch**. In other cases, the IdP allows login to succeed, but the browser cannot return to the internal callback, causing a 302/401 loop. **Do not fix this by exposing the internal hostname to the Internet or relaxing the IdP redirect allowlist to a wildcard.**

### 2.1. Terminology That Must Be Used Consistently

| Term | Example | What does it mean? |
| --- | --- | --- |
| Public origin | `https://portal.example.org` | Scheme + host + effective port; approved trusted address |
| Public base URL | `https://portal.example.org` or `https://portal.example.org/app` | Origin plus path prefix if the application is published under a prefix |
| Internal backend | `http://portal-service:8080` | Address the proxy uses to call the JVM, **not** registered with the IdP |
| External callback | `https://portal.example.org/login/oauth2/code/corporate` | URL the IdP/authorization server redirects the browser back to |
| SAML ACS | `https://portal.example.org/login/saml2/sso/corporate` | SP endpoint receiving SAMLResponse |
| SAML SLO | `https://portal.example.org/logout/saml2/slo` | SP endpoint receiving SAML LogoutRequest/LogoutResponse |
| CAS service | `https://portal.example.org/login/cas` | Exact identifier validated by the CAS server against the ticket |
| CAS PGT callback | `https://portal.example.org/login/cas/proxyreceptor` | Server-to-server HTTPS CAS→SP endpoint to deliver the PGT |
| Kerberos SPN | `HTTP/portal.example.org@EXAMPLE.ORG` | Kerberos identity corresponding to the public hostname, not a URL |
| IdP issuer | `https://idp.example.org/realms/corporate` | Identifier of the IdP/OP; not the Portal's public origin |

**SAML Entity ID can be a URN**, for example `urn:portal:prod:sp`, and does not have to be a URL. However, the Entity ID must be **stable and match exactly** between the SP and IdP; ACS/SLO must still be valid public endpoints. With Spring SAML2 defaults, the entity ID is often derived from `{baseUrl}/saml2/service-provider-metadata/{registrationId}`, so a wrong public base URL can unintentionally change **both the Entity ID and the ACS**.

## 3. Standardize the Canonical Public Origin Before Configuring

An approved contract for the production environment:

~~~text
Environment: prod
Canonical public scheme: https
Canonical public host: portal.example.org
Canonical port: 443 (implicit, omit :443 when the registry uses portless URIs)
Canonical base path: / (no prefix)
Application internal host: portal-service
Application internal port: 8080
Trusted edge proxy: ingress/proxy group with governed network/identity
OAuth2 callback: /login/oauth2/code/corporate
SAML ACS: /login/saml2/sso/corporate
SAML SLO: /logout/saml2/slo
CAS service: /login/cas
CAS PGT receptor: /login/cas/proxyreceptor
Kerberos service principal: HTTP/portal.example.org@EXAMPLE.ORG
~~~

For other environments: `https://portal-stg.example.org` and `https://portal-dev.example.org` must be **separate registrations** with different keys/clients/metadata/environments. Do not register a production client with redirect URI `http://localhost:8080` just for testing if policy forbids it. Do not mix staging SAML Entity IDs/certificates with prod.

**URI principles:**

- **Scheme:** HTTPS for browser/IdP-facing URLs. Internal `http://` is only valid behind a protected trust boundary; never leak it into metadata or redirects.
- **Host:** Lowercase/canonical FQDN owned by the organization. Do not derive host from browser input without checking allowed hosts; avoid IDN homographs, trailing dots, unusual characters, suffix matching, and arbitrary IP literals.
- **Port:** Default 443 is usually written without `:443`; some IdPs compare URIs **as exact strings** and treat differences in port/encoding/path as a mismatch. Choose the exact registered form.
- **Path:** Distinguish `/login/oauth2/code/corporate`, `/login/saml2/sso/corporate`, and `/logout/saml2/slo`. Trailing slashes, case differences, or percent-encoding can cause a mismatch.
- **Query:** OAuth2 callbacks carry `?code=...&state=...` when the IdP returns; the **registered redirect_uri** contains only the approved base, never accepting `next=evil` or user-supplied URIs. SAML POST callbacks receive form `SAMLResponse` and must not let users arbitrarily set `Recipient`.
- **Fragment:** Do not use fragments to pass authorization codes/server-side callbacks when the framework flow uses Authorization Code.
- **Public path prefix:** If published at `/portal` while the container runs at root `/`, prefix handling must be designed **once**, avoiding double prefixes or dropped prefixes.

### 3.1. Do Not "Fix" URLs with String Replacement

**Incorrect:**

~~~java
// Anti-pattern example: overly simplistic string replacement of http -> https.
String callback = request.getRequestURL().toString()
        .replace("http://", "https://");
~~~

If the host is already `internal-host:8080`, this still produces `https://internal-host:8080`, which is wrong. If the request has an attacker-controlled `Host`, it generates a callback/redirect to the attacker. Moreover, replacing the scheme does not automatically fix `port`, `context-path`, `forwarded prefix`, or the IdP allowlist.

**Correct in principle:** Use a **canonical public base URL in configuration**, or a request-derived URL only behind a **trusted reverse proxy that overwrites forwarded headers and validates Host**. Spring Security URI templates `{baseUrl}` are only a URL-building mechanism; the trustworthiness of the resolved value is still guaranteed by topology.

## 4. Forwarded Headers: Very Useful and Very Dangerous

When TLS terminates at the reverse proxy, the JVM receives an internal request with `scheme=http`, `serverName=portal-service`, `serverPort=8080`. The reverse proxy can convey the public semantics via:

~~~http
Host: portal.example.org
X-Forwarded-Proto: https
X-Forwarded-Host: portal.example.org
X-Forwarded-Port: 443
X-Forwarded-For: 192.0.2.40
~~~

Or per RFC 7239:

~~~http
Forwarded: for=192.0.2.40;proto=https;host=portal.example.org
~~~

**However:** Internet clients **can also send those headers themselves**. Therefore, you must never configure Spring to "trust X-Forwarded-Host on every request" while the backend remains directly reachable or the edge merely appends to what the client sent.

### 4.1. Two-Layer Trust Boundary

~~~text
Attacker browser:
  GET /oauth2/authorization/corporate
  Host: portal.example.org
  X-Forwarded-Host: evil.example
  X-Forwarded-Proto: http

Secure edge proxy:
  - validates public host
  - strips client-supplied Forwarded and X-Forwarded-*
  - sets X-Forwarded-Host = portal.example.org
  - sets X-Forwarded-Proto = https
  - sets X-Forwarded-Port = 443
  - forwards only to the private-network backend

Spring:
  - sees only headers controlled by the edge
  - resolves {baseUrl} as https://portal.example.org
  - emits the correct callback URL
~~~

**If the edge does not scrub:** Some `ForwardedHeaderFilter` configurations will interpret `X-Forwarded-Host: evil.example` as the public host and the app may emit `Location: https://evil.example/...`, wrong OAuth2 `redirect_uri`, password reset poisoning, cache poisoning, or open redirects. In some cases the IdP rejects immediately; in other cases an attacker exploits other URLs in the application. Do not rely on strict IdP URI matching as a substitute for host validation.

### 4.2. Header Precedence and Multi-Proxy Chains

Multiple layers can generate headers:

~~~text
Browser → CDN → LB → Nginx ingress → JVM

Forwarded: for=...;host=...;proto=...
X-Forwarded-For: client, CDN, LB
X-Forwarded-Host: ...
X-Forwarded-Proto: ...
~~~

Decide **one place** that owns the canonical public scheme/host/port and subsequent trust layers. The Internet-facing edge must strip untrusted headers; downstream proxies only trust authenticated/governed predecessors. If both `Forwarded` and `X-Forwarded-*` are sent and conflict, different frameworks may prioritize them differently, causing wrong redirects or Host spoofing. Standardize on one set or clear the other—never leave two conflicting values.

`X-Forwarded-For` is an IP chain; its order and true client IP are only trustworthy if you know the list of permitted proxies. Do not take the first element for authorization, rate limiting, or anti-abuse when the client can spoof it. With Nginx `real_ip`, only trust `set_real_ip_from` for known upstreams; never turn `0.0.0.0/0` into a trusted proxy list.

### 4.3. Spring Framework ForwardedHeaderFilter

`ForwardedHeaderFilter` wraps the request so Spring components see the scheme/host/port from `Forwarded` or `X-Forwarded-*` and removes those headers after processing. It **does not authenticate the trustworthiness of the source proxy**; Spring Framework docs require the edge proxy to strip Internet-supplied headers and set fresh ones. The filter can be configured with `removeOnly` when you want to **discard forwarded headers without using their values**.

**Pitfall:** Do not enable container-native forwarding and also manually register another `ForwardedHeaderFilter` without understanding filter ordering and semantics. Avoid multiple sources of truth that rewrite the request scheme/host twice.

## 5. Spring Boot 3.5: Choosing One Forwarded-Header Strategy

Spring Boot provides the property:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Options:

| Strategy | How it works | When to consider |
| --- | --- | --- |
| `none` | Does not use forwarded headers to alter the request URL | App uses fixed canonical URLs or has no trusted reverse proxy; does not rely on request-derived baseUrl |
| `native` | Container/server handles headers natively (e.g., Tomcat RemoteIpValve when Boot configures it) | Platform standardizes/trusts proxies at the container layer and understands `X-Forwarded-*` behavior |
| `framework` | Spring uses `ForwardedHeaderFilter` (Servlet) or WebFlux equivalent | Spring must resolve URLs from trusted edge headers, supporting scheme/host/prefix per framework semantics |

**Use `framework` in this example** because there is a managed Nginx proxy, the backend is not exposed to the Internet, the edge overwrites forwarded headers, and Spring Security relies on `{baseUrl}`. Do not assume `framework` blocks spoofed `Forwarded` headers on its own. For applications traversing multiple proxies or complex headers, normalizing at the edge and testing the actual backend scheme/host/port are mandatory.

### 5.1. application.yml for a Servlet App

~~~yaml
server:
  port: 8080
  forward-headers-strategy: framework
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: lax

management:
  endpoints:
    web:
      exposure:
        include: health,info
~~~

**Explanation:** `server.port=8080` is the backend port, not the public port. `secure=true` on the session cookie ensures the browser sends it only over HTTPS (TLS termination still counts on the client side). `http-only=true` reduces JavaScript access. `same-site=lax` fits many OIDC Authorization Code GET callbacks, but **may not work for cross-site SAML HTTP-POST ACS**. This article will show how to test and set the proper cookie policy in section 12. Do not expose sensitive actuator endpoints to the Internet; review `health/info` exposure as well.

**Do not misconfigure:**
- `server.forward-headers-strategy=framework` and `native` simultaneously (the property takes a single value).
- A separate `ForwardedHeaderFilter` bean for the same purpose if Boot already configures one, unless you control the filter chain and have an explicit requirement.
- An invented property like `trustAllForwardedHeaders=true`; that is not a standard property guaranteeing trust.
- `X-Forwarded-Proto: https` in the browser to "force Spring to understand HTTPS."

### 5.2. Confirm with Safe Request Diagnostics

In a sandbox, a verification `HandlerInterceptor`/controller can print:

~~~text
request.getScheme()     -> https
request.getServerName() -> portal.example.org
request.getServerPort() -> 443
request.isSecure()      -> true
public app base URL     -> https://portal.example.org
~~~

Display this only in a test environment or on a protected endpoint; never expose request headers/cookies or internal info on a public diagnostic page. Once verified, **disable the diagnostics endpoint**. Remember that `getRequestURL()` may include the actual request path; do not use it as a redirect_uri template when the path is `/oauth2/authorization/corporate`.

### 5.3. Trusted Proxy Does Not Mean Blindly Trusting Every Header

Even when clients only go through Nginx, you must:
- Restrict public `Host`/SNI to approved FQDNs.
- Strip client-supplied `Forwarded` and `X-Forwarded-*` and overwrite them accurately.
- Prevent direct access to the backend service via public IP, NodePort, exposed pod port, or an alternate LB.
- Protect Kubernetes ingress configs and service mesh policies from untrusted edits.
- Audit logging/redaction and redirect egress.
- Use only published origins from an environment allowlist; never customize the host from user input.

## 6. Nginx at the Edge: Sample Config Controlling Public Host

Same-host test example: Nginx receives `https://portal.example.org` and proxies to `127.0.0.1:8080`. In Kubernetes, change the upstream to a ClusterIP/internal address protected by a NetworkPolicy.

~~~nginx
# Illustrative Nginx server blocks; configure TLS ciphers,
# stapling, certificate renewal, and access logs per actual policy.

server {
    listen 80;
    server_name portal.example.org;
    return 308 https://portal.example.org$request_uri;
}

server {
    listen 443 ssl;
    server_name portal.example.org;

    ssl_certificate     /etc/nginx/tls/fullchain.pem;
    ssl_certificate_key /etc/nginx/tls/privkey.pem;

    # Optional once all content/subdomains are fully on HTTPS.
    add_header Strict-Transport-Security "max-age=31536000" always;

    location / {
        proxy_pass http://127.0.0.1:8080;

        # Canonical public host: do not take from attacker headers.
        proxy_set_header Host              portal.example.org;
        proxy_set_header X-Forwarded-Host  portal.example.org;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Port  443;

        # Single trusted edge pattern, preserving remote_addr of the connection to Nginx.
        proxy_set_header X-Forwarded-For   $remote_addr;
        proxy_set_header X-Real-IP         $remote_addr;

        # Do not forward client-supplied Forwarded header.
        proxy_set_header Forwarded "";
        proxy_set_header X-Forwarded-Prefix "";

        proxy_http_version 1.1;
        proxy_set_header Connection "";
    }
}
~~~

**Sample scope:**
- Nginx `server_name` alone does not guarantee rejecting unknown hostnames if it is the virtual host/default server: you need a **default/catch-all vhost** with a policy to reject unknown hosts and proper TLS SNI/Host routing. Test with `Host: evil.example` to ensure requests are not routed to Portal to generate bad callbacks.
- `$remote_addr` in Nginx is the direct peer. If a CDN/LB sits in front of Nginx, it is the LB/CDN IP, **not** the end user; adjust the trusted IP chain via a `real_ip` allowlist, and do not use `proxy_add_x_forwarded_for` unless you scrub the incoming chain first.
- `proxy_pass http://127.0.0.1:8080` only makes sense when Nginx and the JVM share a host. When they are on separate hosts, consider TLS backhaul or mTLS; do not leave unencrypted HTTP on a shared network.
- HSTS must be approved for the hostnames/subdomains currently in use; `includeSubDomains`/`preload` are high-impact decisions—do not enable them blindly from an example before subdomains are ready.
- `return 308` on port 80 is suitable for HTTP→HTTPS redirection while preserving method, but do not rely on HTTP redirects for SAML POST callbacks sent to the wrong host/scheme. **Register the IdP callback directly as HTTPS** so the browser never redirects a POST and loses the body/cookies.
- Certificate/key paths in Nginx are TLS keys for the public host, **distinct** from the SAML SP signing key, CAS PGT credentials, or Kerberos keytab.

### 6.1. Is “X-Forwarded-Host = $host” Safe Enough?

Only if the vhost/edge has already verified **$host belongs to an allowlist**. If the Nginx default vhost accepts an arbitrary `Host` and sets `X-Forwarded-Host=$host`, an attacker can push `evil.example` into Spring even though Spring only receives traffic from "trusted Nginx." For illustration, the config above sets the **literal** `portal.example.org`. In environments serving multiple permitted hosts, use a reviewed map/route allowlist rather than accepting arbitrary user input values.

### 6.2. CDN→ALB→Ingress Chain

If there are multiple hops, clearly specify:
1. Which layer terminates public TLS?
2. Which layer receives/strips client-supplied forwarded headers?
3. Which layer populates canonical `proto/host/port/prefix`?
4. Which internal hops have a trusted identity?
5. Does container native or Spring framework consume the headers?
6. Is there any bypass path reaching the service directly?

Test from outside the Internet and from inside the cluster using an untrusted pod: direct backend requests must not be able to force generated URLs using forged headers. "Spring accepts forwarded headers" is only format processing; it cannot tell which edge is genuine unless network policy and proxy configuration enforce it.

## 7. OAuth2 / OIDC: redirect_uri Is an Exact Contract

Spring Security OAuth2 Login in the Servlet stack typically uses:

~~~text
Start authorization:
  GET https://portal.example.org/oauth2/authorization/corporate

Registered redirect URI:
  https://portal.example.org/login/oauth2/code/corporate

Default Spring template:
  {baseUrl}/login/oauth2/code/{registrationId}

Internal backend:
  http://portal-service:8080
~~~

Flow:

~~~text
Browser -> Portal /oauth2/authorization/corporate
Portal -> 302 IdP /authorize
  client_id=...
  redirect_uri=https://portal.example.org/login/oauth2/code/corporate
  state=...
  code_challenge=... (PKCE when configured/used)
  nonce=... (OIDC request when applicable)

Browser -> IdP login/consent
IdP -> Browser redirect:
  https://portal.example.org/login/oauth2/code/corporate
    ?code=[redacted]
    &state=[redacted]

Portal:
  validates state/correlated authorization request
  exchanges code over TLS, validates tokens/issuer/audience/nonce
  sets secure application session
~~~

**Typical failure:** The IdP shows `redirect_uri_mismatch` because Spring generates `http://portal-service:8080/...` or `http://portal.example.org/...` (wrong scheme). Do not fix this by registering `http://portal-service:8080` at the IdP, adding wildcards, or disabling verification; fix the public URL/trusted forwarding.

### 7.1. Spring Boot OAuth2 Client Config (Fragment)

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: corporate-idp
            client-id: portal-web
            client-secret: "${OIDC_CLIENT_SECRET}"
            scope: openid,profile,email
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
        provider:
          corporate-idp:
            issuer-uri: https://idp.example.org/realms/corporate
~~~

**Explanation:** This fragment requires a real IdP/Authorization Server and a secret injected from a secret manager; it contains **no** real credentials. `issuer-uri` is the identifier for discovering/verifying the OP/IdP, not the Portal public URL. `redirect-uri` is the client redirect URI; the IdP must have the exact string registered. `{baseUrl}` is resolved by Spring from the trusted request/public config. If using Spring Authorization Server or a different tenant domain, resolve provider metadata/JWKS/TLS per issuer; do not change `issuer-uri` to the Portal host.

**Do not conflate redirect_uri and token endpoint:** Browser callbacks go to Portal; the Portal backend calls the IdP token endpoint **server-to-server**. The backend may reside on a private network; the callback is not the token endpoint. Never expose the client secret to the browser or logs.

### 7.2. Concerns Beyond the URL

- **`state`:** Binds the callback to the browser/session authorization request; do not skip the state check when the callback lands on a different node.
- **PKCE:** Use when configured/supported by the provider, especially for public clients; the URL does not replace code challenge/verifier.
- **OIDC `nonce`:** When using OIDC, require/validate nonce per flow; a callback hitting the right host does not prove the ID Token is valid.
- **`iss`, `aud`, `exp`, signature/JWKS:** Must still be fully validated after code exchange.
- **Open redirect:** Never place a user-provided `returnUrl` into `redirect_uri` and never redirect the browser to an arbitrary domain after login.
- **Multi-tenant:** `registrationId=corporate` must map to a specific approved IdP/client; never select the authorization server host from `X-Forwarded-Host` or a query parameter.
- **Session cookie:** Cross-site front-channel callbacks are usually GET; SameSite Lax typically allows top-level GETs, whereas SAML POST behaves differently.
- **Codes/tokens:** Do not record full `code`, `state`, or `id_token` in access logs/analytics/Referer; limit callback caching and leakage.

### 7.3. OAuth2/OIDC Positive/Negative Table

| Test | Expected |
| --- | --- |
| Arriving via public HTTPS, normal proxy headers | Authorization request contains `redirect_uri=https://portal.example.org/login/oauth2/code/corporate` |
| Edge omits X-Forwarded-Proto | Test catches Spring generating `http://...`; do not "approve" the wrong URI |
| Client sends forged `X-Forwarded-Host: evil.example` | Edge scrubs; Spring still uses approved host |
| Callback on wrong path | Not handled by the login filter for the right registration |
| Callback with wrong `state` | Rejected; no authenticated session created |
| Callback missing `code`/error response | Handled as failure, never treated as successful login |
| Callback reaches another node, request state stored only on node A | Detects correlation failure, handled via session store/affinity |
| Cookie SameSite policy blocks callback | Test in a real browser, balancing HTTPS/CSRF |
| IdP has exact redirect allowlist | Rejects http/private/evil URIs |
| Wrong IdP issuer/JWKS | Token validation rejects without relaxing signature checks |

## 8. SAML2: Entity ID, ACS, SLO, and Metadata Must Use Public Values

Spring Security SAML2 Service Provider typically uses:
- **Default SP Entity ID:** `{baseUrl}/saml2/service-provider-metadata/{registrationId}`.
- **ACS:** `/login/saml2/sso/{registrationId}` per registration/default matcher.
- **Metadata publication:** `/saml2/metadata/{registrationId}` or `/saml2/service-provider-metadata/{registrationId}` depending on DSL/version; enable `saml2Metadata()` when needed.
- **SLO listener:** `/logout/saml2/slo` in Spring SAML2 logout when configured/enabled.

An IdP may require the SP issuer/entity ID to **remain constant across all deployments** even when browser URLs change. Changing the entity ID from `urn:portal:prod:sp` to `https://portal.example.org/...` must be treated as **changing the identity federation**, not merely adjusting a reverse proxy. Coordinate metadata and the IdP trust registry.

### 8.1. AuthnRequest and SAMLResponse Flow Through a Proxy

~~~text
Browser -> https://portal.example.org/saml2/authenticate/corporate
SP -> AuthnRequest:
  Issuer = https://portal.example.org/saml2/service-provider-metadata/corporate
  AssertionConsumerServiceURL = https://portal.example.org/login/saml2/sso/corporate
  Destination = https://idp.example.org/sso

IdP -> Browser HTTP-POST:
  https://portal.example.org/login/saml2/sso/corporate
  form SAMLResponse=[redacted] RelayState=[redacted]

SP validates:
  trusted IdP signature
  expected Issuer
  Destination / Recipient = public ACS expected by registration
  AudienceRestriction includes expected SP Entity ID
  InResponseTo matches pending AuthnRequest (SP-initiated)
  time conditions / replay protections / registered ACS
~~~

**These fields are not the same URI:**
- `AuthnRequest.Destination`: the **IdP's** SSO endpoint.
- `AuthnRequest.Issuer`: the **SP entity ID**.
- `AssertionConsumerServiceURL`: where the browser will POST SAMLResponse—the **SP public ACS**.
- `SAMLResponse.Destination` and `SubjectConfirmationData.Recipient`: usually the **SP public ACS URL**, which must match the registration.
- `AudienceRestriction`: the **SP entity ID**, which may be a URN.
- `InResponseTo`: request ID; not a URL.
- `RelayState`: binding/correlation; must not become an open redirect or select an untrusted IdP.

If the reverse proxy causes `Recipient=http://portal-service:8080/login/saml2/sso/corporate` in the SP's expected configuration while the IdP sends `https://portal.example.org/...`, Spring may reject the SAMLResponse **even when the signature is valid**. Do not disable Recipient/Destination/Audience validation to make it pass.

### 8.2. Spring Boot SAML Configuration (Fragment)

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corporate:
            entity-id: "https://portal.example.org/saml2/service-provider-metadata/corporate"
            assertingparty:
              metadata-uri: https://idp.example.org/saml/metadata
            singlelogout:
              url: "https://portal.example.org/logout/saml2/slo"
~~~

This fragment requires the `spring-security-saml2-service-provider` module, test IdP metadata, registration, and appropriate signing/decryption credentials. `singlelogout.url` specifies the SLO callback **at the SP**, **not** the IdP SLO URL. SLO usually requires an SP PKCS#8 signing private key and an X.509 certificate trusted by the IdP. If the system does not use SLO, do not enable a dummy endpoint just to "complete the metadata."

**ACS:** By default it can be resolved from the request's public base URL/path. If the IdP requires a **fixed path**, configure `RelyingPartyRegistration`/Boot properties for the appropriate Assertion Consumer Service Location and verify the actual generated metadata; do not assume `entity-id` sets the ACS automatically. Post-deployment metadata is the **source of verification**; compare full URIs, not just hostnames.

### 8.3. SLO with TLS Termination / Browser POST

- User RP-initiated SLO sends a LogoutRequest to the IdP; the IdP then POSTs a signed LogoutResponse back to `https://portal.example.org/logout/saml2/slo`.
- IdP-initiated SLO sends a signed LogoutRequest to the same public callback; the SP validates it and returns a signed LogoutResponse to the IdP.
- Cross-site HTTP-POST binding requires the browser to carry the form/cookies properly; `SameSite=Lax` may **not** send the session cookie on a cross-site POST, causing loss of pending SLO state.
- Test `InResponseTo`/LogoutRequestRepository; do not skip correlation when the session cookie is missing.
- A 308/301 redirect from HTTP to HTTPS at the callback can cause binding/POST issues; configure the IdP directly with the **HTTPS public SLO URL**.
- Never log raw `SAMLRequest`/`SAMLResponse`, NameID, or signed XML in nginx access logs/APM.

### 8.4. SAML Metadata Behind a Proxy

Inspect the metadata registered by the IdP:

~~~text
Expected EntityDescriptor entityID:
  https://portal.example.org/saml2/service-provider-metadata/corporate

Expected SPSSODescriptor / AssertionConsumerService Location:
  https://portal.example.org/login/saml2/sso/corporate

If SLO supported, SingleLogoutService Location:
  https://portal.example.org/logout/saml2/slo

No internal:
  http://portal-service:8080
  http://127.0.0.1:8080
  http://portal-pod-7.internal
~~~

These Location/EntityID values are examples based on the configured registration; do not assume `/saml2/metadata/...` itself is the `entityID`. Before issuing metadata to a production IdP, verify the exact SAML binding, signed request expectations, certificates, and public URLs according to the profile.

### 8.5. Testing Wrong SAML Callbacks Caused by Forwarded Headers

| Case | Expected |
| --- | --- |
| Spring-generated metadata contains internal host | QA fail; fix trusted forwarding/canonical baseURL |
| AuthnRequest ACS has wrong port/scheme | IdP rejects or browser fails; do not relax IdP trust |
| IdP SAMLResponse Recipient is public but SP expects private | Spring rejects; fix registration |
| SAMLResponse signed by unknown IdP | Rejected regardless of public URL |
| SAML Assertion Audience is a different Entity ID | Rejected; never change audience check to a wildcard |
| Wrong `InResponseTo` | Rejected; do not skip request correlation |
| SAML POST callback lacks cookie due to SameSite | Adjust cookie/session strategy; do not bypass signature |
| IdP-initiated SLO from wrong host/wrong destination | Rejected |
| Multiple registrations on the same public origin | Match the right `registrationId`/issuer; do not use user-supplied Host to select tenant |
| Public URL changes during migration | IdP/SP metadata/cert/ACS/SLO updated per change plan |

## 9. CAS: Service Identifier and PGT Callback Need Exact HTTPS Even More

Central Authentication Service (CAS) typically issues a **Service Ticket (ST)** bound to the `service` used when the browser was sent to CAS login:

~~~text
Browser:
  https://portal.example.org/private

Portal redirect:
  https://cas.example.org/cas/login
    ?service=https%3A%2F%2Fportal.example.org%2Flogin%2Fcas

CAS redirects:
  https://portal.example.org/login/cas?ticket=ST-...

Portal validates:
  https://cas.example.org/cas/serviceValidate
    ?ticket=ST-...
    &service=https%3A%2F%2Fportal.example.org%2Flogin%2Fcas
~~~

If Portal uses public `https://portal.example.org/login/cas` during redirect but internal `http://portal-service:8080/login/cas` when validating the ST, CAS may reject due to **service mismatch**. A CAS ST is one-time and target-bound; you cannot "skip service validation" to fix it.

### 9.1. ServiceProperties Must Be Stable

Spring Security CAS uses `ServiceProperties.service` as the identifier for the CAS service callback. When the application sits behind a proxy, its configuration must **match the public URL registered with the IdP/CAS**; do not depend on a random internal Host.

~~~java
// Spring Security CAS fragment; requires a compatible CAS module.
import org.springframework.security.cas.ServiceProperties;

ServiceProperties service = new ServiceProperties();
service.setService("https://portal.example.org/login/cas");
service.setSendRenew(false);
~~~

The fragment above is **not** a standalone application: it also needs a CAS filter, entry point, authentication provider, ticket validator, CAS Server URLs, and a service registry. Never use `ServiceProperties.service=http://localhost:8080/...` in production.

### 9.2. CAS Proxy PGT Callback Is Another Trust Boundary

If Portal needs to obtain a Proxy-Granting Ticket (PGT) to call Reports on the user's behalf:

~~~text
Portal validates ST at CAS /serviceValidate:
  service=https://portal.example.org/login/cas
  pgtUrl=https://portal.example.org/login/cas/proxyreceptor

CAS Server --HTTPS GET--> Portal PGT callback:
  /login/cas/proxyreceptor?pgtId=...&pgtIou=...

Portal correlates PGTIOU, secures PGT in storage
Portal /proxy(PGT,targetService=Reports)
Reports /proxyValidate(PT,service=Reports)
~~~

**Unlike OAuth2:** The CAS Server actively performs a **server-to-server HTTPS GET** to `pgtUrl` to deliver PGT/PGTIOU. It must reach a public/reachable HTTPS callback, verify the certificate, and satisfy the callback/SP registry policy. If the edge proxy allows only browsers or blocks outbound CAS Server calls, ST login may succeed while PGT acquisition fails. An HTTP→HTTPS redirect directly on the PGT receptor can also break callback validation; configure the exact HTTPS URL directly.

**Do not accept a browser-chosen `pgtUrl` query parameter**: CAS actively connects to that URL, creating SSRF/secret-exfiltration risk if the registry and callback allowlist are wrong. Do not log `pgtId`/`pgtIou` in ingress access logs, APM traces, or exceptions. The backend must verify TLS PKIX/hostname; never use trust-all to "fix the proxy."

### 9.3. CAS Validation and Request URL

The CAS client may use `ServiceAuthenticationDetailsSource`/request URL in certain stateless flows. Verify the service identity behind the proxy at **login redirect emission, ST validation, PT validation, and PGT callback**. Do not assume that proxy properties that fixed OAuth2 automatically fix CAS; the CAS module may have a fixed `service` configuration and distinct behavior.

## 10. Kerberos/SPNEGO: Public Hostname Is the Basis of the HTTP SPN

HTTP Negotiate is unlike redirect-based SAML/OIDC/CAS callbacks. The browser typically requests a Kerberos service ticket for the **public FQDN**:

~~~text
Browser URL:
  https://portal.example.org/private

Kerberos SPN:
  HTTP/portal.example.org@EXAMPLE.ORG

Not:
  HTTP/portal-service:8080@EXAMPLE.ORG
  HTTP/portal-pod-7.internal@EXAMPLE.ORG
  https://portal.example.org/private@EXAMPLE.ORG
~~~

If Nginx **only proxies HTTP headers**, it must forward `WWW-Authenticate: Negotiate` from Spring to the browser and `Authorization: Negotiate ...` from the browser to Spring. The Java acceptor uses a keytab containing the SPN `HTTP/portal.example.org@EXAMPLE.ORG`; having the Spring backend listen on HTTP/8080 does **not** turn the SPN into the Pod hostname.

If Nginx/ingress **performs Kerberos authentication itself**, the backend should not expect raw SPNEGO tokens; instead, design identity propagation with mTLS/trusted headers, strip injected `X-User`, and enforce application authorization. The two models must be clearly distinguished before debugging a 401 loop.

### 10.1. Failures and SPN Checks

| Symptom | Diagnosis |
| --- | --- |
| No `WWW-Authenticate: Negotiate` | Misconfigured entry point/filter chain/ingress challenge |
| Challenge present, browser sends no `Authorization` | Browser integrated auth allowlist, TGT, KDC, VPN, proxy |
| Browser sends token, ingress does not forward it | Proxy strips Authorization |
| KDC reports `KDC_ERR_S_PRINCIPAL_UNKNOWN` | Public SPN unregistered, or wrong DNS/realm |
| `KRB_AP_ERR_MODIFIED` | Java keytab/SPN/key version/enctype mismatches the ticket |
| `GSSException` channel binding mismatch | TLS termination incompatible with Extended Protection/CBT policy |
| Java GSS passes but Spring returns 403 | Business authorization/roles/tenant |

Do not change `HTTP/SPN` to the internal name just to match the JVM's `serverName`. Find the **actual SPN the client requested from the KDC** and compare it with the keytab/AD registration. Differences in CNAMEs, load balancers, or URL aliases can cause the client to request a service ticket for another hostname. TLS termination can affect Kerberos Extended Protection / channel binding; **do not disable EPA** or recklessly enable NTLM fallback.

## 11. URL Path Prefix and Reverse Proxy Rewrites: Harder Than Changing Scheme

Suppose the public URL is `https://portal.example.org/app` while Spring runs at `http://portal-service:8080/`.

There are three design approaches—**pick one**:

**Option A – same internal and public path:** The servlet context path is `/app`, the proxy forwards `/app/...` unchanged; the IdP callback includes `/app/login/oauth2/code/corporate`. Advantage: easy to correlate, though you must check `server.servlet.context-path`, actuator, cookies, and router mappings.

**Option B – proxy strips prefix:** Nginx receives `/app/...` and forwards `/...` to the backend. If Spring generates absolute redirects, it must learn the external prefix via a **trusted `X-Forwarded-Prefix: /app`**/framework strategy or a fixed base URL. Test against your actual Spring/Boot version, because `X-Forwarded-Prefix` is an extension that components may handle differently. Never prepend the prefix in both the proxy and Java.

**Option C – fixed public URLs in federation registrations:** Set Entity ID/ACS, OAuth redirect URI, CAS service, and SLO URLs directly under `https://portal.example.org/app/...`; use a public callback path contract and trusted ingress rewrites. This reduces reliance on request-derived scheme/host, though routing/cookies/CSRF still must be verified.

### 11.1. Prefix Matrix to Avoid Double Paths

| Public URL | Backend URL | App sees externally | Valid? |
| --- | --- | --- | --- |
| `/app/login/oauth2/code/corporate` | `/app/login/oauth2/code/corporate` | `/app/login/oauth2/code/corporate` | Valid if app context path=/app |
| `/app/login/oauth2/code/corporate` | `/login/oauth2/code/corporate` | `/app/login/oauth2/code/corporate` | Valid if trusted prefix is handled once |
| `/app/login/oauth2/code/corporate` | `/login/oauth2/code/corporate` | `/login/oauth2/code/corporate` | Invalid, prefix dropped |
| `/app/login/oauth2/code/corporate` | `/login/oauth2/code/corporate` | `/app/app/login/oauth2/code/corporate` | Invalid, prefix doubled |

**Check both outbound and inbound**: The URL Spring emits to the IdP may be correct while the proxy rewrite on the inbound callback is wrong (404 or filter mismatch). For SAML ACS HTTP POST, a `301/302` from `/app/login/saml2/sso` to `/login/saml2/sso` can drop the body or session cookie. Fix the route rather than relying on a redirect to compensate for a path mismatch.

### 11.2. Changing Context Path Is Not Just Editing YAML

When moving Portal from `https://portal.example.org` to `https://portal.example.org/app`:
- The OAuth IdP redirect_uri allowlist must change.
- SAML ACS/SLO locations and (if the entity ID is URL-based) SP identity must be approved by the IdP.
- CAS serviceId and pgtUrl callback must change.
- Cookie Path and CSRF form actions must be right.
- Load balancer health checks, login success redirects, static assets, and reverse proxy rewrites must change.
- Links/emails/bookmarks may require migration; do not issue a 302 for a signed SAML POST callback as a primary workaround.
- With SPNEGO, the hostname does not change so the HTTP SPN usually stays the same; changing the path does not change the SPN.

## 12. HTTPS: TLS Termination, Backhaul, and Browser Cookies

### 12.1. TLS Termination at the Edge

**TLS terminated at LB/ingress:**

~~~text
Browser ── HTTPS ──> Edge Nginx
                          |
                          | HTTP (private same-host network only)
                          v
                      Spring JVM
~~~

This model can be acceptable under a threat model where backend HTTP stays strictly on loopback/a private isolated network, preventing untrusted tenants from sniffing/injecting, backed by network policies/firewalls. However, **browser HTTPS does not prove the backhaul is encrypted**; if proxy→JVM traverses a shared datacenter network, use TLS/mTLS.

**Full TLS/mTLS:**

~~~text
Browser ── HTTPS ──> Edge
                       |
                       | HTTPS or mTLS
                       v
                    Spring JVM
~~~

Here certificates/trust chains must be managed at both hops. Even with backend HTTPS, Spring still needs the canonical public host/port because the backend may see `https://portal-service.internal:8443` rather than `https://portal.example.org`.

### 12.2. TLS/Redirect Security Checklist

- Valid public cert (CN/SAN matches FQDN), correct chain/trust store, automated renewal, and expiry alerts.
- TLS versions/ciphers per policy (typically TLS 1.2+/1.3); never disable hostname verification in IdP/CAS callbacks.
- HTTP port 80 redirects only to the **canonical HTTPS host**; an unknown Host must never be used in `Location`.
- Enable HSTS on the hostname once ready. Do not turn on preload/includeSubDomains arbitrarily.
- Proxy→backend TLS/mTLS if the network is insufficiently isolated; ingress/controller certificate rotation/identity is governed.
- Prevent clients from accessing the backend directly to bypass TLS, header scrubbing, WAF, rate limits, or auth.
- Never expose the TLS private key in app logs/config repos; SAML signing keys and CAS keytabs are separate secrets.
- Never cache login callbacks/SAML responses, `code`, `state`, or `SAMLResponse` at the reverse proxy.
- Specify port/canonical URL consistently in metadata and redirects; `:443` vs no-port must agree.

### 12.3. Browser Session Cookie Secure, HttpOnly, SameSite

| Attribute | Recommendation | Why |
| --- | --- | --- |
| `Secure` | **true** on public HTTPS | Prevents sending session cookie over HTTP |
| `HttpOnly` | **true** | JavaScript cannot read the session cookie directly |
| `SameSite=Lax` | Usually suitable for many OAuth2 redirect GETs | Cross-site top-level GET can send the cookie |
| `SameSite=None; Secure` | May be needed for SAML HTTP-POST from IdP | Cross-site POST usually does not send Lax/Strict session cookies |
| `Path` | Matches public app prefix | Callback and login pages see the right cookie |
| `Domain` | Prefer host-only unless shared subdomains are needed | Limits cookie scope |
| TTL/Session rotation | Per risk policy | Prevents stale/fixation and token misuse |

**SAML HTTP-POST note:** The IdP sends `SAMLResponse` via a browser POST to the ACS. The browser treats this as a cross-site request; if the session cookie is `SameSite=Lax`, the cookie may be omitted, Spring cannot find the pending AuthnRequest/`InResponseTo`, and it returns 401/invalid response. **Do not disable CSRF app-wide** to "solve" it; configure cookies/context appropriately and let the Spring SAML validator check signature/issuer/recipient/audience/timestamp. You may need `SameSite=None; Secure` for the SAML app's session cookie depending on browser/topology while keeping CSRF enabled for non-protocol endpoints.

**OAuth2 Authorization Code:** Callbacks are usually top-level GETs so Lax may work, but verify actual browser `state` repository and cookie behavior. Some deployments use response_mode=form_post or iframes/front-channel; cookie policy must match the actual callback binding, not just the protocol name.

**Session affinity:** Multiple instances may need a shared session store or sticky sessions; if a login request hits Pod A and the callback lands on Pod B while the session/state repository is in-memory only, OAuth `state` or SAML `InResponseTo` can fail. **Do not drop state/correlation** to fix this. Use Spring Session/Redis or a properly designed repository focusing on privacy/TTL/secure serialization and infrastructure.

### 12.4. CSRF with Federation Callbacks

State-changing user POSTs (profile, logout, payment) require CSRF protection. Certain **SAML protocol endpoints** accept POSTs from the IdP without an SP CSRF token; Spring SAML filters rely on signature/trust/destination/replay checks rather than browser form CSRF. Any exemption, if needed, must be **very narrow** (specific endpoint/binding) and never turn into app-wide `csrf.disable()`.

OAuth2 redirect GETs must verify `state` (and OIDC nonce/PKCE as applicable), without treating an allowed redirect URI as sufficient protection. CAS service ticket validation binds exact service and one-time use; Kerberos JGSS validation binds the service principal. Header trust does not replace protocol-specific security checks.

## 13. Standalone Java 17: Validating a Canonical Public Callback Allowlist

This code is **standalone and compiles/runs on JDK 17** to verify policy URIs when writing deployment tests. It **does not generate OAuth/SAML/CAS tokens**, does not validate SAML assertions, and does not read live HTTP requests. Testers supply candidate URLs constructed in unit tests; production apps must derive the canonical origin from trusted configuration and delegate authentication to Spring Security.

**File `PublicCallbackPolicyDemo.java`:**

~~~java
import java.net.URI;
import java.util.Map;

public class PublicCallbackPolicyDemo {

    static final String PUBLIC_HOST = "portal.example.org";

    static final Map<String, String> APPROVED_PATHS = Map.of(
        "OIDC", "/login/oauth2/code/corporate",
        "SAML_ACS", "/login/saml2/sso/corporate",
        "SAML_SLO", "/logout/saml2/slo",
        "CAS_ST", "/login/cas",
        "CAS_PGT", "/login/cas/proxyreceptor"
    );

    static String validate(String flow, String candidate) {
        String expectedPath = APPROVED_PATHS.get(flow);
        if (expectedPath == null) {
            return "DENY_UNKNOWN_FLOW";
        }

        URI uri;
        try {
            uri = URI.create(candidate);
        } catch (IllegalArgumentException e) {
            return "DENY_MALFORMED_URI";
        }

        if (!uri.isAbsolute()
                || uri.getHost() == null
                || uri.getUserInfo() != null
                || uri.getQuery() != null
                || uri.getFragment() != null) {
            return "DENY_URI_SHAPE";
        }

        boolean originIsPublic =
            "https".equalsIgnoreCase(uri.getScheme())
            && PUBLIC_HOST.equalsIgnoreCase(uri.getHost())
            && (uri.getPort() == -1 || uri.getPort() == 443);

        if (!originIsPublic) {
            return "DENY_ORIGIN";
        }
        if (!expectedPath.equals(uri.getRawPath())) {
            return "DENY_PATH";
        }
        return "ALLOW_PUBLIC_CALLBACK";
    }

    static void check(String label, String flow, String url) {
        System.out.println(label + "=" + validate(flow, url));
    }

    public static void main(String[] args) {
        check("oidcOK", "OIDC",
            "https://portal.example.org/login/oauth2/code/corporate");
        check("samlOK", "SAML_ACS",
            "https://portal.example.org/login/saml2/sso/corporate");
        check("casPgtOK", "CAS_PGT",
            "https://portal.example.org/login/cas/proxyreceptor");
        check("internalHost", "OIDC",
            "http://portal-service:8080/login/oauth2/code/corporate");
        check("insecureScheme", "OIDC",
            "http://portal.example.org/login/oauth2/code/corporate");
        check("attackerHost", "OIDC",
            "https://evil.example.org/login/oauth2/code/corporate");
        check("wrongPort", "OIDC",
            "https://portal.example.org:8443/login/oauth2/code/corporate");
        check("wrongPath", "SAML_SLO",
            "https://portal.example.org/logout/saml2/other");
        check("unexpectedQuery", "CAS_ST",
            "https://portal.example.org/login/cas?next=evil");
        check("userinfo", "OIDC",
            "https://user@portal.example.org/login/oauth2/code/corporate");
        check("unknownFlow", "NTLM",
            "https://portal.example.org/login/cas");
        check("malformed", "OIDC", "bad url with spaces");
    }
}
~~~

**Run:**

~~~bash
javac PublicCallbackPolicyDemo.java
java PublicCallbackPolicyDemo
~~~

**Exact stdout:**

~~~text
oidcOK=ALLOW_PUBLIC_CALLBACK
samlOK=ALLOW_PUBLIC_CALLBACK
casPgtOK=ALLOW_PUBLIC_CALLBACK
internalHost=DENY_ORIGIN
insecureScheme=DENY_ORIGIN
attackerHost=DENY_ORIGIN
wrongPort=DENY_ORIGIN
wrongPath=DENY_PATH
unexpectedQuery=DENY_URI_SHAPE
userinfo=DENY_URI_SHAPE
unknownFlow=DENY_UNKNOWN_FLOW
malformed=DENY_MALFORMED_URI
~~~

**Case breakdown:**

1. OIDC, SAML ACS, and CAS PGT callbacks with valid origin/path are allowed.
2. Internal hostname, HTTP scheme, attacker hostname, or unapproved port 8443 → `DENY_ORIGIN`.
3. SAML SLO wrong path → `DENY_PATH`.
4. Candidates with unexpected query or user-info → `DENY_URI_SHAPE`; a registered redirect_uri/service identifier must not arbitrarily carry business data queries.
5. Unknown flows and malformed URIs are rejected.
6. The code uses `getRawPath()` to avoid implicitly treating a differently percent-encoded path as equivalent; production also requires canonical URL parsing/IDNA/IPv6, normalization, and policy covering approved prefixes/ports.

**Important limitation:** The HTTP `redirect_uri` URI from an IdP **can receive `?code=...&state=...` on actual browser callbacks**. The demo validates the **registered/base callback URL** before response parameters are appended, so rejecting unexpected queries is right for this policy. Do not use the demo to reject real OAuth GET callbacks carrying `code`/`state`. For SAML HTTP-POST, response data is in the form body. Never invoke `validate` with untrusted headers and use the result to grant user authentication; that belongs to protocol validators.

### 13.1. Upgrading the Demo into an Integration Assertion

From Spring MockMvc/IdP sandbox, capture the **generated callback URL** rather than replacing the request auth result with a mock boolean. Compare against the canonical allowlist:
- OAuth2: parse `redirect_uri` in the outbound Authorization Request at the test IdP and compare against the exact registered URI.
- SAML2: read the actual generated SP metadata/`AuthnRequest.AssertionConsumerServiceURL` and verify the public ACS/entity ID.
- CAS: compare `service` in the login redirect and ST validation, plus the approved PGT callback.
- SPNEGO: compare the SPN in actual client KDC ticket metadata with the keytab; this cannot be verified solely by a callback policy.
- Browser: the IdP returns to the callback, and session/correlation/security validation succeeds.
- Attack test: forged `Forwarded`/`X-Forwarded-Host` still does not change the generated URL.

## 14. Verification Commands Without Leaking Secrets

### 14.1. Checking Only HTTP Headers / Public Scheme

In a staging/canonical test domain:

~~~bash
# Do not use -k to bypass TLS peer verification.
# Do not use -v/--trace with real SAMLResponse/code/cookies.
curl -sSI https://portal.example.org/

# Observe the Location header when accessing a protected URL.
curl -sS -D /dev/stderr -o /dev/null \
  --max-redirs 0 https://portal.example.org/private
~~~

**Note:** `curl --head` sends HEAD, and some routes behave differently from GET; test GET when endpoints/matchers differ. `-D` prints response headers, so avoid it when responses include `Set-Cookie` or `Location` containing real sensitive codes/states if the terminal/logs are unprotected. In a sandbox, redact cookies, authorization codes, `SAMLRequest`/`SAMLResponse`, and `RelayState` before saving output.

### 14.2. Testing External Host Header Spoofing

Only in a lab under your administrative authority, run:

~~~bash
# Request intentionally carrying an unknown Host; expect the edge to reject it.
curl --resolve portal.example.org:443:192.0.2.15 \
  -H 'Host: evil.example' \
  --max-redirs 0 \
  -sSI https://portal.example.org/
~~~

`192.0.2.15` is an RFC 5737 documentation address, **not a real service IP**, so it is only illustrative; replace it with your authorized staging IP. **Expected:** default/catch-all vhost rejection or route isolation; no `Location`/metadata containing `evil.example`. Never test against unauthorized infrastructure.

Another test sends forged headers from the Internet:

~~~bash
curl --resolve portal.example.org:443:192.0.2.15 \
  -H 'X-Forwarded-Host: evil.example' \
  -H 'X-Forwarded-Proto: http' \
  -H 'Forwarded: for=192.0.2.9;proto=http;host=evil.example' \
  --max-redirs 0 \
  -sSI https://portal.example.org/
~~~

**Expected:** the edge scrubs them and Spring still emits URLs in canonical `https://portal.example.org`. Tests must combine **capturing outbound OAuth2/SAML/CAS URLs** to prove it rather than asserting 200 alone. If the origin response has no redirect, inspect a protected diagnostic test endpoint or metadata instead of inferring success.

### 14.3. SAML Metadata and OIDC OAuth Request

When `saml2Metadata()` is enabled, verify:
- `EntityDescriptor.entityID` and `AssertionConsumerService.Location` contain no internal IP/hostname.
- `SingleLogoutService.Location` (if SLO is enabled) is public HTTPS.
- Published certificates match the SP public cert, with no private key exposure.
- Entity ID does not change across pods/restarts.
- The IdP sandbox imports the metadata cleanly and emits matching Assertion Destination/Recipient/Audience.

For OAuth2, capture the **outbound Authorization Request** and verify:
- `redirect_uri` has the canonical public HTTPS URI.
- `state` is emitted and validated on callback, along with PKCE/nonce when used.
- Authorization endpoint/issuer belongs to the approved IdP.
- No callbacks are emitted with an internal IP, attacker Host header, wrong relative path, or port 8080.
- Callback code exchange runs over HTTPS without logging codes/secrets/tokens.

### 14.4. CAS and Kerberos

CAS:
- Observe `service` in the `/login` redirect and `/serviceValidate` → they must **match exactly**.
- CAS callback `/login/cas?ticket=...` uses public HTTPS and a one-time ticket.
- If using proxy CAS, server-to-server `pgtUrl` is reachable over HTTPS with a trusted certificate and is not blocked by ingress.
- Do not print ST/PGT/PGTIOU in logs.

Kerberos:
- Test SPN `HTTP/portal.example.org@EXAMPLE.ORG` using sanitized KDC/client logs.
- `401 WWW-Authenticate: Negotiate`/`Authorization: Negotiate` is forwarded properly by the edge (log presence only).
- SPN is unique and the keytab KVNO/enctype matches the service account.
- TLS channel binding/EPA policy is compatible with termination; never disable security to cure a 401.

## 15. Positive/Negative Test Matrix

| ID | Condition | Expected |
| --- | --- | --- |
| P01 | Public HTTPS request via trusted edge | Spring sees scheme=https, host=portal.example.org, port=443 |
| P02 | HTTP port 80 | Redirects to canonical HTTPS host; no host injection |
| P03 | Browser forged X-Forwarded-Host | Edge overwrites, generated URLs unchanged |
| P04 | Browser forged Forwarded RFC7239 | Edge strips, generated URLs unchanged |
| P05 | Unknown Host to public edge | Rejected/isolated, does not serve Portal callbacks |
| P06 | Direct backend request from untrusted client/pod | NetworkPolicy/firewall rejects |
| P07 | Nginx sends conflicting Forwarded/X-Forwarded | Test detects, fix to one canonical source |
| P08 | Both framework and native process headers | Detects duplicate/double rewrite |
| P09 | Nginx upstream internal HTTP | Never emits internal URLs to browser/IdP |
| P10 | Nginx upstream HTTPS/mTLS | Both cert/trust and canonical public URL are correct |
| O01 | OAuth2 authorization request | Exact public HTTPS `redirect_uri` |
| O02 | OAuth2 http redirect URI | IdP rejects, fix forwarded config |
| O03 | OAuth2 wrong registrationId/path | No unauthorized login |
| O04 | OAuth callback wrong state | Rejected, no authenticated session created |
| O05 | Callback on another node loses state | Shared repository/session/affinity, do not drop state |
| O06 | `issuer-uri` wrong provider | Token validation rejects |
| O07 | Forged Host changes OAuth redirect | Security QA FAIL, edge rejects/sanitizes |
| O08 | OAuth after prefix migration | IdP URI allowlist updated to /app |
| S01 | SAML metadata published | EntityID, ACS, SLO public values correct |
| S02 | SAML AuthnRequest | Public ACS, correct SP Issuer, correct IdP Destination |
| S03 | SAML Response valid signature/Recipient/Audience | Login passes per role policy |
| S04 | SAML Response internal/private Recipient | Rejected, fix registration |
| S05 | SAML wrong Audience/Entity ID | Rejected, no wildcard |
| S06 | IdP-initiated SAML POST to ACS | Selects correct registration/trusted issuer |
| S07 | SAML HTTP-POST SameSite=Lax loses session | Detects correlation failure; cookie policy fix |
| S08 | SAML LogoutResponse callback after RP SLO | Verifies signature/InResponseTo, no bypass |
| S09 | SAML callback redirected http→https | Test fails and fixes IdP public HTTPS URL directly |
| S10 | SP metadata contains Pod hostname | QA FAIL |
| C01 | CAS login redirect service | Exact public `https://portal.example.org/login/cas` |
| C02 | CAS /serviceValidate service | Matches service used at login; otherwise rejected |
| C03 | CAS pgtUrl callback | Public HTTPS, certificate trust, registered URL |
| C04 | CAS PGT receptor exposed to untrusted client | Rejects unauthenticated/malformed callback; no secret leak |
| C05 | CAS PT targetService after proxy | Target-bound and exact validation at B |
| K01 | Kerberos browser ticket SPN | `HTTP/portal.example.org`, not Pod hostname |
| K02 | Ingress strips Authorization Negotiate | Fail closed; repair header forwarding |
| K03 | Browser uses alias/CNAME | SPN mapping/keytab matches actual host |
| K04 | TLS channel binding mismatch | Diagnose EPA/CBT, no blanket disable |
| T01 | Session cookie Secure/HttpOnly | Browser sends only over HTTPS, not JavaScript-readable |
| T02 | SAML POST SameSite=None; Secure when necessary | Callback retains required session state |
| T03 | OAuth top-level GET with Lax | State correlation works in real browser |
| T04 | Pod A emits auth request, Pod B gets callback | Shared state or safe failure |
| T05 | Context path /app dropped or doubled | Detected via callback/metadata, fixed once |
| T06 | HTTP Host with unexpected :8080 or :8443 | No unapproved callback URL |
| T07 | SAML/CAS/OAuth logs contain secrets | QA FAIL, redact/rotate/incident |
| T08 | Expired TLS certificate at ingress | TLS fails, alert/renew; no trust-all fallback |

### 15.1. Separating Root Causes Properly

- **OAuth2 redirect_uri_mismatch**: first check the generated URL, IdP URI allowlist, edge trusted forwarding, and path/port; no need to reset client secret yet.
- **OAuth2 invalid_state**: callback path/host/cookie SameSite/session repository/node; never drop `state`.
- **SAML Destination/Recipient mismatch**: public SP callback, metadata, and reverse proxy; never disable signature/Recipient/Audience validation.
- **SAML bad signature**: check signer/key/trust separately; do not immediately blame Host.
- **CAS INVALID_SERVICE**: compare exact `service` strings at login/validation, Port/Prefix/Encoding; do not randomly issue new STs.
- **CAS proxy PGT callback fail**: check HTTPS/cert/reachability/callback policy; never pass PGT through the browser.
- **SPNEGO 401**: 401 challenge/client token/KDC SPN/keytab/CBT; public hostname affects SPN, whereas OIDC callback logic does not apply.
- **HTTP 403 after successful login**: business authorization/roles/tenant; do not modify reverse proxy or IdP URIs.
- **HTTP↔HTTPS redirect loop**: double SSL redirect, proxy not passing proto properly, or app not trusting edge, possibly combined with non-Secure session cookies.
- **Only one Pod failing**: config/secret version/session/cookie drift; do not immediately change the IdP system-wide.

## 16. Troubleshooting by Symptom

| Symptom | Likely Cause | What to Verify |
| --- | --- | --- |
| Browser sees `Location: http://portal-service:8080` | Spring does not receive public host/proto | Proxy-set headers and forward strategy |
| IdP reports `redirect_uri_mismatch` | URL has wrong scheme/host/port/path | Outbound `redirect_uri` vs registry |
| OAuth callback hits right URL but invalid_state | Session cookie/multi-node state lost | Cookie SameSite/Path, shared session store |
| IdP only has http callback | IdP registry not updated | Use canonical HTTPS callback |
| SAML metadata has internal IP | `{baseUrl}` resolved wrongly | EntityID/ACS/SLO config and proxy headers |
| SAML Response Recipient mismatch | SP expected/private vs IdP public ACS | SAML registration/metadata |
| SAML Response Audience mismatch | Entity ID differs from metadata | Stabilize SP identity, do not bypass |
| SAML SLO POST fails from IdP | Cookie SameSite/CSRF/HTTPS callback | Right protocol listener, SAML validation |
| CAS ST `INVALID_SERVICE` | `service` differs on the two sides | Compare exact strings, URL encoding |
| CAS PGT not issued | pgtUrl HTTPS/TLS/callback unreachable | IdP/CAS Server callback logs and trust |
| SPNEGO KDC_ERR_S_PRINCIPAL_UNKNOWN | Kerberos SPN unregistered | Public FQDN/AD registry |
| SPNEGO KRB_AP_ERR_MODIFIED | Keytab does not match ticket | SPN owner/KVNO/enctype |
| Nginx forwards request to backend but Spring 404 | Wrong prefix strip/rewrite | Proxy path vs servlet context path |
| Browser 401/302 loop after HTTPS | Wrong session cookie/redirect scheme | Secure/SameSite/Forwarded headers |
| One Pod passes, another fails | Config/secret/session mismatch | Node/pod-level diagnostics |
| Unknown Host reflected in Location | Host header injection/open redirect | Catch-all host rejection and canonical config |
| Open redirect after login via `returnUrl` | Arbitrary user input | Return URL allowlist / relative paths only |
| Signed SAML callback returns 400 after proxy deploy | Binding/Destination/CSRF/proxy path | Compare metadata and actual callbacks |
| 308 from callback before Spring | IdP sends HTTP instead of HTTPS | Fix IdP registry, no redirect workaround |
| Proxy `X-Forwarded-For` client IP wrong | Multi-hop IP chain trust config | Known proxies/real_ip policy |

**Diagnostic order:** ① Public URL scheme/host/path → ② edge host allowlist/header scrubbing → ③ JVM request scheme/port/context path → ④ IdP registered callback/metadata → ⑤ browser cookie/state → ⑥ protocol cryptographic validation → ⑦ authorization. Do not skip earlier protection layers just to test a later step.

## 17. Safe Production Deployment Procedure

### 17.1. Before Deployment

1. **Lock the canonical origin** for each environment (prod/staging/dev) and each tenant/registration.
2. **Enumerate every callback** OAuth2/OIDC, SAML ACS/SLO, CAS service/PGT; Kerberos SPN; mark who owns each config (Platform, IAM, App, Security).
3. **Update IdP/CAS/SP metadata** in sandbox and prepare public cert/key trust per process; do not delete old registrations before cutover while legitimate traffic remains.
4. **Design edge trust:** host allowlist, forwarded header overwrite, private backend ingress, TLS and optional mTLS.
5. **Choose one Spring forwarding mode** (framework/native/none), with integration tests covering generated URLs.
6. **Verify prefixes**: public path, proxy rewrite, servlet context, asset paths, and cookie Path.
7. **Verify cookies** per actual SAML POST vs OAuth GET, CSRF, and session affinity/shared state.
8. **Prepare rollback runbook:** IdP allowlists/metadata, DNS, proxy config, key rollout, session expiry, and redirect behaviors.
9. **Enable safe observability:** log aliases, outcomes, request IDs (hashed/redacted), error types—never log bearer params.
10. **Test flows directly** from browser/IdP sandbox; do not treat unit tests as sufficient.

### 17.2. During Rollout

- Canary a group of Pods/traffic and verify generated public redirects/metadata are accurate.
- Monitor 401/403, OAuth2 `redirect_uri_mismatch`/`invalid_state`, SAML Destination/Recipient/correlation errors, CAS `INVALID_SERVICE`/PGT failures, and Negotiate failures.
- Track redirects by host/port/path, not just HTTP status totals.
- Test cross-site signed SAML POST in a real browser; verify session cookie attachment without logging raw cookies.
- Test Host/X-Forwarded spoofing from sandbox, confirming the edge does not reflect untrusted values.
- Test callbacks across different nodes; if state is lost, fail closed and halt the rollout.
- Do not let canary and prod share two Entity IDs on one registration unless the IdP supports that migration.
- Test external clients through CDN/LB and direct internal backend access (direct must be blocked or ignore malicious headers).

### 17.3. After Rollout

- Metadata/IdP registry and actual URLs stay consistent; run periodic tests to detect config drift.
- Monitor TLS certificate expiry, HSTS behavior, and redirect loops.
- Manage key rotation/SAML signing certs, CAS PGT trust, and Kerberos keytabs independently per policy.
- Audit session store/cookie attributes/cluster settings as Pod count scales.
- Sanitize proxy request logs; ensure no `code`/`state`/`SAMLRequest`/`ticket=ST-...`/`pgtId` appears.
- Provide a support page clarifying local vs federated logout scope; do not promise logout on every device without session revocation.
- Remove debug endpoints, extra open actuators, or temporary header dumps after investigation.

## 18. Practice Exercises

**Exercise A – draw trust boundaries.** Given a public HTTPS browser, Nginx, and Spring HTTP/8080, draw the two URLs, annotate where TLS terminates, who writes Forwarded headers, and where direct backend access is blocked. Why are forwarded headers sent by an Internet client untrustworthy?

**Exercise B – OIDC redirect URI.** Spring sends `redirect_uri=http://portal-service:8080/login/oauth2/code/corporate`. Identify the 3 configuration layers to inspect (edge, Spring, IdP). Write the expected URI and explain how to test without leaking the authorization code.

**Exercise C – SAML metadata.** The IdP registered ACS `https://portal.example.org/login/saml2/sso/corporate`, while the SP computes `http://portal-service:8080/...`. Name which validators may fail, and fix the root cause without disabling signature/recipient/audience checks.

**Exercise D – Host spoof.** A browser sends `Forwarded: proto=http;host=evil.example` and `X-Forwarded-Host: evil.example`. Propose edge configuration and negative tests so the callback remains `https://portal.example.org`.

**Exercise E – CAS.** CAS login redirects with `service=https://portal.example.org/login/cas` while validation uses `service=http://portal-service:8080/login/cas`. Predict the outcome, propose `ServiceProperties.service`, and design an HTTPS PGT callback test.

**Exercise F – Kerberos.** Public URL `https://portal.example.org`, Nginx proxies to `portal-pod.internal`. Which SPN does the client request? Why is `HTTP/portal-pod.internal` in the keytab usually wrong? Check `WWW-Authenticate`/`Authorization` header forwarding.

**Exercise G – Java 17.** Run `PublicCallbackPolicyDemo.java` and verify all 12 stdout lines. Add trailing-slash and encoded-path tests to observe expected allowlist behavior; state the limits of a URI-only demo.

**Exercise H – SameSite.** A SAML POST callback omits JSESSIONID while an OAuth GET callback works normally. Explain SameSite Lax/None; propose Secure/CSRF cookie tests without disabling SAML signatures or OAuth `state`.

**Exercise I – prefix.** The app is published at `/app`, and ingress strips the prefix before forwarding. Provide public/backend URL examples and design a setup with no double-prefixing when Spring generates metadata, callbacks, and cookie Path.

**Exercise J – multi-node.** An OAuth authorization request lands on Pod A, and the IdP callback hits Pod B, returning `invalid_state`. Design a shared session/repository and tests without dropping state.

**Exercise K – TLS termination.** Client→Nginx HTTPS, Nginx→Pod HTTP over a shared cluster. Analyze the threat model and conditions requiring mTLS, HSTS, certificate renewal, and network policy.

**Exercise L – runbook.** Write a 10-step migration checklist from `https://portal-old.example.org` to `https://portal.example.org`, covering IdP registrations/SAML entity identity/CAS service/Kerberos SPN/proxy headers/TLS/cookies/rollback.

**Pass criteria:** The learner can design a **canonical public scheme + host + port + prefix**, build proxy trust boundaries, configure Spring forwarding cleanly once, reconcile OAuth redirect URI/SAML ACS+SLO+EntityID/CAS service+PGT/Kerberos SPN, complete E2E HTTPS/browser/IdP tests, and defend against Host-header injection.

## 19. Official References

- Spring Framework – ForwardedHeaderFilter and security considerations: https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html
- Spring Boot 3.5 – Running Behind a Front-end Proxy Server (`server.forward-headers-strategy`): https://docs.spring.io/spring-boot/3.5/reference/how-to/webserver.html
- Spring Security – OAuth2 Login Core Configuration, default `{baseUrl}/login/oauth2/code/{registrationId}`: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/login/core.html
- Spring Security – OAuth2 Login Advanced Configuration / Redirection Endpoint: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/login/advanced.html
- Spring Security – OAuth2 Client Authorization Grants, URI template variables: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/client/authorization-grants.html
- Spring Security – SAML2 Login Overview, default EntityID/ACS, metadata: https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/login/overview.html
- Spring Security – SAML2 Metadata: https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/metadata.html
- Spring Security – SAML2 Single Logout: https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/logout.html
- Spring Security – CAS Authentication: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/cas.html
- Spring Security Kerberos – SPNEGO integration: https://docs.spring.io/spring-security-kerberos/reference/ssk.html
- RFC 7239 – Forwarded HTTP Extension: https://www.rfc-editor.org/rfc/rfc7239
- RFC 6749 – OAuth2 Authorization Framework, redirect_uri: https://www.rfc-editor.org/rfc/rfc6749
- RFC 9700 – OAuth 2.0 Security Best Current Practice: https://www.rfc-editor.org/rfc/rfc9700
- OASIS SAML 2.0 Core, Bindings, Metadata: https://docs.oasis-open.org/security/saml/v2.0/
- OWASP – Unvalidated Redirects and Forwards Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.html
- OWASP – HTTP Security Response Headers Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html
- OWASP – Session Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
