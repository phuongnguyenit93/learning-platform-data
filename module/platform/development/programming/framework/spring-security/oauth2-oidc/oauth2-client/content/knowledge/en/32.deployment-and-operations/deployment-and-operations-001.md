# 32.1. HTTPS, Public Domains, and Environment-Specific Redirect URIs

## 1. Real-world problem: OIDC Login works locally but fails after deployment

A **Spring Boot + Spring Security OAuth 2.0/OIDC Client** application works normally on a development machine:

~~~text
Browser: http://localhost:8080
Login:   GET /oauth2/authorization/company
Callback: http://localhost:8080/login/oauth2/code/company
~~~

After deploying to production, users access:

~~~text
https://portal.example.com
~~~

but the Spring Boot application is actually running behind a reverse proxy:

~~~text
Internet browser
     |
     | HTTPS :443
     v
Load balancer / Ingress
     |
     | HTTP :8080 (private network)
     v
Spring Boot application
~~~

When users click “Sign in with Company”, the following issues may appear:

- The OpenID Provider (OP) reports <code>redirect_uri_mismatch</code> because the Client generates the callback <code>http://portal-service:8080/login/oauth2/code/company</code> instead of the public HTTPS URL.
- The browser is redirected to <code>http://portal.example.com</code> even though the user started over HTTPS.
- The OP accepted the callback, but Spring Security cannot find the authorization request because the session cookie is not sent.
- Staging and production share the same Client ID/redirect URIs, inadvertently allowing callbacks from one environment to go to another.
- The post-logout URL returns to the wrong hostname or HTTP.
- A proxy trusts <code>X-Forwarded-Host</code> sent by an attacker, causing the application to generate redirects to an untrusted domain.

This is not just a matter of “fixing the URL”. It is the boundary between **HTTPS, public origin, proxy headers, session cookies, the OAuth2 authorization request, and the Redirect URI allowlist permitted by the OP**.

> **Core principle:** Each environment needs a deterministic public URL, an exact redirect URI registered at the OP, proper HTTPS/cookie configuration, and forwarded header handling that trusts only controlled proxies. Do not disable <code>state</code>, issuer validation, or PKCE to work around deployment errors.

## 2. Lesson objectives

After this lesson, you will be able to:

1. Distinguish **internal service URL**, **public base URL**, **OAuth2 redirect URI**, and **OIDC issuer URI**.
2. Explain why HTTPS and public domains directly affect the Authorization Code Flow.
3. Use <code>{baseUrl}/login/oauth2/code/{registrationId}</code> in the proper Spring Security context.
4. Configure separate redirect URIs for local, staging, and production in both the Portal and the OP.
5. Understand TLS termination, reverse proxies, <code>Forwarded</code> and <code>X-Forwarded-*</code>, and their trust boundaries.
6. Configure <code>server.forward-headers-strategy</code> according to infrastructure without opening up Host header injection.
7. Configure <code>Secure</code>, <code>HttpOnly</code>, and <code>SameSite</code> session cookies for browser OIDC Login.
8. Handle reverse proxy path prefixes, multiple instances, multiple providers, and multi-tenant hostnames.
9. Distinguish the callback <code>redirect_uri</code> from OIDC <code>post_logout_redirect_uri</code>.
10. Test the Authorization Code Flow through a public ingress and establish a runbook when encountering <code>redirect_uri_mismatch</code>.

## 3. Four types of URLs that must not be confused

Consider a deployment:

~~~text
Public Portal:
    https://portal.example.com

Internal Portal service:
    http://portal-service.namespace.svc.cluster.local:8080

OIDC issuer / OpenID Provider:
    https://login.example-idp.com/realms/company

OAuth2 Redirect URI (registered at OP):
    https://portal.example.com/login/oauth2/code/company
~~~

| Name | Actor using it | Role | Should it be public to the browser? |
|---|---|---|---|
| **Public base URL** | Browser, OP redirect, reverse proxy | External scheme + hostname + port + context path of the Portal | Yes |
| **Internal service URL** | Proxy/cluster/private network | Spring Boot backend address | Usually no |
| **OIDC issuer URI** | Spring Security OIDC Client | Identifies the OP, used for Discovery and checking the ID Token <code>iss</code> | Must be a valid URL per OP configuration |
| **OAuth2 redirect URI** | OP when issuing authorization response | Browser callback back to the Client | Yes, the OP must allow it exactly |
| **Post-logout redirect URI** | OP after RP-Initiated Logout | Browser returns to the Portal after logout | Yes, registered per OP policy |
| **OAuth2 authorization initiation URI** | Browser calls at Portal | Starts login at <code>/oauth2/authorization/{registrationId}</code> | Yes |

### 3.1. Public origin and base URL

In the browser security model:

~~~text
origin = scheme + host + port
~~~

These two addresses:

~~~text
https://portal.example.com
http://portal.example.com
~~~

**have different origins** because their schemes differ. These two addresses:

~~~text
https://portal.example.com
https://portal.example.com:8443
~~~

**have different origins** because their ports differ.

The public base URL can include a context path beyond the origin:

~~~text
https://portal.example.com/app
~~~

if the reverse proxy actually serves the application under <code>/app</code>.

### 3.2. Redirect URI is not the issuer URI

Incorrect:

~~~yaml
spring:
  security:
    oauth2:
      client:
        provider:
          company:
            issuer-uri: https://portal.example.com
~~~

if the real OP is <code>https://login.example-idp.com/realms/company</code>. The issuer must point to the **OP**, not the Client application.

Conversely, the Redirect URI must point to the **Portal callback**, not the Token Endpoint or the OP's login page.

### 3.3. Registration ID is not Client ID

For example:

~~~yaml
registration:
  company:
    client-id: portal-production
~~~

Where:

~~~text
registrationId = company
client_id      = portal-production
~~~

Spring Security's default callback path uses <code>registrationId</code>:

~~~text
/login/oauth2/code/company
~~~

rather than automatically replacing <code>company</code> with <code>portal-production</code>.

## 4. Authorization Code Flow: where the Redirect URI is used

~~~mermaid
sequenceDiagram
    autonumber
    actor User
    participant B as Browser
    participant Proxy as Public HTTPS Ingress
    participant RP as Spring Security Portal
    participant OP as OpenID Provider

    User->>B: Access https://portal.example.com
    B->>Proxy: GET /oauth2/authorization/company over HTTPS
    Proxy->>RP: Internal forward over HTTP + trusted public-origin metadata
    RP->>RP: Create OAuth2AuthorizationRequest, state/PKCE/nonce
    RP-->>Proxy: 302 OP /authorize with redirect_uri=https://portal.example.com/login/oauth2/code/company
    Proxy-->>B: Redirect to OP
    B->>OP: Authorization request, client_id, redirect_uri, state
    OP->>OP: Validate Client registration and Redirect URI
    OP-->>B: 302 to HTTPS callback with code + state
    B->>Proxy: GET /login/oauth2/code/company?code=...&state=... (HTTPS)
    Proxy->>RP: Callback + session cookie
    RP->>RP: Validate state and saved authorization request
    RP->>OP: Server-to-server Token Request, code + client authentication/PKCE
    OP-->>RP: Tokens
    RP->>RP: Validate ID Token and establish Authentication
    RP-->>B: Redirect to protected page /home
~~~

An authorization initiation request to the OP may contain:

~~~text
response_type=code
client_id=portal-production
scope=openid profile
redirect_uri=https%3A%2F%2Fportal.example.com%2Flogin%2Foauth2%2Fcode%2Fcompany
state=<random-value>
code_challenge=<derived-from-verifier>
code_challenge_method=S256
~~~

<code>state</code>, nonce, and PKCE data are security data for a single authorization transaction; they must not be hardcoded per environment or written to logs in raw form.

## 5. HTTPS is a design requirement, not just a padlock icon

### 5.1. Why does the Authorization Code Flow require HTTPS?

When the browser is redirected from the OP back to the Client:

~~~text
https://portal.example.com/login/oauth2/code/company?code=...&state=...
~~~

the authorization code is a short-lived credential, and state binds the flow to the browser session. HTTPS protects the browser ↔ Portal channel against eavesdropping and tampering on the network.

HTTPS is also critical for:

- Session cookies.
- Redirect responses.
- CSRF protection of the browser session.
- Account linking, consent, or reauthentication confirmation pages.
- API endpoints served by the BFF/Web app.

Do not place authorization codes, client secrets, or tokens in public HTTP URLs.

### 5.2. TLS can terminate at the proxy

There are two models:

~~~text
A. End-to-end TLS:
Browser --HTTPS--> Ingress --HTTPS/mTLS--> Spring Boot

B. TLS termination:
Browser --HTTPS--> Ingress --HTTP on trusted private network--> Spring Boot
~~~

Model B can be acceptable depending on network architecture and trust policy; however:

- The proxy must accurately set the public scheme/host/port.
- The ingress → app channel must reside within a protected trust boundary.
- Do not expose the HTTP backend directly to the Internet.
- Consider internal TLS/mTLS when required by compliance, zero-trust, or a multi-tenant cluster.
- The browser must still receive HTTPS redirects, never internal URLs or HTTP downgrades returned by the app.

### 5.3. TLS certificate and hostname

The public ingress certificate must be valid for the domain the browser uses:

~~~text
portal.example.com
~~~

Verify:

1. Trusted certificate chain.
2. Subject Alternative Name (SAN) contains the exact hostname.
3. Certificate is not expired.
4. TLS protocols/ciphers comply with policy.
5. Automated renewal is monitored.

Similarly, the Portal's JVM must **trust the TLS certificate of the OP Token/Discovery/JWKS endpoints**. Do not use a <code>trust-all</code> HTTP client just because a certificate in staging is invalid.

### 5.4. HSTS

HSTS instructs the browser to use only HTTPS for a host that has learned the policy:

~~~http
Strict-Transport-Security: max-age=31536000; includeSubDomains
~~~

However, <code>includeSubDomains</code> should only be enabled when **every subdomain within scope is ready for HTTPS**. <code>preload</code> has strict operational requirements; do not enable it just to feel “safer” before inventorying all domains.

In Spring Security, HSTS may be enabled by default for HTTPS requests depending on configuration. Do not rely on the app's behavior when TLS terminates at the proxy while Spring Boot still perceives the request as HTTP; configure proper scheme detection and inspect the actual response from the public ingress.

## 6. Redirect URI matching: exact down to scheme, host, port, and path

For the OAuth2 Authorization Code Flow, the OP must verify the Redirect URI against registration and security profile requirements. For fully registered redirect URIs, modern security standards favor **exact string matching** with specific exceptions, such as dynamic ports for native app loopback redirects.

Given OP registration:

~~~text
https://portal.example.com/login/oauth2/code/company
~~~

The following URLs **must not be arbitrarily treated as equivalent**:

| Sent Redirect URI | Difference | Should OP accept? |
|---|---|---|
| <code>https://portal.example.com/login/oauth2/code/company</code> | Matches registration | Yes |
| <code>http://portal.example.com/login/oauth2/code/company</code> | Wrong scheme | No |
| <code>https://portal.internal/login/oauth2/code/company</code> | Wrong host | No |
| <code>https://portal.example.com:8443/login/oauth2/code/company</code> | Wrong port | No unless registered |
| <code>https://portal.example.com/app/login/oauth2/code/company</code> | Added path prefix | No unless registered |
| <code>https://portal.example.com/login/oauth2/code/partner</code> | Wrong registration callback | No unless registered |
| <code>https://staging.portal.example.com/login/oauth2/code/company</code> | Different environment | No unless registered |
| <code>https://portal.example.com/login/oauth2/code/company/</code> | Trailing slash | No if registration string differs |

### 6.1. Do not use wildcards to work around redirect_uri_mismatch

Overly broad configurations like:

~~~text
https://*.example.com/*
~~~

or:

~~~text
https://portal.example.com/*
~~~

can open pathways to divert authorization codes to attacker-controlled hosts/paths, especially when subdomain takeover, open redirects, or mutable target routes exist. Avoid wildcards whenever **exact redirect URIs** per environment can be used.

### 6.2. Fragments are not where authorization codes are received

Do not declare:

~~~text
https://portal.example.com/login/oauth2/code/company#callback
~~~

as a Redirect URI for the Authorization Code Flow. URI fragments have browser-specific semantics and are not sent to the server like an HTTP request's path/query; OAuth2 Redirect URI registrations must not contain fragments per protocol rules.

### 6.3. Query parameters in a registered redirect URI

Some providers allow fixed query parameters in a Redirect URI according to their own rules and policies. However, do not use query parameters containing tokens, session IDs, or browser-controlled tenant data to make the callback “dynamic”.

Business information used to restore navigation after login can be stored server-side alongside the authorization transaction or SavedRequest; <code>state</code> must continue to have integrity and CSRF protection.

## 7. How does Spring Security build the Redirect URI by default?

In Spring Boot OAuth2 Client:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: portal-production
            client-secret: ${COMPANY_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            client-authentication-method: client_secret_basic
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
        provider:
          company:
            issuer-uri: https://login.example-idp.com/realms/company
~~~

For a request with public origin:

~~~text
https://portal.example.com
~~~

and <code>registrationId=company</code>, the template produces:

~~~text
https://portal.example.com/login/oauth2/code/company
~~~

### 7.1. Important placeholders

Spring Security supports redirect URI template variables such as:

~~~text
{baseScheme}
{baseHost}
{basePort}
{basePath}
{baseUrl}
{registrationId}
~~~

<code>{baseUrl}</code> reflects the portion of the request URL that the framework considers the external base URL, after applying appropriate forwarded header handling. It does not automatically know the production domain if the request comes through a proxy with missing or incorrect forwarding metadata.

### 7.2. Default callback endpoint

Servlet OAuth2 Login by default receives callbacks in the form:

~~~text
GET /login/oauth2/code/{registrationId}
~~~

and initiation at:

~~~text
GET /oauth2/authorization/{registrationId}
~~~

If you customize the base URI of <code>OAuth2LoginAuthenticationFilter</code> or the authorization request resolver, you must keep in sync:

1. <code>ClientRegistration.redirectUri</code>.
2. The OP redirect URI allowlist.
3. The callback processing matcher/filter.
4. Reverse proxy path mapping.
5. Tests for all environments.

Do not simply change the YAML Redirect URI to <code>/auth/callback</code> while leaving the Spring Security callback filter at <code>/login/oauth2/code/*</code>.

### 7.3. Why does {baseUrl} become wrong?

If the app sees the request as:

~~~text
scheme=http
host=portal-service
port=8080
~~~

then <code>{baseUrl}</code> may become:

~~~text
http://portal-service:8080
~~~

even though the browser is on <code>https://portal.example.com</code>. You must fix **trusted forwarded headers/public base URL** or decide on an environment-specific fixed callback configuration — do not loosen wildcards at the OP.

## 8. Separate configurations for local, staging, and production

A practical matrix:

| Property | Local | Staging | Production |
|---|---|---|---|
| Public Portal | <code>http://localhost:8080</code> | <code>https://portal.staging.example.com</code> | <code>https://portal.example.com</code> |
| Issuer | <code>http://localhost:18081/realms/it</code> | <code>https://sso.staging.example.com/realms/company</code> | <code>https://sso.example.com/realms/company</code> |
| Client ID | <code>portal-local</code> | <code>portal-staging</code> | <code>portal-production</code> |
| Client secret | Test-only | Staging secret store | Production secret store |
| Redirect URI | <code>http://localhost:8080/login/oauth2/code/company</code> | <code>https://portal.staging.example.com/login/oauth2/code/company</code> | <code>https://portal.example.com/login/oauth2/code/company</code> |
| Session cookie Secure | Depends on local HTTP | <code>true</code> | <code>true</code> |
| TLS cert | Local exception | Staging TLS cert | Production TLS cert |
| User data | Mock/test | Test/staging account | Production identities |

### 8.1. Why should ClientRegistration be separated at the OP?

Sharing a Client ID/secret between staging and production can cause:

- A large, hard-to-control cross-environment redirect allowlist.
- Staging tests or errors affecting production grants.
- Staging secret rotation causing a production outage.
- Mixed identity/consent/refresh token policies.
- Difficulty auditing which callback belongs to which environment.

**Recommendation:** Separate client registrations and secrets at least between staging and production. For providers that support separate realms/tenants, issuers, users, and policies can also be separated.

### 8.2. Do not share production credentials in local tests

Local environments should use an OP container/sandbox, Client ID, and test accounts. Do not copy production <code>client_secret</code>, refresh tokens, or private keys onto a developer laptop just to reproduce a login.

### 8.3. Environment-specific Redirect URIs

When a user initiates login from staging:

~~~text
authorization request:
  client_id=portal-staging
  redirect_uri=https://portal.staging.example.com/login/oauth2/code/company
~~~

When from production:

~~~text
authorization request:
  client_id=portal-production
  redirect_uri=https://portal.example.com/login/oauth2/code/company
~~~

The corresponding OP registration must allow the exact URL. Do not rely on conventions like “the OP guesses staging from the hostname”.

## 9. Spring Boot profiles and environment variables

### 9.1. A configuration template using environment variables

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            client-authentication-method: client_secret_basic
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          company:
            issuer-uri: ${OIDC_ISSUER_URI}

server:
  forward-headers-strategy: framework
  servlet:
    session:
      cookie:
        http-only: true
        secure: true
        same-site: lax
~~~

Explanation:

- <code>OIDC_CLIENT_ID</code>, <code>OIDC_CLIENT_SECRET</code>, and <code>OIDC_ISSUER_URI</code> are injected per environment.
- <code>redirect-uri</code> uses the request's public base URL, after handling headers within the proper trust boundary.
- <code>server.forward-headers-strategy=framework</code> is **one option** for controlled proxy infrastructure, not a setting to blindly enable on every application.
- Session cookie <code>Secure=true</code> makes sense for HTTPS staging/production. For plain local HTTP, use a separate profile or local HTTPS testing.
- <code>same-site=lax</code> is generally compatible with top-level GET callbacks; <code>response_mode=form_post</code> requires separate evaluation.

**Do not put production client secrets into <code>application.yml</code> stored in Git.** Use the environment's secret store and restrict read permissions.

### 9.2. application-local.yml

For HTTP localhost:

~~~yaml
server:
  port: 8080
  forward-headers-strategy: none
  servlet:
    session:
      cookie:
        secure: false
        http-only: true
        same-site: lax

spring:
  security:
    oauth2:
      client:
        provider:
          company:
            issuer-uri: http://localhost:18081/realms/it
        registration:
          company:
            client-id: portal-local
            client-secret: local-test-only-secret
~~~

Here, these values are used only in an isolated local test OP/realm. **HTTP localhost is a controlled development exception**, not a reason to allow production redirect URIs to use HTTP. Do not ship an active local profile inside a production artifact.

### 9.3. application-staging.yml and application-prod.yml

Both profiles can share a template while differing in <code>OIDC_ISSUER_URI</code>, Client ID, secrets, public hosts, and cookie/TLS policies. Keep secrets in environment variables or a secret manager rather than copying them directly into profile files.

In the deployment pipeline, validate the configuration before serving traffic:

~~~text
activeProfile=prod
publicBaseUrl=https://portal.example.com
oidcRegistrationId=company
issuer=https://sso.example.com/realms/company
redirectUri=https://portal.example.com/login/oauth2/code/company
~~~

Log only non-sensitive values; never log client secrets, authorization codes, state, nonce, or tokens.

## 10. Forwarded headers: the bridge between external HTTPS and internal HTTP

A reverse proxy typically passes metadata:

~~~http
Host: portal.example.com
X-Forwarded-Proto: https
X-Forwarded-Host: portal.example.com
X-Forwarded-Port: 443
X-Forwarded-For: 203.0.113.10
~~~

Or the RFC 7239 header:

~~~http
Forwarded: for=203.0.113.10;proto=https;host=portal.example.com
~~~

<code>203.0.113.10</code> is an example address. These headers describe the request **that the proxy handled**.

### 10.1. Purpose

When the backend directly receives HTTP on port 8080, this proxy metadata lets the framework know the browser accessed it over HTTPS on the public host.

This can affect:

- <code>request.getScheme()</code>.
- <code>request.isSecure()</code>.
- <code>request.getServerName()</code> and port.
- Redirect URLs generated by Spring Security.
- Absolute links, Location headers, and URL building.
- Scheme-based cookie/security behavior.

### 10.2. The trust boundary is critical

If an external Internet client sends:

~~~http
X-Forwarded-Host: attacker.example
X-Forwarded-Proto: https
~~~

and the backend trusts this header, <code>{baseUrl}</code> can be poisoned into:

~~~text
https://attacker.example
~~~

This is a Host header/forwarded header injection risk, which can lead to bad redirects, poisoning, or compromised authorization redirect URI generation.

**Do not trust all X-Forwarded-* headers from arbitrary IPs.**

### 10.3. The proper trust model

A safer architecture:

~~~text
Untrusted browser
    |
    v
Trusted edge proxy:
  - Serves only known hostnames
  - Strips/overwrites client-supplied forwarded headers
  - Sets scheme/host/port from the verified connection
    |
    v
Private application network:
  - Only the edge proxy can connect to the app
  - App uses forwarded metadata sanitized by the proxy
~~~

If there are **multiple proxy hops**, you must explicitly define which proxy sets/appends/strips each header. The header chain must never blindly trust unverified outermost values.

### 10.4. server.forward-headers-strategy

In Spring Boot 3.x, the options are:

| Value | Meaning | Use when |
|---|---|---|
| <code>none</code> | Do not handle forwarded headers automatically via Boot strategy | Backend directly serves public traffic or has other custom handling |
| <code>native</code> | Use the web server/container's native capability | Infrastructure/container supports it and trusted proxies are explicitly configured |
| <code>framework</code> | Use Spring Framework-level support | You want Spring to process forwarded headers in a trusted proxy environment |

For example:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

For Servlet, Spring provides <code>ForwardedHeaderFilter</code> or an equivalent mechanism via Boot auto-configuration; for Reactive, there are corresponding mechanisms suited for WebFlux.

**Do not enable multiple Forwarded processors simultaneously without verification**, because double-processing or misconfigured proxy trust can produce unexpected schemes, hosts, or paths.

### 10.5. native does not mean automatically trusting every client

When using <code>native</code> with Tomcat or another server, you must configure valid proxy trust/IP ranges according to the container/version. Do not simply enable <code>native</code> and assume direct Internet requests cannot spoof forwarded headers.

## 11. NGINX reverse proxy: illustrative configuration

Assume the public host is:

~~~text
portal.example.com
~~~

and Spring Boot runs at:

~~~text
http://127.0.0.1:8080
~~~

A **minimal configuration, solely to illustrate the trust boundary**:

~~~nginx
# In a real configuration, the default server should reject unknown hosts.
server {
    listen 443 ssl;
    server_name portal.example.com;

    ssl_certificate     /etc/nginx/tls/fullchain.pem;
    ssl_certificate_key /etc/nginx/tls/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8080;

        proxy_set_header Host portal.example.com;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Host portal.example.com;
        proxy_set_header X-Forwarded-Port 443;
        proxy_set_header X-Forwarded-For $remote_addr;

        # Do not forward a client-supplied RFC 7239 Forwarded header.
        proxy_set_header Forwarded "";
    }
}
~~~

This is **not a complete production NGINX file**: you still need HTTP-to-HTTPS redirects, default-server rejection, TLS policies, proxy timeouts, limits, and monitoring. In particular, if the proxy sits behind another edge load balancer, values like <code>https</code> and <code>$remote_addr</code> must be derived from real **trusted hops**, not erroneously hardcoded.

### 11.1. Why set a fixed Host in the example?

<code>Host</code> is data the client can send. Using an allowlisted hostname at the edge prevents arbitrary requests hitting this virtual host with an arbitrary Host from being used by the application as the public base.

When serving **multiple hostnames** via a single ingress, explicit virtual host routing/allowlisting is needed; do not copy a fixed-host configuration across all tenants.

### 11.2. Avoid direct public access to the backend

If an attacker can call:

~~~text
http://public-ip:8080/
~~~

and set <code>X-Forwarded-Host</code> themselves, the application may trust the forged metadata. The backend must bind to a private interface, with appropriate firewall/security groups or Kubernetes NetworkPolicy.

### 11.3. The proxy must not modify the authorization code

The proxy only forwards the callback request; it must not:

- Extract the code and exchange it with the OP on behalf of the Spring Security Client unless intentionally architected to do so.
- Write raw callback URLs containing <code>code</code>/<code>state</code> into uncontrolled shared logs.
- Drop callback query parameters.
- Alter <code>state</code> or <code>redirect_uri</code>.

## 12. Kubernetes Ingress and service port

Simple Ingress example:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: portal
  namespace: portal-prod
spec:
  ingressClassName: nginx
  tls:
    - hosts:
        - portal.example.com
      secretName: portal-tls
  rules:
    - host: portal.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: portal-service
                port:
                  number: 8080
~~~

Assumptions:

~~~text
Ingress: TLS :443 for portal.example.com
Service: portal-service:8080
Pod:     Spring Boot :8080
~~~

The Ingress controller must be configured to:

1. Accept only host <code>portal.example.com</code> per rules.
2. Manage the TLS cert for this host.
3. Set the forwarded scheme/host/port properly.
4. Strip/overwrite untrusted inbound forwarded headers.
5. Not expose the application directly to the Internet outside the ingress.

**An Ingress manifest does not guarantee that every controller handles forwarded headers identically.** Coordinate with the platform team to confirm the trusted proxy chain, ingressClass, and appropriate annotations for your controller/version.

### 12.1. X-Forwarded-Prefix and an app under /portal

If externally:

~~~text
https://example.com/portal
~~~

but the backend serves at root:

~~~text
http://portal-service:8080/
~~~

the proxy may strip <code>/portal</code> before forwarding. Depending on the architecture, you may need:

~~~text
X-Forwarded-Prefix: /portal
~~~

with the Spring Boot strategy handling the prefix properly, or configure <code>server.servlet.context-path=/portal</code> if the backend actually serves under that path.

**Do not configure both ways such that the prefix is doubled.**

The correct public callback might be:

~~~text
https://example.com/portal/login/oauth2/code/company
~~~

While the internal callback route remains:

~~~text
/login/oauth2/code/company
~~~

If the app/ingress assembles it wrongly:

~~~text
https://example.com/portal/portal/login/oauth2/code/company
~~~

the OP will reject the redirect URI or the browser callback will hit a 404.

### 12.2. Path rewrites must preserve the query string

Browser authorization responses typically look like:

~~~text
/login/oauth2/code/company?code=C&state=S
~~~

If a rewrite drops the query string, Spring Security cannot find state/code and login will fail. Test both the public request and the backend route, not just the health endpoint.

## 13. Cookies: HTTPS, Secure, HttpOnly, and SameSite

Spring Security OAuth2 Login typically relies on the browser session to store the authorization request and subsequently the SecurityContext.

### 13.1. Baseline configuration for an HTTPS Portal

~~~yaml
server:
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: lax
~~~

Explanation:

- **Secure:** the browser sends the cookie only over HTTPS (localhost exceptions/browser-specific behaviors must be tested, not relied upon as a production assumption).
- **HttpOnly:** JavaScript cannot directly read the cookie; reduces some risks of session exposure via scripts.
- **SameSite=Lax:** usually allows the session cookie on top-level cross-site GET navigations from the OP back to the Portal.

**No cookie attribute replaces OAuth2 <code>state</code>, PKCE, or CSRF protection for business POST requests.**

### 13.2. GET callback and SameSite=Lax

A typical flow:

~~~text
Browser: Portal → OP → top-level GET callback Portal
~~~

A <code>SameSite=Lax</code> cookie is usually sent when the browser returns to the Portal via a top-level GET navigation. As a result, Spring Security can restore the authorization request from the session and compare <code>state</code>.

### 13.3. OIDC response_mode=form_post

With:

~~~text
response_mode=form_post
~~~

the OP may return the authorization response to the Portal via a **cross-site POST**. <code>SameSite=Lax</code> typically does not send the session cookie in this case, leading to:

~~~text
authorization_request_not_found
invalid_state
~~~

You may need <code>SameSite=None; Secure</code> or a different flow/correlation design. However:

- <code>SameSite=None</code> causes the browser to send the cookie in more cross-site contexts.
- CSRF protection for business browser POSTs must remain enabled.
- Your Spring Security version may require custom handling/CSRF matchers for the POST callback.
- Do not assume that merely changing the cookie to None is enough to support <code>form_post</code>.

### 13.4. Domain and Path

Cookies should be scoped narrowly enough:

~~~text
Host: portal.example.com
Path: /
~~~

Do not automatically use:

~~~text
Domain=.example.com
~~~

when subdomains do not share a trust boundary. A compromised sibling subdomain could affect a domain-wide cookie.

If the Portal runs under <code>/portal</code>, check the cookie Path/context/session strategy and callback path. Do not assume a cookie with Path <code>/app</code> will be sent by the browser to a callback outside that path.

### 13.5. Cookie persistence in a cluster

If the HTTP session is stored in-memory on node A, a callback landing on node B may fail to find the authorization request even though the browser sent the right cookie. Spring Session Redis/JDBC or session affinity must be designed per architecture. **Proper HTTPS configuration does not solve distributed state storage**.

## 14. Authorization request, state, and proxy trust

When a user initiates:

~~~text
GET /oauth2/authorization/company
~~~

Spring Security creates an <code>OAuth2AuthorizationRequest</code> and stores it in a repository (usually session-based on Servlet).

An authorization request has properties:

~~~text
authorizationUri
clientId
redirectUri
scopes
state
attributes (nonce, PKCE, registration context when applicable)
~~~

### 14.1. Redirect URI injection is not purely a UI bug

If an attacker forces the backend to build a redirect URI from untrusted Host/forwarded headers:

~~~text
Host: attacker.example
X-Forwarded-Proto: https
~~~

the Client may send an authorization request to the OP with the wrong redirect_uri. Strict URI registration at the OP may block it, but the OP must not be treated as the sole defense. Allowed hosts must be enforced at both the ingress and backend per security policy.

### 14.2. Do not let the user choose an arbitrary redirect URI

Do not build an endpoint like:

~~~text
/oauth2/authorization/company?redirect_uri=https://attacker.example
~~~

and trust this query parameter to override the ClientRegistration's authorized redirect URI. If tenant/environment-specific callbacks are needed, use server-side allowlisted mappings; do not let the browser pick an arbitrary host.

### 14.3. Do not use state to pass full secret URLs

<code>state</code> should help correlate the callback, not hold access tokens, session IDs, client secrets, or PII. If storing a return path, use server-side SavedRequest/transaction mapping and open-redirect validation.

## 15. Issuer and public OP hostname must also be consistent

Portal:

~~~yaml
spring:
  security:
    oauth2:
      client:
        provider:
          company:
            issuer-uri: https://sso.example.com/realms/company
~~~

OP Discovery:

~~~text
https://sso.example.com/realms/company/.well-known/openid-configuration
~~~

must have issuer:

~~~json
{
  "issuer": "https://sso.example.com/realms/company"
}
~~~

The ID Token after login must have an <code>iss</code> matching the issuer trusted by the Client.

### 15.1. Do not use an internal issuer in one place and a public issuer in another

Incorrect:

~~~text
Spring issuer-uri:
    http://keycloak:8080/realms/company

Discovery issuer:
    https://sso.example.com/realms/company

ID Token iss:
    https://sso.example.com/realms/company
~~~

The issue is not solved by disabling issuer validation. The OP must advertise the appropriate canonical issuer, and the backend must reach the Discovery/Token/JWKS endpoints per trust/network configuration.

### 15.2. Can the backend URL differ from the issuer?

Some OPs support separate internal endpoints while keeping the public issuer unchanged. This must be explicitly supported by OP metadata/security profile and Spring Security client configuration; do not rewrite the issuer yourself or bypass validation.

### 15.3. Do not let the browser supply a dynamic issuer

If the application supports multiple tenants/providers, do not take directly:

~~~text
?issuer=https://unknown.example
~~~

to have the Client call Discovery/JWKS without control. Beyond OAuth mix-up, this can also be an SSRF/supply-chain trust issue. Use a <code>ClientRegistration</code> allowlist or a trusted tenant registry with an onboarding/approval workflow.

## 16. Multiple providers and multiple Redirect URIs

For example, a Portal supporting two OPs:

~~~text
Registration ID: company
Issuer: https://sso.company.example/realms/workforce
Callback: https://portal.example.com/login/oauth2/code/company

Registration ID: partner
Issuer: https://login.partner.example/oidc
Callback: https://portal.example.com/login/oauth2/code/partner
~~~

Spring Boot:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: ${COMPANY_CLIENT_ID}
            client-secret: ${COMPANY_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile]
          partner:
            provider: partner
            client-id: ${PARTNER_CLIENT_ID}
            client-secret: ${PARTNER_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid]
        provider:
          company:
            issuer-uri: https://sso.company.example/realms/workforce
          partner:
            issuer-uri: https://login.partner.example/oidc
~~~

### 16.1. Each OP must register the exact callback

The Company OP only needs to allow the <code>/company</code> callback; the Partner OP only needs to allow the <code>/partner</code> callback per their registrations.

Do not register a wildcard <code>/login/oauth2/code/*</code> to let all providers redirect to any route.

### 16.2. OAuth mix-up risk

If a callback from Provider A is processed as Provider B, the application might send the authorization code/token credentials to the wrong Token Endpoint. Maintain binding across:

~~~text
state ↔ authorization request ↔ registrationId ↔ issuer ↔ token endpoint
~~~

and OIDC validation of <code>iss</code>, <code>aud</code>, and nonce per flow. RFC 9207 describes issuer identification to mitigate mix-up for OAuth2 authorization responses when supported by the profile/provider.

### 16.3. Changing providers does not mean changing the public URL

A Public Portal can be a single hostname for multiple OPs. Conversely, each environment may have multiple public hostnames; explicit mapping and registration allowlists are needed rather than guessing the provider from an arbitrary header.

## 17. Multi-tenant and multiple public hostnames

A SaaS Portal has:

~~~text
https://tenant-a.portal.example.com
https://tenant-b.portal.example.com
~~~

If the same OIDC ClientRegistration uses <code>{baseUrl}</code>, the callback can change depending on the request hostname.

### 17.1. The problem

The OP may allow only a fixed list of Redirect URIs, while tenants are created dynamically. Do not solve this with:

~~~text
https://*.portal.example.com/login/oauth2/code/company
~~~

when policy/security prohibits wildcards.

### 17.2. Viable architectures

**Option A — Centralized callback hostname**

~~~text
All tenants
   ↓
https://auth.portal.example.com/login/oauth2/code/company
   ↓
Server-side transaction/tenant mapping
   ↓
Redirect back to permitted tenant after login
~~~

Pros: one fixed registered Redirect URI. However, it requires careful design of cookie/session/cross-site correlation, tenant trust, return URL validation, and avoiding uncontrolled forwarding of authorization codes/tokens across tenant origins.

**Option B — ClientRegistration/Redirect URI per onboarded tenant**

Each tenant uses a registration/URI created and approved server-side. Requires automating OP registration and lifecycle management, without allowing users to input arbitrary issuers/callbacks.

**Option C — Isolate tenants via separate realms/issuers or deployments**

Suitable for environments with high isolation requirements, at higher operational cost.

### 17.3. Host validation

Before generating a redirect:

1. Resolve the hostname from a trusted proxy.
2. Look up the tenant mapping in the backend.
3. Accept only hosts with verified ownership that are allowlisted.
4. Select the ClientRegistration/issuer matching the tenant.
5. Save the transaction binding to session/state.
6. After callback, verify issuer/sub/tenant and return target.

Do not use self-declared email domains or a standalone request Host header as proof of tenant ownership.

## 18. OIDC logout and environment-specific post_logout_redirect_uri

When the Portal uses **RP-Initiated Logout**, the browser may be redirected to the OP:

~~~text
https://sso.example.com/realms/company/protocol/openid-connect/logout
~~~

and then the OP sends the browser back to the Portal:

~~~text
https://portal.example.com/login?logout
~~~

This URL is typically passed via <code>post_logout_redirect_uri</code> and may need to be registered/allowlisted separately at the OP.

### 18.1. Logout URL differs from login callback

The two URLs are typically:

~~~text
Login redirect_uri:
  https://portal.example.com/login/oauth2/code/company

Post-logout redirect URI:
  https://portal.example.com/login?logout
~~~

Do not register the post-logout URL in the login callback allowlist and assume that is sufficient; the OP may enforce separate verification rules.

### 18.2. Spring Security Servlet handler

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.oidc.web.logout
    .OidcClientInitiatedLogoutSuccessHandler;
import org.springframework.security.oauth2.client.registration
    .ClientRegistrationRepository;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class PortalOidcLogoutConfig {

    @Bean
    SecurityFilterChain portalChain(
            HttpSecurity http,
            ClientRegistrationRepository registrations)
            throws Exception {

        var handler =
            new OidcClientInitiatedLogoutSuccessHandler(registrations);

        handler.setPostLogoutRedirectUri(
            "{baseUrl}/login?logout");

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .logout(logout ->
                logout.logoutSuccessHandler(handler));

        return http.build();
    }
}
~~~

This is a **SecurityFilterChain replacing a simple login chain**, not a configuration layered on top of another chain with the same matcher. APIs may vary by Spring Security version; consult the docs for your specific version.

### 18.3. Local logout and OP logout differ

A local <code>POST /logout</code> with CSRF only ends the Portal session per configured handlers. RP-Initiated Logout asks the OP to end the SSO session and may use <code>id_token_hint</code> along with parameters per the OP profile.

OP logout behavior, post-logout redirect URI registration, and browser SSO cookies must be tested against the provider in use.

### 18.4. Reverse proxy affects logout just like login

If <code>{baseUrl}</code> is derived as:

~~~text
http://portal-service:8080
~~~

then <code>post_logout_redirect_uri</code> can also be wrong. Public scheme/host/prefix handling must be consistent across both login and logout.

## 19. Session, CSRF, and cookies when hostnames change

### 19.1. www and non-www

If a user visits:

~~~text
https://www.portal.example.com
~~~

but the OP only registered:

~~~text
https://portal.example.com/login/oauth2/code/company
~~~

then you need a **canonical host redirect before starting the OAuth2 flow**, or exact registration/configuration per host according to security policy.

Do not:

~~~text
Begin state under www.portal.example.com
Callback to portal.example.com
~~~

and expect a host-only session cookie from <code>www</code> to be sent to the apex host.

### 19.2. Session cookie scope

A host-only cookie:

~~~text
portal.example.com
~~~

cannot automatically be used at:

~~~text
staging.portal.example.com
~~~

This is good for isolation between environments. Do not widen the cookie Domain just to share sessions between production and staging.

### 19.3. Spring Session across multiple instances

An initiation request hitting instance A and the callback hitting instance B requires shared session/authorization request state. Shared Redis/JDBC-backed Spring Session or sticky sessions per architecture is a solution.

However:

- Shared sessions do not replace exact redirect URI validation.
- Correct TLS does not automatically synchronize state.
- Correct X-Forwarded-Host does not replace the Spring Security OAuth2AuthorizationRequestRepository.

## 20. Architecture scenarios: direct HTTPS vs. proxied HTTPS

### 20.1. Direct HTTPS at Spring Boot

If the app serves HTTPS directly:

~~~text
Browser → https://portal.example.com:443 → Spring Boot TLS
~~~

then the server needs a valid keystore/certificate and proper public host resolution. <code>server.forward-headers-strategy=none</code> can be appropriate if there is no proxy and the app does not trust forwarded headers.

Pros: fewer scheme-translation layers. Cons: the application must manage TLS termination/cert lifecycle or use a supporting web server.

### 20.2. TLS termination at ingress

If:

~~~text
Browser → HTTPS ingress → HTTP Pod
~~~

then Spring Boot needs trusted forwarded headers or an appropriate public-base-url mapping mechanism. Do not mechanically set <code>server.ssl.enabled=true</code> inside the Pod if the ingress is doing <code>proxy_pass http://...</code> to the backend; the protocol between ingress and Pod must match.

### 20.3. TLS re-encryption

If:

~~~text
Browser → HTTPS ingress → HTTPS Pod
~~~

then the app and ingress need trust/certificates for the internal hop, while the public host/port may still differ from the Pod's host/port. Forwarded metadata remains relevant for public URL generation.

## 21. Testing Redirect URIs before going to production

A test must verify all of the following:

1. The Portal page is accessed by the browser over the public HTTPS host.
2. The authorization initiation response redirects to the correct OP.
3. The <code>redirect_uri</code> query parameter in the OP authorization URL matches the public HTTPS callback.
4. The OP registration permits that URI.
5. The browser returns to the callback with the right host/path/query.
6. The session cookie is present and state correlation is valid.
7. Token exchange hits the right OP, and ID Token issuer/audience/nonce validation succeeds.
8. The login success handler routes the user to a safe target.

### 21.1. Manual testing with browser DevTools

In a controlled staging environment:

~~~text
1. Visit https://portal.staging.example.com
2. Open the Network tab
3. Click Login
4. Inspect the 302 Location to the OP Authorization Endpoint
5. Verify client_id and redirect_uri (do not copy code/state)
6. Log in with a staging account
7. Confirm the HTTPS callback has the right host and path
8. Confirm the browser session is maintained
9. Test logout and the post-logout redirect
~~~

**Avoid sharing HAR files or screenshots containing authorization codes, state, ID Tokens, or session cookies** in public tickets. If artifacts are needed, redact them.

### 21.2. curl only verifies part of the picture

You can inspect TLS/headers or Discovery:

~~~powershell
curl.exe -I https://portal.staging.example.com/login
curl.exe -I https://sso.staging.example.com/realms/company/.well-known/openid-configuration
~~~

However, <code>curl -I</code> sends HEAD and does not go through browser sessions or the Authorization Code Flow. Do not treat an HTTP 200/302 on a health or login page as proof that the OIDC callback works.

### 21.3. Inspecting the generated redirect_uri

An initiation GET:

~~~text
https://portal.staging.example.com/oauth2/authorization/company
~~~

may return:

~~~http
HTTP/1.1 302 Found
Location: https://sso.staging.example.com/.../auth?response_type=code&client_id=portal-staging&redirect_uri=https%3A%2F%2Fportal.staging.example.com%2Flogin%2Foauth2%2Fcode%2Fcompany&state=...
~~~

In automated tests, parse the URL/URL-encoded query and compare <code>redirect_uri</code> as a URI. Do not assert by grepping the raw URL, which is brittle due to percent encoding and query parameter ordering.

## 22. MockMvc testing of forwarded headers and URL generation

MockMvc can test the URL generated by Spring Security **if the TestApplicationContext actually enables the corresponding forwarded header handling**.

Example test configuration:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Test skeleton:

~~~java
package example.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PublicRedirectUriTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void loginUsesExternalHttpsHost() throws Exception {
        MvcResult result = mockMvc.perform(
                get("/oauth2/authorization/company")
                    // Trusted proxy context in test;
                    // does not mean the Internet is allowed to set these headers.
                    .header("X-Forwarded-Proto", "https")
                    .header("X-Forwarded-Host",
                        "portal.staging.example.com")
                    .header("X-Forwarded-Port", "443"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        String location = result.getResponse().getHeader("Location");
        assertNotNull(location);

        // Parse the authorization URL and decode redirect_uri,
        // then assert the value:
        // https://portal.staging.example.com/login/oauth2/code/company
        // Do not compare raw query strings since param order/encoding may vary.
        assertTrue(location.contains("redirect_uri="));
    }
}
~~~

**Limitations of the skeleton:** The test requires a valid test <code>ClientRegistrationRepository</code> and supplied OP issuer/authorization endpoint metadata; the TestContext must actually register <code>ForwardedHeaderFilter</code> or its equivalent. A test that sets headers without enabling the filter will not simulate production.

### 22.1. Comparing against tests without forwarded headers

Two cases can be executed:

| Simulated input request | Expected base URL |
|---|---|
| Internal HTTP, no trusted forwarding | Internal URL or direct backend URL |
| Internal HTTP, trusted <code>X-Forwarded-Proto=https</code>, <code>X-Forwarded-Host=portal.staging.example.com</code> | HTTPS staging public URL |

Tests should also verify that when port=443, <code>:8080</code> is not inserted into the URL.

### 22.2. Security test for forged headers

A test that **only sends <code>X-Forwarded-Host: attacker.example</code> to MockMvc** is not enough to prove the ingress is secure; if the framework trusts the header, the test might intentionally produce the wrong URI.

To verify the security boundary, you need a **deployment integration test passing through the trusted edge proxy**:

1. Client sends malicious forwarded headers.
2. Ingress strips/overwrites them per policy.
3. Spring app sees the allowed public hostname.
4. OP authorization request does not contain the attacker host.

This is a test of **proxy + application**, not just a single filter.

## 23. OP integration testing and callback verification

MockMvc can test initiation, but a complete OIDC flow requires a reliable OP/stub:

~~~text
Portal request
    ↓
Authorization request & state stored
    ↓
OP authorization endpoint
    ↓
Callback code + matching state
    ↓
Token Endpoint exchange
    ↓
ID Token signature, issuer/audience/nonce validation
    ↓
Authenticated session
~~~

In staging integration tests:

- Use test accounts, not production users.
- Register the HTTPS Redirect URI matching the staging hostname.
- Use the staging Client ID/secret.
- Preserve HTTP session/state.
- Verify the Principal <code>(iss, sub)</code> is authenticated.
- Verify the browser receives appropriate <code>Secure</code>/<code>HttpOnly</code> cookies.
- Test both the success handler and failure handler.

**Do not** run <code>mockMvc.perform(get("/private").with(oidcLogin()))</code> and conclude that Redirect URIs, proxies, or ID Tokens have been tested. <code>oidcLogin()</code> mocks an Authentication; it does not run the authorization-code callback.

## 24. Multi-instance deployment: HTTPS is right, yet the callback still fails

Kubernetes:

~~~text
Browser
  |
HTTPS Ingress
  |
  +--> Instance A
  |
  +--> Instance B
           |
        Shared session store (if any)
~~~

A flow:

~~~text
GET /oauth2/authorization/company → A creates state=S1 in session
GET /login/oauth2/code/company?state=S1 → B receives callback
~~~

If B cannot read A's session/authorization request, login fails with:

~~~text
authorization_request_not_found
invalid_state
~~~

This differs from <code>redirect_uri_mismatch</code>. Independent issues:

| Layer | Error |
|---|---|
| Public URL/forwarded headers | Redirect URI has wrong scheme/host/port |
| OP registration | Redirect URI is not allowed |
| Session cookie | Browser does not send cookie back on callback |
| Session store | Node B cannot read node A's state |
| OAuth request repository | Authorization request was lost/overwritten |
| Token Endpoint | Code expired/reused or PKCE/client authentication failed |

Do not “fix” missing state errors by disabling state validation. Use Spring Session or session coordination aligned with HA requirements.

## 25. Troubleshooting by symptom

| Symptom | Common cause | Verification/remediation |
|---|---|---|
| OP reports <code>redirect_uri_mismatch</code> | URI differs from registration | Compare exact scheme/host/port/path with OP |
| Redirect URI is <code>http://portal-service:8080</code> | App does not receive trusted forwarded scheme/host | Check ingress headers + Boot strategy |
| Redirect URI is <code>http://portal.example.com</code> | X-Forwarded-Proto wrong/missing | Check TLS termination and proxy |
| Redirect URI includes public <code>:8080</code> | X-Forwarded-Port or URI synthesis wrong | Check port mapping/header |
| Callback returns 404 | App callback filter/path or ingress rewrite wrong | Check callback path and context prefix |
| Callback goes to <code>/portal/portal/login...</code> | Prefix applied twice | Choose either context-path or X-Forwarded-Prefix cleanly |
| Browser moves from www to apex and loses session | Host-only cookie differs by hostname | Canonical host before initiation |
| Callback <code>authorization_request_not_found</code> | Cookie/session/repository missing | SameSite, session store, load balancer |
| Callback GET state mismatch | Flow started in different session/multi-tab | Do not disable state; investigate correlation |
| Form-post callback state missing | SameSite=Lax blocks cross-site POST cookie | Design None; Secure or appropriate flow; narrow CSRF |
| Callback returns <code>invalid_grant</code> | Code expiry/reuse, PKCE/redirect mismatch | Check token request and OP logs, do not endlessly retry code |
| ID Token issuer mismatch | Internal vs. public OP host differs | Exact Discovery issuer and <code>iss</code> |
| JWKS TLS failure | JVM does not trust OP certificate | Truststore and certificate chain |
| HSTS header missing | App thinks request is HTTP or proxy overrides it | Check headers from public HTTPS ingress |
| Session cookie lacks Secure | Cookie config/proxy secure-request detection | Inspect Set-Cookie from public route |
| Staging login redirects to production | Shared Client ID/wrong URI | Separate ClientRegistration/OP allowlist |
| Logout returns to HTTP | <code>post_logout_redirect_uri</code> uses wrong base URL | Forwarded headers and OP logout registration |
| Tenant A callback goes to Tenant B | Loose host/tenant mapping | Trusted host allowlist, state/issuer binding |
| Unexpected 302 to attacker domain | Untrusted Host/forwarded-header injection | Ingress sanitize, allowed hosts |
| Browser reports “too many redirects” | HTTPS canonicalization, proxy scheme/cookie config | Trace redirect chain, ingress ↔ app |
| Only node A can log in | Local session/secret drift | Shared sessions and consistent config |

### 25.1. Practical investigation workflow

~~~mermaid
flowchart TD
    A["OIDC Login fails in staging/prod"] --> B{"Did browser reach the right HTTPS Portal host?"}
    B -->|No| C["DNS, TLS cert, canonical host, ingress routing"]
    B -->|Yes| D{"Is the authorization request redirect_uri right?"}
    D -->|No| E["Forwarded headers, Boot strategy, prefix, environment config"]
    D -->|Yes| F{"Does the OP allow the exact redirect_uri?"}
    F -->|No| G["OP client registration / exact redirect allowlist"]
    F -->|Yes| H{"Did callback reach the right host/path with cookie?"}
    H -->|No| I["Ingress rewrite, SameSite, Secure, Domain/Path"]
    H -->|Yes| J{"Did Spring find state/authorization request?"}
    J -->|No| K["Session store, multi-instance, OAuth2 repository"]
    J -->|Yes| L{"Did token exchange + OIDC ID Token validation succeed?"}
    L -->|No| M["PKCE, code lifetime, issuer, client auth, JWKS"]
    L -->|Yes| N["Success handler / saved request / business authorization"]
~~~

### 25.2. What to log, and what not to log?

Safe to log:

~~~text
environment=staging
registrationId=company
publicHost=portal.staging.example.com
externalScheme=https
redirectUriTemplate={baseUrl}/login/oauth2/code/{registrationId}
redirectUriHost=portal.staging.example.com
stateRepositoryFound=true
oauth2ErrorCategory=invalid_grant
correlationId=...
~~~

Do not log:

~~~text
authorization_code
real state
real nonce
code_verifier
access_token / refresh_token / id_token
client_secret
session_cookie
client_assertion
~~~

In particular, an HTTP access log containing the **full callback query** can expose <code>code</code>/<code>state</code>. Configure proxy/app logging redaction and restrict artifact retention.

## 26. Go-live preparation runbook

### 26.1. Pre-deployment

1. **DNS:** public host points to the right ingress/load balancer.
2. **TLS:** certificate matches public hostname, with expiry monitoring.
3. **Canonical URL:** definitively choose www/apex, context path, and HTTPS.
4. **Edge trust:** proxy accepts only known hosts, strips/overwrites forwarded headers.
5. **Backend exposure:** private service/port is not opened directly to the Internet.
6. **Boot strategy:** choose <code>none/native/framework</code> appropriate for the infrastructure, avoiding double forwarded-header processing.
7. **OIDC registration:** separate Client ID/secret/issuer/redirect URI per environment.
8. **OP allowlist:** exact login callback URI and logout callback if applicable.
9. **Session cookies:** proper Secure, HttpOnly, SameSite, and Domain/Path.
10. **Session store:** HA if running multiple instances.
11. **OAuth security:** state, PKCE, nonce, and issuer/audience/signature validation enabled.
12. **Logs:** free of codes/state/tokens/cookies/secrets.

### 26.2. Post-deployment

1. Access the public HTTPS URL from a real browser.
2. Verify HSTS and the TLS cert against policy.
3. Click login and read <code>redirect_uri</code> in the Authorization Endpoint redirect.
4. Verify the right ClientRegistration/OP issuer.
5. Use an environment-specific test account, not production data outside authorized procedures.
6. Verify the public HTTPS callback and session cookie.
7. Verify ID Token validation and login success.
8. Verify access to protected routes after login.
9. Verify logout POST/CSRF and OP logout if applicable.
10. Test cross-node multi-instance callbacks.
11. Verify whether users arriving via www/alias URLs are canonicalized properly before login.
12. Monitor metrics for <code>redirect_uri_mismatch</code>, missing state, invalid_grant, and login failure rates.

### 26.3. Rollback/rotation

When changing the public hostname or ClientRegistration:

- Add the new OP redirect registration via a controlled process before cutover.
- Run smoke tests against the new public host.
- Determine how old session cookies behave when the host changes.
- Do not leave unnecessary wildcards/old callbacks around indefinitely.
- Plan to revoke the old host's client secret and redirect URI after the transition window.
- Do not change <code>issuer-uri</code> arbitrarily: an issuer change can mean a new trust domain and affect linked accounts.

## 27. Scenario exercises

### Exercise 1 — Wrong scheme after TLS termination

The public Portal is <code>https://portal.example.com</code>, while the Spring Boot backend listens on HTTP 8080. Yet the authorization redirect URI is <code>http://portal-service:8080/login/oauth2/code/company</code>.

**Question:** Where is the root cause?

**Answer hint:** The backend is using the internal origin due to missing/incorrect trusted forwarded metadata or base URL configuration. Fix the proxy and Boot strategy rather than loosening OP wildcards.

### Exercise 2 — Moving from localhost to staging

Local callback is:

~~~text
http://localhost:8080/login/oauth2/code/company
~~~

Staging uses:

~~~text
https://portal.staging.example.com/login/oauth2/code/company
~~~

**Question:** Should the same Client ID/secret be used?

**Answer:** Separate OP registrations and staging credentials from local/production. Register the exact staging callback, and do not use production secrets locally.

### Exercise 3 — Issuer differs from callback

~~~text
issuer=https://sso.example.com/realms/company
redirect_uri=https://portal.example.com/login/oauth2/code/company
~~~

**Question:** Is this an error?

**Answer:** No. The issuer belongs to the OP, while the redirect URI belongs to the Portal Client; they usually reside on two different hosts.

### Exercise 4 — Host header injection

An attacker sends <code>X-Forwarded-Host: attacker.example</code> to the public ingress.

**Question:** Which layer needs to handle this?

**Answer:** The trusted edge proxy must strip/overwrite untrusted forwarded headers and serve only known hosts; the backend must trust metadata only from the trusted network. Testing must go through the ingress, not just MockMvc.

### Exercise 5 — Duplicated prefix

The public callback becomes:

~~~text
https://example.com/portal/portal/login/oauth2/code/company
~~~

**Answer:** Both context-path <code>/portal</code> and <code>X-Forwarded-Prefix=/portal</code> may be configured while the proxy already rewrites the path. Pick one consistent mapping and register the exact OP URI.

### Exercise 6 — Wrong port

The OP allows the default HTTPS port 443 callback, but the Client sends a URL containing <code>:8080</code>.

**Answer:** Check <code>X-Forwarded-Port</code>, <code>Forwarded</code>, and Boot/server scheme/port normalization. Do not add port 8080 to the production allowlist.

### Exercise 7 — Form-post callback

The browser performs a cross-site POST callback, but does not send the <code>SameSite=Lax</code> session cookie.

**Answer:** Check response_mode support, SameSite=None; Secure, or an alternative correlation design, while keeping business CSRF protection and state validation.

### Exercise 8 — Callback loses state across two nodes

Initiation hits A, callback hits B, and both use the same public HTTPS host.

**Answer:** Having the right public URL does not automatically share sessions. Check Spring Session/affinity/cookie/authorization request repository; do not disable state.

### Exercise 9 — Wrong OP issuer

Spring configures:

~~~text
https://sso.example.com/realms/company
~~~

but the ID Token has <code>iss=http://keycloak:8080/realms/company</code>.

**Answer:** Fix the OP's canonical issuer/hostname metadata. Do not skip ID Token issuer validation.

### Exercise 10 — www vs apex

A user starts login from <code>www.portal.example.com</code>, gets called back at <code>portal.example.com</code>, and loses the session.

**Answer:** Canonicalize the host before initiation or deliberately design cookie/redirect URLs; do not widen the cookie Domain without control.

### Exercise 11 — GET localhost

**Question:** Why can <code>http://localhost</code> be used in a local test while HTTP public redirect URIs cannot be considered production-safe?

**Answer:** Localhost tests belong to the development trust boundary; production browser traffic traverses untrusted networks and requires HTTPS. Loopback exceptions in OAuth native apps are also not a license for every web Client to run over HTTP.

### Exercise 12 — Wrong RP-Initiated Logout URL

Login succeeds over HTTPS, but logout redirects back to <code>http://portal-service:8080/login?logout</code>.

**Answer:** <code>post_logout_redirect_uri</code> also depends on the public base URL. Check the OIDC logout handler, proxy metadata, and OP registration.

### Exercise 13 — Wildcard redirect URI

A teammate proposes <code>https://*.example.com/*</code> for all environments.

**Answer:** Don't do it. It expands the surface for diverting authorization codes when an attacker-controlled subdomain or open redirect exists. Use exact URIs or an automated registration workflow per environment/tenant.

### Exercise 14 — Disabling security validation to pass tests

The callback reports <code>invalid_state</code>, and the team wants to remove the state check.

**Answer:** No. Investigate cookies, SameSite, session store, callback host/path, authorization repository, and concurrency; removing state creates a login CSRF risk.

### Exercise 15 — Green MockMvc test

A test:

~~~java
mockMvc.perform(get("/reports").with(oidcLogin()));
~~~

passes.

**Question:** Does this prove TLS ingress, Redirect URI, and Token Endpoint work?

**Answer:** No. <code>oidcLogin()</code> only creates a mock principal in the test request; it does not run the browser/OP code flow.

### Exercise 16 — Separating environments

Production and staging currently share a Client ID and secret.

**Requirement:** Draft a separation plan.

**Hint:** Create a new staging OP registration, separate secret, and exact callback; test staging login; then remove the staging URI from the production registration. Monitor OAuth errors and avoid unexpectedly changing the production issuer.

### Exercise 17 — Multi-tenant callback

There are hundreds of tenant hostnames, and the OP does not allow wildcard redirects.

**Answer:** Consider a centralized callback hostname with server-side tenant/state binding or approved dynamic registration, without using an arbitrary browser return URL.

### Exercise 18 — Go-live runbook

Design a checklist for:

~~~text
Production portal:
  https://portal.example.com

OP issuer:
  https://sso.example.com/realms/company

Internal service:
  http://portal-service:8080
~~~

**Expected answer:** Cover DNS/cert, ingress trusted headers, Boot forwarded strategy, ClientRegistration/secret, exact redirect URI, Secure/HttpOnly/SameSite cookies, session storage, OP callback allowlist, browser E2E login/logout, and log redaction.

### Exercise 19 — Deployment hands-on

1. Set up a Spring Boot Servlet OAuth2/OIDC Client with registration <code>company</code>.
2. Create a test OP and separate clients for local/staging.
3. Configure the callback template <code>{baseUrl}/login/oauth2/code/{registrationId}</code>.
4. Set up a TLS reverse proxy on a staging test hostname.
5. From an HTTPS browser, verify the Authorization Endpoint redirect contains the public HTTPS URI.
6. Send forged Host/X-Forwarded-Host headers through the ingress and check that the headers are sanitized.
7. Test strict Redirect URI registration (wrong URI is rejected by the OP).
8. Test successful code/state/session callback.
9. Check session cookie flags via browser DevTools.
10. Test a missing state callback when the session is cleared and verify it fails closed.
11. Test logout post-logout redirect URI.
12. Test two instances with a shared session store.
13. Test the app under path prefix <code>/portal</code>.
14. Record the runbook/correlation ID without capturing raw codes/state/tokens/cookies.

## 28. Summary

- **Public base URL** belongs to the Portal/browser, **internal URL** belongs to the proxy/cluster, and **issuer URI** belongs to the OP. These three concepts are not interchangeable.
- Spring Security uses a Redirect URI template like <code>{baseUrl}/login/oauth2/code/{registrationId}</code>; <code>{baseUrl}</code> is only accurate when the request origin is recognized correctly by the framework.
- **HTTPS is mandatory in production web login** to protect authorization responses, session cookies, and browser traffic. HTTP localhost may be used for controlled local testing.
- The OP should register **exact Redirect URIs per environment**, distinguishing scheme, host, port, path, registration ID, and prefix; avoid broad wildcards.
- Staging and production should have separate ClientRegistrations/Client IDs/secrets; do not copy production credentials to local machines.
- When TLS terminates at the ingress, Spring Boot must understand the **public HTTPS scheme/host/port** via controlled forwarded headers or public URL mapping.
- <code>Forwarded</code>/<code>X-Forwarded-*</code> are **untrusted data if arriving directly from the Internet**. The edge proxy must strip/overwrite client-supplied values and restrict allowed hosts; the backend should not be directly public.
- <code>server.forward-headers-strategy</code> offers <code>none</code>, <code>native</code>, and <code>framework</code>; choose according to the container/ingress trust model, and do not stack multiple mechanisms.
- If the app has a <code>context-path</code> or <code>X-Forwarded-Prefix</code>, avoid prefix duplication and ensure the public callback path matches the OP allowlist.
- Session cookie <code>Secure</code>, <code>HttpOnly</code>, <code>SameSite</code>, and Domain/Path must fit the browser flow; a GET callback differs from a <code>form_post</code> callback.
- Issuer Discovery and ID Token <code>iss</code> must match the trusted issuer. Do not use an internal OP hostname to bypass issuer validation or mix providers.
- With multiple providers/tenants, maintain binding between <code>state</code>, ClientRegistration, issuer, and redirect URI; do not allow the browser to pick arbitrary callbacks/issuers.
- <code>post_logout_redirect_uri</code> serves RP-Initiated Logout and requires separate configuration/allowlisting per environment.
- Callback errors can stem from URL/proxy, cookies, session store, state, Token Endpoint, or ID Token validation. Classify accurately before changing configurations.
- Testing must pass through the **public HTTPS ingress and a real/appropriate stub OP**; MockMvc <code>oidcLogin()</code> does not prove Redirect URIs or TLS are working.
- Go-live requires verifying DNS/cert, exact callback, proxy trust, cookies, HA sessions, E2E login/logout, metrics, and credential redaction.

### References

- **Spring Security Reference — OAuth2 Login (Servlet):** authorization initiation, ClientRegistration, Redirect URI template, callback, and state.
- **Spring Security Reference — OAuth2 Client:** grant types, authorized clients, and provider configuration.
- **Spring Security Reference — OIDC Login and Logout:** ID Token issuer validation, RP-Initiated Logout, and post-logout redirect.
- **Spring Boot Reference — Embedded Web Servers / Behind a Front-end Proxy:** <code>server.forward-headers-strategy</code>, scheme/host/port, and reverse proxies.
- **Spring Framework Reference — ForwardedHeaderFilter / Forwarded Headers:** request origin reconstruction and removing untrusted headers.
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** authorization code redirect URI, state, and redirect restrictions.
- **RFC 7636 — Proof Key for Code Exchange (PKCE):** code interception mitigation.
- **RFC 9207 — OAuth 2.0 Authorization Server Issuer Identification:** issuer-based mix-up protection.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** Redirect URI exact matching, HTTPS, mix-up, and Authorization Code security.
- **RFC 7239 — Forwarded HTTP Extension:** standardized <code>Forwarded</code> header syntax and proxy metadata.
- **OpenID Connect Core 1.0:** ID Token, nonce, issuer/audience validation, and Authorization Code Flow.
- **OpenID Connect Discovery 1.0:** issuer, authorization/token/JWKS endpoints.
- **OpenID Connect RP-Initiated Logout 1.0:** <code>post_logout_redirect_uri</code> and OP logout.
- **OWASP Unvalidated Redirects and Forwards Cheat Sheet:** allowed redirect targets, open redirect defenses.
- **OWASP Session Management Cheat Sheet:** Secure, HttpOnly, SameSite, Domain/Path, session lifecycle.
- **OWASP Transport Layer Security Cheat Sheet:** certificates, trusted TLS, HSTS, and downgrade prevention.
