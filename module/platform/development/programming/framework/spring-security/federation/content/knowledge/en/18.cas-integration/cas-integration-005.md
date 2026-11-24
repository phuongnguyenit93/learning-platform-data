# Matching the Service URL During CAS Ticket Validation and Reverse Proxy Deployment

> **Context:** Spring Security – Federation · **Group:** CAS Integration. This document is for Spring Security applications using the **CAS protocol** for centralized login, especially when deployed behind Nginx, Ingress, an API Gateway, a Load Balancer, or a TLS-terminating reverse proxy. The core focus is that **the exact same service URL identifier must be used when the CAS Server issues the Service Ticket and when the backend validates the ticket**, even while the browser sees a public URL and the servlet container may see an internal URL. The Spring configuration snippets target Spring Boot 3.x / Spring Security 6.x Servlet (verify against your exact version); the Java 17 example runs standalone to teach the underlying mechanics.

## 1. The Problem: CAS Issues a Ticket for the Public URL, While the Service Validates with an Internal URL

A portal has a public callback:

```text
https://portal.example.org/app/login/cas
```

Yet the actual deployment topology is:

```text
Browser HTTPS :443
      |
      v
Nginx / Kubernetes Ingress
  public /app/login/cas
      |
      | proxy HTTP, rewrite /app -> /
      v
Spring Boot pod
  http://portal-service:8080/login/cas
```

The user initiates CAS login with:

```text
GET https://sso.example.org/cas/login
    ?service=https%3A%2F%2Fportal.example.org%2Fapp%2Flogin%2Fcas
```

The CAS Server issues `ST-...` **for that exact public service URL** and sends the browser back to:

```text
https://portal.example.org/app/login/cas?ticket=ST-example
```

If the Spring Boot backend then sends CAS validation as:

```text
GET https://sso.example.org/cas/serviceValidate
    ?ticket=ST-example
    &service=http%3A%2F%2Fportal-service%3A8080%2Flogin%2Fcas
```

then **the service at ticket issuance and the service at validation do not match**. CAS rejects it, typically with `INVALID_SERVICE`; an ST that undergoes a validation attempt is **consumed**, so fixing the URL and retrying that same `ST-example` will not work. You must configure a consistent service URL and start a **new login flow to obtain a fresh ST**.

This is one of the most common root causes of "CAS login loop," "ticket not recognized," "SSO fails after Ingress deploy," or "breaks only in production."

### Learning Objectives

After completing this article, you will be able to:

1. Define the **CAS service identifier** and distinguish the public callback URL from the internal backend URL.
2. Match the `service` value accurately between **`/login`** and **`/serviceValidate`** (or `/p3/serviceValidate`).
3. Understand the rule that an **ST is valid only for the issued service and a single validation attempt**, even when validation fails.
4. Distinguish **CAS registered service regex/allowlist** from **ticket-bound service comparison**; never weaken ticket verification just to work around a deployment issue.
5. Configure Spring Security's `ServiceProperties.setService(...)`, `CasAuthenticationFilter`, and `CasAuthenticationEntryPoint` around one **public canonical URL**.
6. Manage `Forwarded`, `X-Forwarded-Proto`, `X-Forwarded-Host`, `X-Forwarded-Port`, and `X-Forwarded-Prefix` safely across a reverse proxy.
7. Debug `INVALID_SERVICE` errors without logging raw tickets, TGCs, cookies/sessions, or PII.
8. Write tests covering external/internal URL comparisons, prefix rewrites, port/query encoding, host-header spoofing, multi-node/multi-tenant setups, and replay.
9. Use a standalone Java 17 example demonstrating service binding and ticket consumption.

## 2. How Does a CAS Service Ticket Bind the Service Identifier?

In the traditional CAS protocol:

- A CAS **Service Ticket (ST)** is a short-lived opaque bearer credential, typically prefixed with `ST-`.
- The user/browser initiates login by navigating to `CAS /login?service=<service-identifier>`.
- The CAS Server checks the registered service, authenticates the user (or reuses TGT/TGC), and issues an ST **exclusively for that service identifier**.
- The browser carries the ST via the `ticket` query parameter when redirected back to the service URL.
- The CAS service backend must call `CAS /serviceValidate?service=<same-service-identifier>&ticket=<ST>`.
- CAS verifies the ST and its binding to `service`, returning either `authenticationSuccess` or `authenticationFailure`.
- An ST is **valid for only one validation attempt**; CAS must invalidate it after that attempt, whether it succeeds or fails.

### 2.1. Rules from the CAS Protocol Specification

CAS 2.0 `/serviceValidate` requires:

| Parameter | Required? | Role |
| --- | --- | --- |
| `service` | Yes | **Identifier of the service for which the ST was issued** |
| `ticket` | Yes | ST to validate |
| `renew` | No | Demands an ST derived from primary credentials per CAS semantics |
| `pgtUrl` | No | Used only with CAS proxy authentication under the right profile |

CAS returns `INVALID_SERVICE` when the ticket is valid yet the `service` supplied at validation **does not match** the service bound to the ticket at issuance. The CAS Protocol also mandates invalidating the ticket after that validation attempt. For nonexistent, expired, or already-consumed tickets, you may receive `INVALID_TICKET`.

**Never try to retry the same ST** after `INVALID_SERVICE`, because the retry can turn into `INVALID_TICKET`. Fix the service configuration, start a fresh login to obtain a new ST, and test again.

### 2.2. "Matching Service" Means More Than Matching Hostname

For an initial service:

```text
https://portal.example.org/app/login/cas
```

the following values **must not be assumed equivalent** in a CAS transaction:

| Validation `service` | Difference |
| --- | --- |
| `http://portal.example.org/app/login/cas` | HTTP scheme instead of HTTPS |
| `https://portal.example.org:8443/app/login/cas` | Different port |
| `https://portal.example.org/login/cas` | Missing public path prefix `/app` |
| `https://portal-service:8080/login/cas` | Internal host and different port |
| `https://portal.example.org/app/login/cas/` | Differing trailing slash |
| `https://portal.example.org/app/LOGIN/cas` | Different path casing |
| `https://portal.example.org/app/login/cas?lang=vi` | Extra query parameter |
| `https://another.example.org/app/login/cas` | Different host/service |

URIs may behave equivalently at **some** HTTP layers or be custom-normalized by a CAS server per policy, but you must never **rely on implicit equivalence to bypass service-ticket binding**. The most reliable approach is issuing and validating with **the exact same canonical value**, verified by tests against **your deployed CAS Server**.

**Distinguish two levels of comparison:**

1. **Registered-service matching:** The CAS Server decides whether a service URL is permitted to request login, typically via admin-configured regex or literal service definitions.
2. **Ticket-to-service binding:** When validating a specific ST, CAS checks whether the ST was issued for the **corresponding service identifier**. A service registry regex approves services; **it does not automatically make an ST issued for `/app-a` usable at `/app-b`**.

A permissive registry rule is not a fix for `INVALID_SERVICE`; it can even open redirects or ticket issuance to unauthorized hosts.

### 2.3. URL Encoding and Comparison

The `service` parameter on `/login` and `/serviceValidate` is a **URL value that must be query-encoded**:

```text
Service identity (unencoded):
https://portal.example.org/app/login/cas

HTTP query parameter:
service=https%3A%2F%2Fportal.example.org%2Fapp%2Flogin%2Fcas
```

The CAS server decodes the query parameter to obtain the service identifier. **Do not compare two raw query strings merely because their percent-encoding differs**; compare properly parsed identities or inspect safe logs from normalized components. Equally, do not strip queries, paths, or ports automatically just to make two identities match: that can break security binding.

Avoid **double encoding**:

```text
Single encoding (correct for query-parameter encoding):
https%3A%2F%2Fportal.example.org%2Fapp%2Flogin%2Fcas

Double encoding (usually wrong):
https%253A%252F%252Fportal.example.org%252Fapp%252Flogin%252Fcas
```

Depending on the HTTP client, pass the **raw unencoded URI** to the builder that encodes query params—do not encode manually and then let the builder encode it a second time. Inspect the final request CAS actually receives, not just your YAML config.

### 2.4. Query Parameters in the Callback

If a service callback intentionally requires a fixed query parameter such as `/login/cas?tenant=corp`, that query parameter is **part of the service identity by policy**. The browser return URL will have `ticket=ST-...` appended by the CAS Server; when validating, the service normally needs to pass the **original identity without `ticket`**, rather than copying the entire callback query including `ticket` into `service`.

Do not do this:

```text
Issue:
service=https://portal.example.org/app/login/cas

Wrong validation:
service=https://portal.example.org/app/login/cas?ticket=ST-...
```

Some CAS clients/servers have specific rules for handling query parameters and service matching. Check the actual implementation, especially if the app constructs URLs dynamically. Avoid embedding unnecessary dynamic queries—such as timestamps, ad-hoc nonces, debug flags, or tracking parameters—in the service identity; use controlled request cache/state for the original protected URL.

## 3. Complete Flow Through a Reverse Proxy

```text
Browser                   Reverse Proxy / Ingress        Spring Boot Pod       CAS
   | HTTPS portal.example.org/app/login/cas             |                 |
   |---------------------------->|                     |                 |
   |                             | HTTP portal:8080    |                 |
   |                             | /login/cas          |                 |
   |                             |-------------------->|                 |
   |                             |                     |                  |
   | 302 to CAS /login?service=https://portal.example.org/app/login/cas   |
   |<----------------------------|<--------------------|                 |
   |------------------------------------------------------------------->|
   |         CAS authenticates, issues ST for PUBLIC service URL        |
   |<-------------------------------------------------------------------|
   | 302 to https://portal.example.org/app/login/cas?ticket=ST-...      |
   |---------------------------->|                     |                 |
   |                             | GET /login/cas      |                 |
   |                             |-------------------->|                 |
   |                             |                     |                 |
   |                             |  Backend CAS /serviceValidate?      |
   |                             |   service=PUBLIC URL&ticket=ST-...  |
   |                             |                     |--------------->|
   |                             |                     |<---------------|
   |                             |             authenticationSuccess    |
   |          Spring creates local SecurityContext/session              |
   |<----------------------------|<--------------------|                 |
```

**Note:** Even when CAS validation travels from the pod over an internal network to the CAS Server, **the `service` parameter value is still the public callback URL**, not the internal pod address and not the CAS Server's backend URL.

### 3.1. Three Non-Interchangeable Addresses

| Component | Example | Purpose |
| --- | --- | --- |
| **CAS Server base URL** | `https://sso.example.org/cas` | Where the CAS service calls `/serviceValidate` and the browser redirects to `/login` |
| **Public CAS service URL** | `https://portal.example.org/app/login/cas` | Service identifier for CAS to issue and validate STs |
| **Internal upstream URL** | `http://portal-service:8080/login/cas` | Where the proxy forwards requests to the Spring servlet |

Common mistake: putting the CAS Server base URL into `ServiceProperties.setService`, or putting the internal upstream URL into the `service` parameter when validating an ST.

### 3.2. Browser and Backend Observe Two Different Sides

The browser sees the redirect `Location` and the callback URL carrying `ticket`; the Spring Security backend calls CAS `/serviceValidate` over a **server-to-server backchannel**. Browser DevTools will **not** display the validation request because the backend executes it.

To debug without exposing secrets, observe both sides safely:

- Frontchannel: public CAS login redirect + browser callback path, **redacting `ticket`**.
- Backchannel: CAS validation result and `service` identity in normalized diagnostic form, never logging raw tickets or full query strings.

## 4. Sources of Mismatch Introduced by Reverse Proxies

### 4.1. TLS Termination Changes the Scheme

```text
Browser: https://portal.example.org
    |
TLS terminated by Nginx/Ingress
    |
Backend: http://portal-service:8080
```

If Spring reads `HttpServletRequest.getScheme()` on the backend without handling trusted forwarded headers, it can produce `http://...` in service URLs or redirects. Since CAS issued the ST for `https://...`, validation fails with a mismatch.

**Fix:** prefer configuring a **fixed canonical public service URL** on `ServiceProperties`. Also configure safe forwarded-header handling for redirects/absolute URLs if the framework generates other links. Never fake HTTPS by changing the CAS validator to "ignore scheme."

### 4.2. Proxies Rewrite `Host`

Many reverse proxies forward to upstreams with an internal `Host`:

```text
Public Host: portal.example.org
Upstream Host: portal-service
```

If the service URL is taken from the servlet request's host, it becomes `portal-service`. Conversely, if the proxy blindly copies the browser's `Host` header without an allowlist check, an attacker can manipulate links, redirects, and `service`.

**Solution:** configure explicit `server_name`/host routing on the proxy, accept only permitted `Host` values, strip/overwrite forwarded headers, and forward the **verified public host**. The application should read its public URI from managed config rather than treating arbitrary `Host`/`X-Forwarded-Host` headers as a trusted service identity.

### 4.3. Path Prefixes and Rewrites

For example, the public path is `/app/login/cas` while the upstream servlet path is `/login/cas`:

```text
Public:  https://portal.example.org/app/login/cas
Ingress: rewrite /app -> /
Backend: http://portal-service:8080/login/cas
```

If the service URL omits `/app` during validation, it mismatches. If both the application context path and `X-Forwarded-Prefix` prepend `/app`, you can end up with **`/app/app/login/cas`**.

Choose **exactly one** path strategy:

- Either the app actually runs with `server.servlet.context-path=/app` and ingress preserves the prefix; or
- The proxy rewrites away the prefix and the app runs at root context, while the **canonical public service URL** still includes `/app`.

Never combine both by accident. Test the redirect `Location`, the URL CAS receives, and the callback path the filter actually intercepts.

### 4.4. Port Mismatch

`https://portal.example.org/app/login/cas` and `https://portal.example.org:443/app/login/cas` may be treated equivalently in some URI/HTTP contexts, but you should not assume CAS service matching normalizes them identically across every release.

**Simple strategy:** use one fixed canonical URL and do not vary the port per request. Use the exact same representation in the service registry and probes; if a custom port such as `8443` is used, declare it explicitly on every side.

### 4.5. Context Path, Servlet Mapping, and Filter URL

`CasAuthenticationFilter` normally handles `/login/cas` inside the service app. With a proxy rewrite, the browser hits `/app/login/cas` while the servlet filter sees `/login/cas`. That is **completely consistent** when configured properly:

- Public CAS `service`: `https://portal.example.org/app/login/cas`.
- CAS filter local processing URL: `/login/cas`.
- Proxy rewrites `/app/login/cas` to `/login/cas`.
- `ServiceProperties.service` remains the **public** URL.

Do not change `CasAuthenticationFilter.filterProcessesUrl` to the full public URL; the filter matcher inspects the local servlet request path, not an absolute URL. Change the local path only when internal app routing genuinely requires it.

## 5. Preferred Solution: One Public Canonical Service URL from Configuration

For a CAS service app with a fixed callback, the most reliable approach is **specifying a single service URL value** in operator-controlled configuration:

```yaml
# application.yml: custom application properties, NOT
# Spring Security CAS default auto-configuration.
cas-client:
  server-base-url: "https://sso.example.org/cas"
  public-service-url: "https://portal.example.org/app/login/cas"

# Enable forwarded header parsing ONLY when ingress/proxy genuinely
# strips/regenerates headers and forms a trusted boundary.
server:
  forward-headers-strategy: framework
```

The two `cas-client.*` keys are **custom application properties**: to use them, bind them to a bean or read them in a configuration class. Do not assume Spring Boot auto-configures CAS login from these keys.

### 5.1. Fixed `ServiceProperties` Using the External URL

Create `CasPublicServiceConfiguration.java`:

```java
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.cas.ServiceProperties;

@ConfigurationProperties(prefix = "cas-client")
record CasClientSettings(
        String serverBaseUrl,
        String publicServiceUrl) {}

@Configuration
@EnableConfigurationProperties(CasClientSettings.class)
public class CasPublicServiceConfiguration {

    @Bean
    ServiceProperties serviceProperties(CasClientSettings settings) {
        String publicServiceUrl = settings.publicServiceUrl();

        // Stricter URI validation should run at bootstrap:
        if (!publicServiceUrl.startsWith("https://")) {
            throw new IllegalArgumentException(
                    "CAS public service URL must be HTTPS");
        }

        ServiceProperties service = new ServiceProperties();
        service.setService(publicServiceUrl);
        service.setSendRenew(false);
        return service;
    }
}
```

This is a **Spring Boot 3.x configuration class**, not a standalone program compiled directly with `javac`. It requires compatible `spring-security-cas`, configuration-properties binding, Spring Boot/Security beans, and the remaining CAS client components. Spring Boot binds `server-base-url` and `public-service-url` to the corresponding record fields when configured properly.

**Security note:** `startsWith("https://")` is only a preliminary check in this example and **does not replace a URI parser, hostname allowlist, or userinfo/port policies**. In a real application, validate with `URI` and an environment-specific callback allowlist. The value must come from managed configuration, never from a browser `service` query parameter.

The key point here is `ServiceProperties.setService("https://portal.example.org/app/login/cas")`. This value is used by `CasAuthenticationEntryPoint` when redirecting to CAS, and by `CasAuthenticationFilter`/provider when validating the ST in a standard CAS service-ticket flow.

### 5.2. CAS Server URL Differs from `ServiceProperties.service`

In another configuration class, the CAS login entry point uses the **CAS Server base URL**:

```java
import org.springframework.security.cas.ServiceProperties;
import org.springframework.security.cas.web.CasAuthenticationEntryPoint;

// Fragment; requires beans already declared in Spring.
CasAuthenticationEntryPoint entryPoint =
        new CasAuthenticationEntryPoint();

entryPoint.setLoginUrl("https://sso.example.org/cas/login");
entryPoint.setServiceProperties(serviceProperties);
```

In this fragment, `serviceProperties` is the bean instance from the previous section. The entry point builds the CAS login redirect with query `service=PUBLIC_URL`. Never put an internal upstream URL here, and never send an ST for validation through the browser.

### 5.3. `CasAuthenticationFilter` and the Callback Matcher

`CasAuthenticationFilter` normally listens on local `/login/cas`:

```java
import org.springframework.security.cas.web.CasAuthenticationFilter;

// Fragment: authenticationManager is a Spring AuthenticationManager
// wired with a compatible CasAuthenticationProvider.
CasAuthenticationFilter filter = new CasAuthenticationFilter();
filter.setFilterProcessesUrl("/login/cas");
filter.setAuthenticationManager(authenticationManager);
```

**Separate the two strings:** `filterProcessesUrl=/login/cas` is the **local servlet route**, whereas `serviceProperties.service=https://portal.example.org/app/login/cas` is the **external CAS callback identifier**.

If the app has `server.servlet.context-path=/app` and ingress does not rewrite, the local matcher still follows servlet context-path logic; verify the actual `servletPath` seen by the framework. Never accidentally produce `/app/app/login/cas` in the service URL.

### 5.4. `CasAuthenticationProvider` and `TicketValidator`

Spring Security uses `CasAuthenticationProvider` paired with a CAS client `TicketValidator`. Fragment example:

```java
import org.apereo.cas.client.validation.Cas20ServiceTicketValidator;
import org.springframework.security.cas.ServiceProperties;
import org.springframework.security.cas.authentication.CasAuthenticationProvider;

// Fragment: userDetailsService and serviceProperties are beans already
// configured in the application, not standalone runnable code.
Cas20ServiceTicketValidator validator =
        new Cas20ServiceTicketValidator("https://sso.example.org/cas");

CasAuthenticationProvider provider = new CasAuthenticationProvider();
provider.setServiceProperties(serviceProperties);
provider.setTicketValidator(validator);
provider.setKey("portal-cas-provider-v1");

// Also configure authenticationUserDetailsService / user-authority mapping
// per the API of your Spring Security release.
```

`Cas20ServiceTicketValidator` takes the CAS server base URL to call `/serviceValidate`. `CasAuthenticationProvider` must receive the right `ServiceProperties`, validator, and user-details/authorities mapping. Evaluate the username only after CAS succeeds; never build a principal from raw ticket queries or arbitrary browser data.

**Do not overlook:** if any one of the entry point, filter, or provider uses a different service URL from the rest, errors will still happen even if the `ServiceProperties` bean looks "right" at a glance.

### 5.5. Memorable Spring Security Flow Diagram

```text
Unauthorized GET /orders
       |
       v
CasAuthenticationEntryPoint
       |
       +--> CAS /login?service=PUBLIC_CALLBACK
                |
                v
        Browser CAS login / existing SSO
                |
                v
        GET PUBLIC_CALLBACK?ticket=ST-...
                |
         Reverse proxy rewrite
                |
                v
        CasAuthenticationFilter at local /login/cas
                |
                v
        AuthenticationManager
                |
                v
        CasAuthenticationProvider
                |
                v
        Cas20ServiceTicketValidator
                |
                +--> backend HTTPS CAS /serviceValidate
                    ?service=THE_SAME_PUBLIC_CALLBACK
                    &ticket=ST-...
                |
                v
        CAS authenticationSuccess -> principal
                |
                v
        Spring SecurityContext + local session
```

This is the **CAS protocol**; do not use `saml2Login()` to handle STs. A CAS native service ticket differs from a SAML Assertion/Response. Also, "reverse proxy" in this topic means an HTTP proxy in front of the app, **not a CAS Proxy Ticket (PT/PGT)**; `Cas20ProxyTicketValidator` and `pgtUrl` belong to a separate backend delegation topic.

## 6. Forwarded Headers: Computing the Right URL Without Trusting Attackers

### 6.1. Common Headers

| Header | Typical Purpose | Risk If Client-Supplied Headers Are Trusted |
| --- | --- | --- |
| `Forwarded: proto=https;host=portal.example.org` | RFC 7239 standard recording original scheme/host | Attacker spoofs host/protocol |
| `X-Forwarded-Proto: https` | Public HTTPS when upstream is HTTP | Spoofed scheme, wrong generated URLs |
| `X-Forwarded-Host: portal.example.org` | External host | Host-header injection / open redirect / service confusion |
| `X-Forwarded-Port: 443` | External port | Port mismatch and abnormal redirects |
| `X-Forwarded-Prefix: /app` | Public path rewritten by proxy | Prefix injection / double prefix |
| `X-Forwarded-For` | Client IP chain | IP spoofing / rate-limit bypass if trusted wrongly |

**Critical rule:** process forwarded headers only when generated by a **trusted proxy**. The edge proxy facing the Internet must **strip client-supplied copies** and then **set accurate values from controlled ingress routing**. Spring Framework docs emphasize that an app cannot tell on its own whether a header was added by a proxy or injected by an attacker; the trust boundary must be enforced at the edge.

### 6.2. Illustrative Nginx Proxy Snippet

The snippet below assumes Nginx is the **sole ingress** for the specific host `portal.example.org`; TLS is terminated at Nginx and the backend accepts only internal traffic from the proxy. This is a **topology fragment**, not a complete Internet-facing Nginx configuration; you still need a full TLS `server` block, certificates, logging, and explicit host rejection.

```nginx
# Inside a server block restricted to server_name portal.example.org
# listening on 443 ssl. Block direct internet traffic bypassing the proxy.
location /app/ {
    # Trailing "/" replaces the /app/ prefix with "/".
    # Public /app/login/cas -> upstream /login/cas.
    proxy_pass http://portal-service:8080/;

    # External headers are fixed/verified per vhost.
    proxy_set_header Host portal.example.org;
    proxy_set_header X-Forwarded-Host portal.example.org;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-Port 443;
    proxy_set_header X-Forwarded-Prefix /app;

    # Never forward raw client-supplied Forwarded/Host headers as trusted.
    # Edge security must also strip incoming forwarded variants.
}
```

**Verify separately:** a different Nginx rule with `proxy_pass http://portal-service:8080;` (no trailing slash) has different rewrite semantics; Kubernetes ingress-nginx uses regex/rewrite-target annotations instead of this config. Verify the **actual upstream path** with routing tests. A snippet never replaces ingress ownership, TLS termination, header sanitization, or host allowlisting.

It is **not enough** to set `X-Forwarded-Host` to `$http_host` from the browser and turn on Spring trust. If the edge lets unknown `Host` or spoofed `Forwarded` headers through, the app can generate redirects or ticket service URLs pointing to an attacker-controlled host.

### 6.3. Spring Boot Forwarded Header Handling

In Spring Boot (Servlet):

```yaml
server:
  forward-headers-strategy: framework
```

`FRAMEWORK` uses Spring framework-level forwarded header support such as `ForwardedHeaderFilter` depending on environment; `NATIVE` delegates to container-level handling; `NONE` ignores them. Choose based on runtime and ingress. **Never stack multiple rewrite layers** that mutate the request URL twice; test both redirect URLs and callback matching.

**However:** enabling `server.forward-headers-strategy=framework` should only be done once ingress strips forged headers and sets authentic ones. It **does not create a trust boundary by itself**, does not validate CAS service identity, and does not automatically secure session metadata/cookies.

In many cases, a **fixed `ServiceProperties.service` set to the exact public URL** solves CAS binding far more cleanly than deriving URLs dynamically from requests. Forwarded headers still matter for redirects and cookie `Path`/`Secure`, yet you should not let the CAS service identifier vary based on browser `Host` input.

### 6.4. `ForwardedHeaderFilter` and Filter Ordering

If configuring `ForwardedHeaderFilter` manually, ensure it runs before components that read the rewritten URL, and do not duplicate Boot's `server.forward-headers-strategy` auto-configuration. Spring Framework docs also provide `removeOnly` mode to **strip untrusted headers** without applying them.

Misordering the filter can cause:

- The CAS entry point to build redirects with the raw internal URI;
- The CAS provider to validate with a different URI;
- Application absolute links to leak the internal hostname;
- Callbacks to route to the wrong context path.

Verify behavior at **runtime**, not just in config files: a single request traversing the proxy must consistently observe the verified external scheme, host, and prefix.

### 6.5. Caution with `X-Forwarded-Prefix`

Some ingress controllers strip `/app` before forwarding upstream and add `X-Forwarded-Prefix: /app`. If the app also sets `context-path: /app`, Spring can generate absolute URLs with a duplicated prefix. Conversely, if ingress does not strip the prefix yet the app prepends a forwarded prefix anyway, paths also break.

**Decide upfront:** external path, upstream path, servlet context path, forwarded-prefix handling, and `ServiceProperties.service`. Draw the mapping table and test it rather than guessing.

## 7. Pre-Deployment URL Contract Table

For the example topology, a clear contract table looks like:

| Field | Canonical Value |
| --- | --- |
| Browser external origin | `https://portal.example.org` |
| Public CAS service callback | `https://portal.example.org/app/login/cas` |
| CAS Server login URL | `https://sso.example.org/cas/login` |
| CAS Server validation URL | `https://sso.example.org/cas/serviceValidate` |
| Backend listener | `http://portal-service:8080` |
| Browser public callback path | `/app/login/cas` |
| Backend servlet callback path | `/login/cas` |
| Proxy rewrite | `/app/` -> `/` |
| Spring Security `filterProcessesUrl` | `/login/cas` |
| Spring `ServiceProperties.service` | `https://portal.example.org/app/login/cas` |
| CAS registered service | Permits only this public callback or an equivalent tight pattern |
| Validation request `service` value | **Identical to** `ServiceProperties.service` |
| IdP/CAS trusted TLS connection | Backend -> `https://sso.example.org/cas` with CA/hostname verification |

This contract table is a critical operational artifact. Whenever changing domain, prefix, or port, update the **CAS service registry**, **client `ServiceProperties`**, **ingress route**, and **tests** in lockstep—never in just one place.

### 7.1. Alternative Pattern: App with a Real Context Path

If the app is configured with:

```yaml
server:
  servlet:
    context-path: /app
```

and ingress forwards `/app/login/cas` intact (no rewrite), the public callback remains `https://portal.example.org/app/login/cas`, though local routing/context path differs from the earlier example. Never simultaneously strip `/app` and configure `context-path=/app` unless an explicit rule restores the path; the callback will 404 before reaching `CasAuthenticationFilter`.

## 8. CAS Registered Service Matching Is Not Ticket Validation Matching

The Apereo CAS service registry can use a `serviceId` regex, literal, or another strategy to define **permitted applications**:

```text
Registered service (admin-defined):
  https://portal.example.org/app/login/cas

Ticket issued for:
  https://portal.example.org/app/login/cas

Validation service:
  https://portal.example.org/app/login/cas
```

In several CAS versions, the service registry uses **full regex matching** with default anchors; admins can also choose literal matching. However, **registry matching** and **binding of a specific ST** are two distinct checks.

### 8.1. Illustrative Registry Config Example

```json
{
  "@class": "org.apereo.cas.services.CasRegisteredService",
  "serviceId": "https://portal[.]example[.]org/app/login/cas",
  "name": "Portal CAS Client",
  "id": 1201
}
```

This is a **conceptual JSON snippet for an Apereo CAS registered service**, not a guaranteed complete schema for your current CAS release or service policies. Regex encoding, `matchingStrategy`, `evaluationOrder`, access strategy, and registry storage vary by version. If choosing a **literal matching strategy**, you can configure a literal URI instead of a regex; verify against the docs for your deployed release.

Do not open patterns like:

```text
https://.*
http[s]?://.*
.*login/cas.*
```

An overly broad rule can let attackers register or send browsers to out-of-contract URLs or obtain unintended tickets. The looser the CAS server config, the greater the risk of open redirects, unauthorized service enrollment, and credential abuse.

### 8.2. Why Not Modify CAS `ServiceMatchingStrategy` to "Ignore Host"?

Modern CAS Servers support customizing service matching; however, writing a strategy that treats every scheme/host/path as equivalent to work around proxy bugs undermines the goal that **an ST belongs exclusively to its issued service**. An ST leaked from service A could be accepted at service B if the matcher is too broad.

**Fix the upstream contract** first: `ServiceProperties`, Ingress, registry, and callback URL. If there is a genuine requirement for URL aliases or domain migration, design an **approved alias list** with expiration dates, clear mappings, tenant-isolation tests, and security review—never drop host verification globally.

### 8.3. CAS Proxy Server vs. HTTP Reverse Proxy

Similar names can cause confusion:

- **HTTP reverse proxy:** Nginx/Ingress sitting in front of Portal, handling TLS termination, path rewrites, and forwarded headers. That is this article's topic.
- **CAS proxy authentication:** PGT/PT, `/proxy`, `/proxyValidate`, `pgtUrl` for delegated backend calls. That is a **different protocol feature**.

Do not use `Cas20ProxyTicketValidator` just because the app sits behind Nginx. Standard CAS service-ticket login still uses `Cas20ServiceTicketValidator` or the matching CAS 3.0 validator when attributes are needed—never switch to proxy tickets needlessly.

## 9. HTTP Transcripts: Correct vs. Broken

### 9.1. Correct Flow

```http
# Frontchannel: Browser -> CAS Server
GET /cas/login?service=https%3A%2F%2Fportal.example.org%2Fapp%2Flogin%2Fcas HTTP/1.1
Host: sso.example.org

# CAS Server -> Browser (sample ticket, not a real ST)
HTTP/1.1 302 Found
Location: https://portal.example.org/app/login/cas?ticket=ST-DEMO

# Browser -> Proxy -> Portal callback
GET /app/login/cas?ticket=ST-DEMO HTTP/1.1
Host: portal.example.org

# Backend Portal -> CAS Server, over HTTPS
GET /cas/serviceValidate?service=https%3A%2F%2Fportal.example.org%2Fapp%2Flogin%2Fcas&ticket=ST-DEMO HTTP/1.1
Host: sso.example.org
```

The CAS Server returns `authenticationSuccess`, after which Spring establishes a local authenticated session. If the app needs to return the user to `/dashboard`, use a saved request or safe redirect (without turning the protected original path into the service identifier).

### 9.2. Broken Flow Due to Internal URL

```http
# Backend uses internal host/proto/path, differing from ST binding:
GET /cas/serviceValidate?service=http%3A%2F%2Fportal-service%3A8080%2Flogin%2Fcas&ticket=ST-DEMO HTTP/1.1
Host: sso.example.org
```

CAS may respond:

```xml
<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">
  <cas:authenticationFailure code="INVALID_SERVICE">
    Service mismatch
  </cas:authenticationFailure>
</cas:serviceResponse>
```

This XML is an **illustrative simulation**, and cannot be used to spoof a CAS response. Never log full exceptions, as CAS servers may include the ticket or service details inside error descriptions.

### 9.3. After `INVALID_SERVICE`, What Next?

1. Identify the service URL **that issued the ST**: from CAS entry-point config or redacted CAS audit logs; never store the ST.
2. Identify the service URL **the client sent during validation**: from `ServiceProperties`/provider or sanitized internal telemetry.
3. Compare scheme, host, port, path, prefix, query, and URL encoding.
4. Fix the **configuration** on the client, proxy, or registry—do not try to alter the ticket.
5. Start a **new login transaction**; never replay the old ST.
6. Test valid and wrong services, expired STs, and multi-node callbacks.

Never enable a "trust all tickets" mode, drop the `service` parameter, or ask CAS to accept arbitrary hosts just to keep login rates up.

## 10. Java 17: Simulating Service-Binding and Reverse-Proxy Mismatch

The following program runs on **plain JDK 17+** with no Spring or CAS dependencies. It simulates a CAS Server issuing an ST bound to a `serviceUrl` and validating via **exact identity match**. Every validation attempt **consumes the ticket before comparing**. The test demonstrates that using the internal URL is rejected, retrying that same ST with the public URL also fails, and only a **new ST** validated with the right public URL succeeds.

**This is not a real CAS Server:** ticket strings are synthetic values lacking real entropy/TTL; there are no passwords, MFA, CAS TGT/TGC, HTTPS, XML validation, or sessions. It models solely the relationship between service identity and single-use tickets.

Save file `CasServiceUrlContractDemo.java`:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Set;

public class CasServiceUrlContractDemo {

    private static final String PUBLIC_SERVICE =
            "https://portal.example.org/app/login/cas";
    private static final String INTERNAL_SERVICE =
            "http://portal-service:8080/login/cas";

    record Ticket(String serviceUrl, String username) {}

    static class MockCasServer {
        private final Map<String, Ticket> tickets = new HashMap<>();
        private int nextId = 1;

        String issue(String serviceUrl, String username) {
            String id = "ST-" + nextId++;
            tickets.put(id, new Ticket(serviceUrl, username));
            return id;
        }

        String validate(String ticketId, String serviceUrl) {
            // CAS service tickets are one-attempt credentials.
            Ticket issued = tickets.remove(ticketId);
            if (issued == null || !issued.serviceUrl().equals(serviceUrl)) {
                return "REJECT";
            }
            return "AUTH:" + issued.username();
        }
    }

    static boolean allowedPublicCallback(String candidate) {
        // Simulates a configured allowlist, NOT parsing proxy headers.
        return Set.of(PUBLIC_SERVICE).contains(candidate);
    }

    public static void main(String[] args) {
        MockCasServer cas = new MockCasServer();

        System.out.println("Public callback: " + PUBLIC_SERVICE);
        System.out.println("Internal equals public: "
                + PUBLIC_SERVICE.equals(INTERNAL_SERVICE));

        String first = cas.issue(PUBLIC_SERVICE, "alice");
        System.out.println("Wrong internal validation: "
                + cas.validate(first, INTERNAL_SERVICE));
        System.out.println("Retry same ticket: "
                + cas.validate(first, PUBLIC_SERVICE));

        String second = cas.issue(PUBLIC_SERVICE, "alice");
        System.out.println("Canonical public approved: "
                + allowedPublicCallback(PUBLIC_SERVICE));
        System.out.println("Correct validation: "
                + cas.validate(second, PUBLIC_SERVICE));
        System.out.println("Replay after success: "
                + cas.validate(second, PUBLIC_SERVICE));

        String spoofed = "https://evil.example/app/login/cas";
        System.out.println("Spoofed forwarded host approved: "
                + allowedPublicCallback(spoofed));

        String reports = "https://reports.example.org/login/cas";
        String third = cas.issue(PUBLIC_SERVICE, "alice");
        System.out.println("Other service validation: "
                + cas.validate(third, reports));
    }
}
```

Compile and run:

```bash
javac CasServiceUrlContractDemo.java
java CasServiceUrlContractDemo
```

**Exact** stdout:

```text
Public callback: https://portal.example.org/app/login/cas
Internal equals public: false
Wrong internal validation: REJECT
Retry same ticket: REJECT
Canonical public approved: true
Correct validation: AUTH:alice
Replay after success: REJECT
Spoofed forwarded host approved: false
Other service validation: REJECT
```

### 10.1. Explaining Each Result

- `Public callback` is the pinned external service identity.
- `Internal equals public=false`: the upstream HTTP/host/path cannot stand in for the external URL.
- `Wrong internal validation=REJECT`: a CAS ST issued for the public URL is rejected when validated with the internal service.
- `Retry same ticket=REJECT`: a failed validation attempt already consumed the ST; fixing the URL and replaying the ticket does not help.
- `Canonical public approved=true`: the public URL is in the demo app's fixed allowlist.
- `Correct validation=AUTH:alice`: a **fresh** ST for the public URL validates with the exact same identity.
- `Replay after success=REJECT`: a consumed ST cannot authenticate a second time.
- `Spoofed forwarded host approved=false`: a hostname outside the allowlist cannot become the service identity.
- `Other service validation=REJECT`: Portal's ST cannot be validated as a ticket for Reports.

### 10.2. Boundaries of the Example

`MockCasServer.issue` accepts any URL and username because it is a classroom model; real CAS requires a **registered service allowlist**, authentication handlers, and TGT/TGC sessions. `allowedPublicCallback` only models an allowlist, not how `Forwarded` headers are parsed/verified in production. `HashMap` is not safe for a CAS cluster and lacks TTLs and secure randomness; production requires a ticket registry with atomic consumption and timeouts.

Never copy this `validate` function as a production CAS client: a real client must call a trusted CAS Server `/serviceValidate` over HTTPS, handle `authenticationFailure` XML, and establish `Authentication`/local session only after success.

## 11. Testing the Contract in Spring Security

### 11.1. Three Core Checks

An integration test for CAS service URLs behind a proxy should verify all three together:

**A. Issue:** the browser receives a 302 to CAS Server `/login`; the URL-decoded `service` parameter equals `https://portal.example.org/app/login/cas`.

**B. Callback routing:** when the browser accesses `https://portal.example.org/app/login/cas?ticket=...`, the proxy routes the request to local `CasAuthenticationFilter` at `/login/cas` without 404, 403, or redirect loops.

**C. Validate:** the backend calls CAS `/serviceValidate` (or `/p3/serviceValidate`) with `service` **equal to exact identity A** and the corresponding ST; CAS returns the expected result. The browser does not need to observe this backchannel request directly.

### 11.2. MockWebServer / WireMock or CAS Test Server

You can configure a **CAS test server** to capture:

```text
GET /cas/login?...service=PUBLIC_CALLBACK...
GET /cas/serviceValidate?...service=PUBLIC_CALLBACK&ticket=TEST_ST...
```

Use only `TEST_ST` or synthetic fixtures; never store real tickets. When mocking CAS validation responses, distinguish **unit tests of request construction** from **security integration tests**: a mock returning success does not prove a real CAS Server enforces ticket-to-service binding, one-time consumption, trusted transport, and service registry rules.

For true integration tests, deploy an Apereo CAS test instance with matching service definitions and verify:

1. CAS issues an ST for the public callback.
2. Backend validates with the exact service -> success.
3. ST issued for the public callback validated with the internal URL -> `INVALID_SERVICE`.
4. Retrying the failed ST -> `INVALID_TICKET` or equivalent rejection.
5. ST issued for Portal validated with Reports URL -> rejected.
6. Unknown external service URL -> rejected by CAS registry.
7. Requests carrying forged forwarded headers -> cannot hijack the public callback identity.

### 11.3. Controlled Testing of Proxy Headers

| Request Scenario | Expected Public Callback Behavior |
| --- | --- |
| Public HTTPS, proxy strips `/app` | App uses exact `https://portal.example.org/app/login/cas` |
| TLS terminates, backend HTTP | `http://portal-service:8080` never appears in `service` |
| `X-Forwarded-Proto=https` from trusted proxy | Absolute URLs are accurate after sanitization |
| Client sends `X-Forwarded-Host=evil.example` | Edge strips/overwrites; CAS `service` does not change |
| Client sends `Forwarded: host=evil.example;proto=http` | Edge strips or overwrites; CAS `service` does not change |
| Client sends `X-Forwarded-Prefix=/evil` | Does not turn callback into `/evil/login/cas` |
| `Host` header not in allowed vhosts | Ingress rejects; no CAS redirect issued |
| Proxy omits `X-Forwarded-Prefix` where prefix is needed | Test catches missing `/app`; fix routing |
| App `context-path=/app` combined with ingress rewriting `/app` | Test catches 404 / double prefix |
| Changing `proxy_pass` with vs. without trailing slash | Test captures actual upstream path |
| Default port 443 vs. explicit `:443` in URL | Test verifies expected canonical representation |
| Callback with query `lang=vi` | Matches exact service identity if query is part of contract |
| Query gets double URL-encoded | Test detects CAS receiving malformed service identity |
| Multiple pods have differing service URL configs | Test fails rather than mistaking it for an IdP outage |

### 11.4. Assertions to Run Continuously in CI

- CAS redirect `service` is the **HTTPS public callback**, never an internal host.
- Callback `ticket` never appears inside the `service` sent to the validator (unless a distinct profile/URI identity was explicitly designed and verified).
- `ServiceProperties.service` is the exact same string across all CAS components and all pods.
- Local `CasAuthenticationFilter.filterProcessesUrl` matches the callback path after proxy rewrites.
- CAS Server service registry does not permit wildcard hosts violating security policy.
- Wrong service, expired ticket, and reused ticket all **create zero Spring Authentication**.
- When the CAS Server is unreachable or TLS fails, the app fails closed.
- Sessions are created only after successful ticket validation, never from an `ST-` prefix or browser query username.
- Successful callbacks redirect to a clean URL without retaining the raw ST.
- Logs/APM/WAF/Nginx never capture raw `ticket`, CAS TGC/session cookies, or full validation URLs.

## 12. Troubleshooting: Distinguishing Mismatches from Other Failures

| Symptom | Suspected Fault / Component | Check |
| --- | --- | --- |
| CAS reports `INVALID_SERVICE` on first validation | Issuance `service` differs from validation `service` | Compare scheme/host/port/path/query; do not retry the ST |
| After fixing URL, retrying the same ST yields `INVALID_TICKET` | ST was already consumed on the first attempt | Start a new CAS login |
| CAS redirects back to `http://internal:8080/...` | Misconfigured EntryPoint/`serviceProperties`/proxy headers | Use external canonical service URL |
| CAS redirects to right public URL yet Spring callback returns 404 | Wrong ingress rewrite or local filter path | Map public `/app/login/cas` to local `/login/cas` |
| Callback is treated as a protected route and redirects to CAS again | Filter order/matcher misses `/login/cas` | Check `SecurityFilterChain` and callback matcher |
| Validation sends `service` missing `/app` | Wrong `X-Forwarded-Prefix` or `ServiceProperties` | Configure fixed public URL and verify rewrite |
| Validation sends HTTP scheme | Broken TLS termination / forwarded handling | Configure trusted forwarded headers / public URL |
| Validation sends `:8080` or upstream host | URL derived from internal servlet request | Use canonical public service identity |
| Validation sends `:443` inconsistently | Differing canonical port representation | Standardize on one representation and test against CAS release |
| Host altered by client query/header | Untrusted forwarded/`Host` headers | Edge strip/allowlist; never build `service` from user input |
| CAS login rejected by registry before issuing ST | Service URL unregistered or regex mismatch | Update approved, narrow registered service definition |
| `/serviceValidate` returns HTTP 200 yet login fails | XML `authenticationFailure` | Parse CAS protocol response, not just HTTP status |
| `renew=true` makes CAS re-prompt for password | Policy requires fresh primary credentials | Cross-check `ServiceProperties.sendRenew` and CAS policy |
| ST expired | Browser/network latency or stale callback | Re-login; do not extend TTL indefinitely |
| CAS TGC not sent | Cookie domain/`SameSite`/`Secure`/path | Inspect CAS origin cookie; unrelated to service URL binding |
| User logs in successfully yet next request is anonymous | App local session/cookie/proxy affinity | Check Spring Session/`HttpSession` and `SecurityContext` |
| Node A succeeds, Node B hits `INVALID_SERVICE` | Pod config drift on `public-service-url` | Check readiness/version/config consistency |
| Validation TLS fails | Truststore, certificate/hostname, or network | Never disable hostname verification |
| CAS client uses proxy ticket validator just because Nginx is present | Confused reverse proxy with CAS PT/PGT | Use the protocol-appropriate ST validator |
| Proxy rewrites URLs after Ingress deploy | `public-service-url`/registry not updated together | Coordinated change + regression tests |

### 12.1. Investigation Order Without Leaking Tickets

1. **Failure class:** registry rejection before ST issuance, `INVALID_SERVICE` after issuance, `INVALID_TICKET`, callback 404, CAS backend TLS error, or local session failure?
2. **Inspect external callback:** check `ServiceProperties.service` config and `/cas/login` request with `service` properly redacted; never copy `ticket`.
3. **Inspect validation service:** log only the allowlisted service ID and configured URL fingerprint/normalized form—never log the ST or full query.
4. **Compare:** external scheme/host/port/prefix/path/trailing slash/query; verify ingress rewrite on a real request.
5. **Check pod consistency:** compare desired/applied config and service URL version across every node; never conclude cluster health from a single pod succeeding.
6. **Fix the broken layer:** Spring config, ingress routing, CAS registered service, or forwarded trust boundary.
7. **Fresh login:** the old ST is already consumed; never replay.
8. **Security tests:** verify wrong-service, attacker-host, expired, and replayed tickets are rejected, plus TLS and logging checks.

**Never** log `request.getQueryString()` on the callback or the full validation URL, because they contain `ticket=ST-...`. For auditing, generate an internal event ID and log a reason code such as `CAS_INVALID_SERVICE` alongside the permitted registration/service ID.

## 13. Protecting the Service URL from Host/Forwarded Injection

An application that builds the service URL like:

```java
// ANTI-PATTERN illustration: client-supplied host/proto can be spoofed.
// String service = request.getHeader("X-Forwarded-Proto")
//         + "://" + request.getHeader("X-Forwarded-Host")
//         + "/app/login/cas";
```

can be exploited if the proxy fails to strip headers. When the app redirects to CAS with `service=attacker.example`, CAS could redirect the browser to an unauthorized host if the registry is also too permissive, causing open redirects and ticket exposure.

Layered defenses:

1. Ingress **serves only allowed `Host` values** and rejects unrecognized vhosts.
2. Strip all incoming `Forwarded` and `X-Forwarded-*` headers from clients before injecting trusted values; do not overwrite one header while leaving the standard header intact.
3. Backends accept traffic only from the trusted proxy/service mesh; never expose pods or NodePorts directly to the Internet.
4. Spring Boot parses forwarded headers via framework/container **only after** proxy sanitization.
5. `ServiceProperties.service` is read from **static allowlisted config** or a per-tenant allowlist mapping, never from an arbitrary browser `Host`/URL.
6. CAS Server registry allows service callbacks only for exact domains, paths, and schemes—no broad regexes.
7. Test a client request carrying forged forwarded headers and confirm `service` remains unchanged.

### 13.1. TLS Hostname/Trust and the CAS Validation Backchannel

Terminating TLS at the Portal proxy does not mean **backend -> CAS Server** may skip TLS. CAS ticket validation must connect to `https://sso.example.org/cas/serviceValidate` with proper certificate chain and hostname validation and timeouts. **Never** use a `trustAll` HTTP client or disable SSL verification to resolve a login loop.

Note that a public CAS service ID does not prove the CAS Server's identity: the CAS Server origin must be an operator-managed URL validated over HTTPS. If an attacker could redirect `TicketValidator` to a rogue server, they could forge `authenticationSuccess`. Both service URL accuracy and CAS Server trust must **hold simultaneously**.

### 13.2. Preventing ST Leakage via Logs and Analytics

The ST appears in the callback query:

```text
https://portal.example.org/app/login/cas?ticket=ST-...
```

This is a bearer credential. Ensure:

- Never log raw query strings at reverse proxies, ingress, servlet request loggers, or APM spans.
- Never leak the ticket into third-party analytics or `Referer` headers when rendering callbacks.
- Set `Referrer-Policy: no-referrer` per policy and redirect to a clean URL after validation.
- Never paste real STs into support tickets, chat, or issue trackers.
- Rate-limit and alert on validation errors without writing raw CAS XML responses containing PII to logs.
- Rotate session IDs after login and manage `Secure`/`HttpOnly`/`SameSite` cookie attributes properly.
- Apply CSRF protection to state-changing requests on the local web app; CAS login validation does not replace CSRF or authorization.

## 14. Multi-Node, Blue/Green, and Multi-Tenant Service URLs

### 14.1. Multi-Pod: One Shared Public Service URL

A service running across 3 pods:

```text
portal-v1-pod-a:8080
portal-v1-pod-b:8080
portal-v2-pod-c:8080
        |
    Ingress /app/
        |
https://portal.example.org/app/login/cas
```

**All three pods must share the exact same `ServiceProperties.service`** if they serve callbacks for one public service identity. Never use `podName`, `nodeIP`, or runtime `server.port` as the service ID. A browser callback may land on a different pod than the one that initiated CAS login.

The CAS Server sees only one public registered service. Local Spring Security sessions and request caches need Redis/shared sessions or affinity per app requirements; that is a **separate** concern from ticket-to-service binding.

### 14.2. Blue/Green Domain or Prefix Migration

Suppose a new release moves the callback from:

```text
OLD https://portal.example.org/app/login/cas
NEW https://portal.example.org/workspace/login/cas
```

Coordinate carefully:

1. The CAS registry approves both old and new service IDs for a **bounded migration window** (if policy allows).
2. Ingress routes both old and new callbacks during in-flight transitions to the matching client configuration.
3. The old Spring client must **validate old STs with the old service**; the new client **validates new STs with the new service**. Do not switch all pods to the new config before in-flight old redirects complete.
4. Keep session/request state and auth paths consistent without accepting old STs at the new service by dropping binding.
5. Once old traffic drains and tests pass, retire the old registry entry, routing, and config.
6. If a service URL is recorded in request cache/state, never let the app trust a browser-chosen value.

If each deployment uses a single fixed `ServiceProperties`, blue/green may require **two deployments/filters** or a dedicated design for multiple approved service IDs—never try to "autodetect" from an untrusted `Host` header.

### 14.3. Multi-Tenant and Multiple External Hosts

For example:

```text
Tenant A: https://a.example.org/login/cas
Tenant B: https://b.example.org/login/cas
```

A single static `ServiceProperties.setService` bean represents **only one** service callback. If a single Spring deployment genuinely must serve multiple external identities, design:

- An operator-managed tenant -> approved public service URL mapping.
- Trusted registration/routing context to choose the service for login and validation.
- Verification tying the ticket's service URL to the right tenant/client—never choosing a tenant solely from raw `Host`, `ticket`, or username.
- Possibly filter/provider or `AuthenticationDetailsSource`/validator customization tailored to your Spring Security CAS release and CAS client semantics.
- Tests proving Tenant A's ticket cannot log in to Service B, even when both tenants share the same CAS Server.
- Never treat `setAuthenticateAllArtifacts(true)` as a magic switch for multi-tenant service URLs; read the full dynamic service authentication contract and enforce origin/tenant binding.

Spring Security documents `ServiceAuthenticationDetailsSource` for validating tickets across multiple URLs, particularly in **stateless CAS proxy ticket** flows. This flexibility **does not** mean accepting arbitrary service identities from the browser; it must remain bound to an allowlist and CAS service ticket semantics.

### 14.4. Consistency Across a CAS Cluster

A CAS Server cluster must use a shared/atomic ticket registry so an ST issued on node A is consumed once on node B. Every CAS node must share the exact same service registry and service matching policy; one node carrying a broader regex or different URL normalization will produce inconsistent behavior.

Some CAS Servers support custom `ServiceMatchingStrategy` implementations, but changing matching semantics requires explicit approval and cross-app/cross-tenant testing—never use it as a workaround for proxy URL bugs.

## 15. Important Negative Test Cases

| Scenario | Expected Result |
| --- | --- |
| ST issued for public `https://.../app/login/cas`, validated with same URL | PASS (assuming other conditions hold) |
| ST issued for public URL, validated with internal HTTP URL | **`INVALID_SERVICE` / reject** |
| ST issued for public URL, validated with URL missing `/app` | Reject |
| ST issued for public URL, validated with different host | Reject |
| ST issued for public URL, validated with port 8443 instead of 443 | Reject per policy |
| ST issued for Portal, validated at Reports | Reject |
| ST validation mismatch, then retrying same ticket with right service | Reject because ST was consumed |
| ST validation succeeds, then ticket replayed | Reject |
| Expired ST | Reject, require new login |
| Fabricated ticket `ST-fake` never issued | Reject |
| CAS backend TLS hostname mismatch | Reject / fail closed |
| Unregistered service ID | CAS refuses to issue/accept ST |
| Overly broad registry match rule | Security review/test FAIL |
| Browser sends `X-Forwarded-Host=evil.example` | Does not alter `ServiceProperties.service` or redirect |
| Browser sends `Forwarded: host=evil.example` | Stripped at edge; no effect |
| Browser sends `X-Forwarded-Prefix=/evil` | Stripped at edge; no effect |
| Proxy prefix duplicates `/app/app` | Integration routing test must fail |
| Proxy context mismatch causes callback 404 | Never loosen ticket validation |
| CAS `/serviceValidate` HTTP 200 with `authenticationFailure` XML | No `Authentication` created |
| CAS validation endpoint outage | Fail closed; never trust unvalidated tickets |
| Browser callback carrying `ticket` appears in access logs | Privacy/security test FAIL |
| One pod uses `http://portal-service`, another uses public URL | Config drift test FAIL |
| Tenant changes host; old-tenant ticket sent to new-tenant host | Reject; follow proper migration |
| `renew` enabled on one side while validator/issuer policy differs | Diagnose/reject without weakening service binding |
| Multiple CAS nodes accept replay of same ST | CAS ticket registry test FAIL |

**Do not just verify "user sees the dashboard"**: capture test backend CAS requests, verify issuer service identity, and assert rejection on ticket replay and wrong-service attempts.

## 16. Deployment Checklist

- [ ] Defined **one public canonical callback URL** per CAS service: scheme, host, port, prefix, path, and fixed query (if any).
- [ ] `CasAuthenticationEntryPoint` sends this exact URL in `/login?service=...`.
- [ ] `CasAuthenticationFilter` matches the exact **local callback path** after proxy rewrites.
- [ ] `CasAuthenticationProvider`/`TicketValidator` validates STs with the same service ID used at issuance.
- [ ] `ServiceProperties.service` never uses internal upstream hosts and is never computed dynamically from untrusted browser headers.
- [ ] CAS service registry allows only the exact HTTPS callback with a narrow matching strategy.
- [ ] Proxy strips/overwrites incoming `Forwarded` and `X-Forwarded-*` headers and rejects unknown `Host` headers.
- [ ] Spring `server.forward-headers-strategy` is chosen properly without double-rewriting.
- [ ] Prefix/context path verified in practice: no `/app/app` duplication and no missing `/app`.
- [ ] Proxy TLS termination is never confused with backend-to-CAS HTTPS trust.
- [ ] STs allow one validation attempt, are service-bound with short TTL, and reject mismatches/replays.
- [ ] CAS XML validation failures never create `Authentication` even when HTTP status is 200.
- [ ] STs rejected with `INVALID_SERVICE` are never retried with a corrected service.
- [ ] STs, raw query strings, cookies, and PII-bearing validation XML are redacted from proxy, servlet, and APM logs.
- [ ] Spring Security session ID rotation, session cookies, and authorization are verified.
- [ ] All pods share the exact same public service URL/registry contract, with drift alerts.
- [ ] Blue/green domain or prefix migrations keep old/new flows isolated with a sunset plan.
- [ ] Multi-tenant service URLs are allowlisted per tenant; never selected arbitrarily from `Host`.
- [ ] Tested matching/mismatched services, double encoding, port/case/trailing slashes, forged forwarded headers, SLO, and cookie/session side effects.
- [ ] `INVALID_SERVICE` runbook relies on event IDs and reason codes rather than asking for raw STs.

## 17. Review Questions

**Question 1.** CAS issues an ST for `https://portal.example.org/app/login/cas`. The backend runs at `http://portal-service:8080/login/cas`. Which URL must `service` contain during validation?  
**Answer:** The public callback URL **used when issuing the ST**, not the internal upstream URL.

**Question 2.** After `INVALID_SERVICE`, can you fix `service` and retry the same ST?  
**Answer:** No. The CAS protocol requires consuming the ST after a single validation attempt. Start a new login.

**Question 3.** The CAS service registry has a regex covering both `portal` and `reports`. Can Portal's ST be used at Reports?  
**Answer:** No. The registry permits applications to request tickets; each ticket remains bound to the **service identifier used when it was issued**.

**Question 4.** Should `CasAuthenticationFilter.filterProcessesUrl` be set to the full URL `https://portal.example.org/app/login/cas`?  
**Answer:** No. The filter matcher takes a **local servlet path** such as `/login/cas`; `ServiceProperties.service` holds the public URL.

**Question 5.** Should you enable `server.forward-headers-strategy=framework` without checking whether Nginx strips client headers?  
**Answer:** No. Forwarded headers can be spoofed by clients; trusted proxy sanitization and host allowlisting are required.

**Question 6.** Why can a trailing slash or `:443` cause errors?  
**Answer:** Because service identity must match the running CAS rules; never assume every URL representation normalizes identically.

**Question 7.** CAS login redirects to the right URL, yet the callback returns 404. Where is the bug?  
**Answer:** Likely a proxy rewrite/context path mismatch or wrong `CasAuthenticationFilter` matcher—never a reason to disable service binding.

**Question 8.** Is an HTTP 200 from `/serviceValidate` enough to create a local session?  
**Answer:** No. The XML body may contain `authenticationFailure`. You must parse the CAS protocol result.

**Question 9.** Are an HTTP reverse proxy and a CAS Proxy Ticket the same thing?  
**Answer:** No. Nginx/Ingress is a network proxy; CAS PGT/PT is a separate delegated authentication mechanism.

**Question 10.** Why is a fixed `ServiceProperties.service` generally better than building the URL from `Host`/`X-Forwarded-Host`?  
**Answer:** It prevents drift/mismatches and reduces host-header injection risks. Proxy headers still need proper handling for redirects and cookies.

**Question 11.** During a blue/green move from `/app/login/cas` to `/workspace/login/cas`, should both share one service ID indiscriminately?  
**Answer:** Never drop binding. Maintain separate old/new registered services and flows per the migration plan, validating each ticket with the identity that issued it.

**Question 12.** When serving multiple tenants/hosts in one app, can `service` be taken from any incoming HTTP `Host`?  
**Answer:** No. You need a tenant -> approved public callback mapping, trusted request context, and cross-tenant tests.

**Question 13.** Is CAS Server `/serviceValidate` called by the browser or the SP backend?  
**Answer:** By the backend CAS client/service over HTTPS server-to-server; the browser carries the ST only via frontchannel redirect.

**Question 14.** Can an ST that failed validation due to wrong-service be "rescued" by extending its TTL?  
**Answer:** No. TTL and service identity are separate checks; the ST is already consumed, and extending TTL does not fix a mismatch.

## 18. Official References

- [Apereo CAS — CAS Protocol Specification](https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html): `service` on `/login` and `/serviceValidate`, `INVALID_SERVICE`/`INVALID_TICKET`, single-use ST, and service binding.
- [Apereo CAS — Ticket Validation](https://apereo.github.io/cas/development/authentication/CAS-Protocol-TicketValidation.html): service identifier matching and extensions; note security impact when customizing.
- [Apereo CAS — Configuring Service Matching Strategy](https://apereo.github.io/cas/development/services/Configuring-Service-Matching-Strategy.html): full regex/literal matching in the service registry, distinct from ticket binding.
- [Apereo CAS — Service Management](https://apereo.github.io/cas/development/services/): registered services and URL governance.
- [Spring Security — CAS Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html): `ServiceProperties`, `CasAuthenticationEntryPoint`, `CasAuthenticationFilter`, `CasAuthenticationProvider`, `TicketValidator`.
- [Spring Security 6.2.6 — CasAuthenticationFilter API](https://docs.spring.io/spring-security/site/docs/6.2.6/api/org/springframework/security/cas/web/CasAuthenticationFilter.html): default `filterProcessesUrl` `/login/cas` and `ServiceProperties.getService()` during ticket validation.
- [Spring Security — ServiceProperties API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/ServiceProperties.html): public service URL and options.
- [Spring Framework — ForwardedHeaderFilter](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html): handling `Forwarded`/`X-Forwarded-*` and trust boundary warnings; `removeOnly` mode.
- [Spring Boot 3.0 — Running Behind a Front-end Proxy Server](https://docs.spring.io/spring-boot/docs/3.0.x/reference/html/howto.html): `server.forward-headers-strategy`, `FRAMEWORK`/`NATIVE`, and proxy HTTPS details.
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/): forwarded strategy settings.
- [OWASP Unvalidated Redirects and Forwards Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.html): host/redirect allowlists.
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): cookie and session security.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): credentials in logs and audit events.

**Takeaway:** **CAS does not validate an ST against a pod name or internal upstream URL**. The ST is bound to the **service identity** CAS used when issuing the ticket; therefore `ServiceProperties.service`, CAS login `service`, CAS validation `service`, and the CAS registered-service contract must all agree on the **public callback URL**. A reverse proxy may change the internal scheme, host, port, or path without altering this identifier. Fix mismatches in public URL config, ingress routing, and trusted forwarded headers—**never weaken ticket-to-service binding, never retry a consumed ticket, and never trust client-supplied `Host`/`Forwarded` headers**.