# Trust Forwarded or X-Forwarded-* Only from Controlled Proxies

> **Module:** Spring Security – federation. **Knowledge group:** Deployment and Operations. **This Knowledge README** guides the design of trust boundaries for HTTP forwarding headers when a Spring Security application sits behind a reverse proxy, ingress, load balancer, or CDN. The focus is on **using only `Forwarded` / `X-Forwarded-*` created or sanitized by a controlled proxy**, never treating browser-asserted headers as proof of client IP, scheme, host, port, or path. These effects are especially critical for OAuth2/OIDC `redirect_uri`, SAML2 ACS/Destination/Recipient, CAS redirects, session cookies, HTTPS security, tenant routing, and auditing.

## 1. Core Statement

**HTTP Forwarded headers are routing metadata, not authenticated information.** Any client can send:
- `Forwarded: for=...;proto=...;host=...`.
- `X-Forwarded-For: ...`.
- `X-Forwarded-Proto: ...`.
- `X-Forwarded-Host: ...`.
- `X-Forwarded-Port: ...`.
- `X-Forwarded-Prefix: ...`.

An application cannot infer that a header was produced by a trusted proxy merely because it exists. **Trust only data that has crossed a trusted ingress boundary, had external input stripped/overwritten, and was delivered to the backend over a controlled channel.**

When a reverse proxy has validated and normalized these fields, they help Spring learn the true external public URL. If the proxy forwards raw client headers to Spring, an attacker can make the application believe the wrong address, scheme, or host.

### 1.1. Concise Deployment Rules

1. **Block direct access** from the Internet to the Spring backend port; only identified proxies may connect.
2. **At the edge of trust**, strip every incoming `Forwarded` and `X-Forwarded-*` header before constructing a fresh header set.
3. **Only proxies controlled by the organization may generate public origin values**, based on verified TLS/virtual host, never copying client-asserted values.
4. If multiple proxies exist, define **which hops are trusted** and process the address chain using proper trust semantics—never trust the first element blindly.
5. Enable the corresponding `server.forward-headers-strategy` in Spring Boot only when the network boundary and sanitization are **already guaranteed**.
6. Public scheme/host/port/prefix used to construct URLs must pass an **allowlist/canonical origin policy**, especially for federation callback URLs.
7. Distinguish **accepting forwarded data** from **accepting credentials/authenticated identity**; these headers never grant `ROLE_ADMIN`, select an unapproved IdP, or verify a user.

## 2. Why Is Spring Security Federation Especially Sensitive?

A common topology:

~~~text
Browser
   |
   | HTTPS https://login.example.org/saml2/authenticate/staff
   v
Reverse Proxy / WAF / Ingress / LB
   | terminates external TLS
   | connects to app via private HTTP or mTLS
   | rewrites scheme, host, port, client address
   v
Spring Boot on 10.23.0.21:8080
   |
   +-- OAuth2Login redirect_uri generation
   +-- SAML2 SP entityID / ACS URLs / metadata
   +-- Login redirect / RequestCache / session cookies
   +-- Client IP for audit and security decisions
~~~

Without trusted forwarding, the application only sees:
~~~text
request.getScheme()     = "http"
request.getServerName() = "10.23.0.21"
request.getServerPort() = 8080
request.getRemoteAddr() = "10.23.0.8"  (proxy)
~~~

Meanwhile, the address the user uses is `https://login.example.org`. When the proxy supplies proper metadata:
~~~http
X-Forwarded-Proto: https
X-Forwarded-Host: login.example.org
X-Forwarded-Port: 443
X-Forwarded-For: 198.51.100.77
~~~

Spring can derive the external origin. **However, if those headers are sent by the browser and the proxy fails to strip/overwrite them**, the same fields may be forged. Origin correctness directly affects OAuth2 redirect URIs, the SAML Assertion Consumer Service, cookies, and redirect destinations.

### 2.1. Two Opposite Failure Modes

**Not trusting forwarding even when the proxy normalizes properly:** Spring generates callbacks like `http://10.23.0.21:8080/...`, the IdP rejects `redirect_uri`, SAML Recipient/Destination mismatches occur, or cookies misbehave.

**Trusting forwarding from an uncontrolled source:** Spring constructs callbacks/redirects to an attacker-chosen host, logs fake client IPs, selects the wrong trust tenant, bypasses IP-based throttling, or suffers Host header poisoning.

The solution is not unconditionally enabling forwarded headers. Solve the **trust boundary first**, then solve **URL correctness**.

## 3. Explaining Each Header

| Header | Information intended to forward | Risk when modified by client |
|---|---|---|
| `Forwarded` (RFC 7239) | `for`, `by`, `host`, `proto` per hop | Spoofing client IP, host, and scheme; parser differences |
| `X-Forwarded-For` | List of client/proxy IP addresses | Bypassing IP allowlist/rate limits, wrong audit |
| `X-Forwarded-Proto` | External scheme `https` or `http` | Redirect URI/cookie/scheme confusion |
| `X-Forwarded-Host` | Public host accessed by the user | Host poisoning, open redirect, IdP/tenant mix-up |
| `X-Forwarded-Port` | Public port | Callback URL/port mismatch |
| `X-Forwarded-Prefix` | Public path prefix stripped/rewritten by proxy | Wrong context path, callback, links, route confusion |
| `X-Forwarded-Ssl` | Variant indicating edge TLS | Inconsistent scheme inference |
| `X-Real-IP` | De-facto client IP from proxy | Spoofing if not normalized |
| `Host` | HTTP authority requested by client | Also requires virtual-host validation, not just forwarded host |

`X-Forwarded-*` is a widespread convention, not standardized by RFC 7239 as a suite with uniform semantics. `Forwarded` has a formal grammar, yet **the RFC itself does not authenticate values**; RFC 7239 §8.1 warns about header modification across hops.

### 3.1. RFC 7239 Standard Forwarded

Example:
~~~http
Forwarded: for=198.51.100.77;proto=https;host=login.example.org
~~~

Multiple hops can appear:
~~~http
Forwarded: for=198.51.100.77;proto=https;host=login.example.org, for=10.23.0.8;proto=http;host=app.internal
~~~

The `for` field can contain bracketed IPv6 and quoted strings, as well as `unknown`/obfuscated identifiers per the RFC. **Never write a naive split-based parser and use it to authenticate client IPs.** The Java examples later in this article are trust-policy illustration models, not production RFC 7239 parsers.

### 3.2. List-Form X-Forwarded-For

~~~http
X-Forwarded-For: 192.0.2.99, 198.51.100.77
~~~

The meaning of the list depends on **proxy append rules and sanitization points**. If a client can send `192.0.2.99` and the proxy merely appends the real IP `198.51.100.77`, **the first element can be completely forged**.

To determine the endpoint address for audit/IP policies, **walk backward from the trusted socket peer toward the client until the first address outside trusted proxies**, after proper parsing and handling IPv4/IPv6/duplicate headers. This does not fix topologies where an untrusted proxy can forge the entire chain; the trust set and sanitization remain decisive.

### 3.3. X-Forwarded-Prefix Needs Its Own Policy

When the public URL is `https://login.example.org/portal` while the backend serves `/`, the proxy may send `X-Forwarded-Prefix: /portal`. If the client can control the prefix, logout paths, SAML ACS, or OAuth callbacks can be shifted wrongly.

In recent Spring Framework versions, choosing between `Forwarded` vs `X-Forwarded-*` and permitting prefixes can be configured independently. **Check API/behavior for your exact version** rather than assuming every constructor handles all headers identically.

## 4. Who Is a Trusted Proxy?

**"Trusted proxy" does not merely mean a private IP.** At minimum you need:
- A proxy you administer or one covered by an explicit trust contract.
- Connections to the backend allowed only from that proxy or exact IPs/CIDRs.
- Network isolation: firewall/security groups/Kubernetes NetworkPolicy/Service firewall.
- Preferably mTLS or workload identity authentication on the proxy→backend path when required by the threat model.
- Edge stripping/overwriting of external request headers.
- Multi-hop paths with no bypass around the sanitizing edge.
- Host/route/tenant validated by the proxy before forwarding.
- Release/change control whenever adding a new LB/ingress.

**Do not treat every 10.0.0.0/8 IP as a trusted proxy** merely because it is RFC 1918. Within a VPC, other workloads share the same private IP space. Trust only addresses actually belonging to the protected gateway/ingress.

### 4.1. Transport Peer Differs from Forwarded Client IP

- `socket peer`: the actual IP of the connection to the backend; originates from the TCP/transport layer, not `X-Forwarded-For`.
- `effective client IP`: the client address derived from trusted proxies and the chain.
- `unverified header value`: a string asserted by the HTTP request; untrusted until verified.

A safe control layer should determine **whether the peer is a trusted proxy before interpreting forwarded data**. In a stack where a filter/valve has already rewritten `getRemoteAddr()`, that value may be the **effective IP**, no longer the raw transport peer; therefore, do not build an allowlist on `getRemoteAddr()` after such a filter thinking you are authenticating the direct proxy.

### 4.2. Blocking Direct Access Is a Baseline Requirement

If Spring's port `8080` is reachable from the Internet or from arbitrary pods:
~~~text
Attacker -> Spring:8080
Header: X-Forwarded-Host: attacker.invalid
Header: X-Forwarded-Proto: https
~~~

and Spring uses `server.forward-headers-strategy: framework`, the framework may process attacker-asserted metadata. **A framework filter is no substitute for a firewall.** Constrain the traffic path first; if the app needs direct admin/health traffic, use a separate network endpoint/route that does not process forwarded headers or applies a specific policy.

## 5. Edge of Trust: Strip Then Reconstruct

Correct pattern:

~~~text
Untrusted browser headers
         |
         v
[Public edge proxy]
  - Reject invalid/unknown public Host
  - Strip ALL incoming Forwarded and X-Forwarded-*
  - Reconstruct allowed public origin from trusted listener/vhost
  - Set real observed client peer, not user-supplied values
  - Forward only to private backend
         |
         v
[Spring app]
  - Accept only this proxy path
  - Apply exactly one configured forwarded-header strategy
  - Validate public scheme/host/port/prefix against allowlist
~~~

**Important:** You must strip **both** standard `Forwarded` **and** the `X-Forwarded-*` family, even if the application reads only one family. Other libraries, gateways, or downstream services may prefer the other family. Overwriting only `X-Forwarded-Proto` while leaving incoming `Forwarded: host=attacker.invalid` intact still leaves a host-poisoning vector.

### 5.1. Multiple Reverse Proxies

With CDN → edge ingress → internal gateway → Spring:
1. Identify the first point that genuinely trusts the preceding source.
2. The edge strips incoming client headers.
3. The edge creates trusted public host/proto/port and the observed client IP.
4. The internal gateway accepts traffic **only** from the authenticated edge.
5. The internal gateway preserves/normalizes the public origin per **contract**; do not accidentally replace it with the internal HTTP scheme.
6. The backend accepts only the internal gateway; every hop along the chain has clear trust/policy.
7. When a multi-hop IP chain is needed, configure the proxy list using right-to-left trusted-hop logic for the specific product/library.

**Do not apply a one-size-fits-all formula across topologies.** If NGINX sits behind a TLS-terminating LB, `$scheme` at NGINX may be `http`, not public `https`; never blindly set `X-Forwarded-Proto: $scheme`. The public HTTPS value must be confirmed by the trusted TLS-terminating proxy or fixed via canonical origin configuration.

### 5.2. Do Not Assume "Inside Kubernetes Means Automatically Safe"

Kubernetes Services, pod CIDRs, or node private IPs do not prevent another pod from calling the backend. Enforce ingress paths and NetworkPolicies/security groups. If isolation cannot be proven, use `NONE` or `removeOnly` and configure static public external base URLs where needed instead of trusting HTTP headers.

## 6. NGINX Edge: Example of Stripping and Resetting Forwarding

Example **solely for a topology where NGINX directly terminates public HTTPS on `login.example.org` and proxies to a private Spring backend**. This NGINX snippet is only part of a real configuration—add TLS policies, a default server, and firewall rules, and verify against your NGINX version.

~~~nginx
server {
    listen 443 ssl;
    server_name login.example.org;

    ssl_certificate     /etc/nginx/tls/login.example.org.crt;
    ssl_certificate_key /etc/nginx/tls/login.example.org.key;

    location / {
        proxy_pass http://10.23.0.21:8080;

        # Exact approved public authority
        proxy_set_header Host login.example.org;

        # Drop client's standardized Forwarded header
        proxy_set_header Forwarded "";

        # Reconstruct allowed X-Forwarded metadata
        proxy_set_header X-Forwarded-Host login.example.org;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Port 443;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Real-IP $remote_addr;

        # No public prefix in this topology
        proxy_set_header X-Forwarded-Prefix "";
        proxy_set_header X-Forwarded-Ssl "";
    }
}
~~~

Explanation:
- `server_name` and default-server routing must ensure only approved public hostnames reach the application. Unknown Host/SNI must be rejected, never routed by default to any tenant.
- `proxy_set_header Forwarded ""` tells NGINX not to forward this header; if another gateway supports proprietary forwarding variants, strip those at the edge too.
- `Host` and `X-Forwarded-Host` are set to **a fixed canonical domain**, rather than raw `$http_host` for auth-sensitive endpoints.
- `X-Forwarded-Proto https` is accurate because **NGINX itself is the public TLS terminator** in this example topology.
- `X-Forwarded-For $remote_addr` is safe only when `$remote_addr` is the observed client peer at the trusted edge. If NGINX sits behind an LB/CDN, configure trusted real-IP recovery or a trust contract at the LB.
- Never use `$proxy_add_x_forwarded_for` at a public edge if you intend to discard client-supplied XFF, because that variable **appends to the incoming header** rather than overwriting it.
- `ssl_certificate_key` in NGINX is the gateway's TLS private key, **not** the IdP SAML signing key.
- Proxying over a private network alone does not mean the backend is safe if clients/pods still have a direct path.

### 6.1. Headers That Must Be Reviewed Together

In real deployments, review all of:
`Forwarded`, `X-Forwarded-For`, `X-Forwarded-Host`, `X-Forwarded-Proto`, `X-Forwarded-Port`, `X-Forwarded-Prefix`, `X-Forwarded-Ssl`, `X-Real-IP`, and any vendor-specific alternatives the stack might read.

Some setups use `True-Client-IP` or `CF-Connecting-IP` from a CDN. **Only trust** those headers from verified CDN addresses/connections, never when requests arrive directly from the public Internet.

### 6.2. Be Careful with the Host Header

Using:
~~~nginx
proxy_set_header Host $http_host;
proxy_set_header X-Forwarded-Host $http_host;
~~~

in a proxy that does not validate public hosts is a **dangerous choice** for SSO. HTTP `Host` is client-supplied data and may include ports, unicode/punycode, or an attacker's domain. Use dynamic hosts only when virtual hosts/tenant mappings are explicitly allowlisted and normalized; for fixed federation registrations, setting an explicit canonical host is safer.

### 6.3. Do Not Strip Headers at the Wrong Point

If the edge proxy already stripped and reconstructed headers, an internal gateway must not wipe the public info and set `X-Forwarded-Proto: http` for the backend hop. Multi-hop configs need a contract:
- Which hop owns the public scheme/host.
- Which hop owns client IP trust.
- Which hop appends to the `for` chain.
- Which hop drops alternate headers to prevent conflicts.
- The final hop delivers a stable origin to Spring.

For auditability, document this explicitly in the architecture rather than combining defaults from multiple ingress controllers unchecked.

## 7. Spring Boot: NONE, NATIVE, FRAMEWORK

Spring Boot supports the property:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Key values (enum names may be written lowercase in YAML):
- **NONE:** does not infer request origin from `X-Forwarded-*` via Boot's built-in support; suitable when the backend is not behind a trusted proxy or uses static canonical external URLs.
- **NATIVE:** uses the underlying web container's native capability, such as Tomcat `RemoteIpValve`. Supported headers and trust logic depend on container/version.
- **FRAMEWORK:** uses Spring Framework `ForwardedHeaderFilter` for Servlet or `ForwardedHeaderTransformer` for reactive/WebFlux, depending on version.

**None of these values turns an untrusted header into a trusted one.** `FRAMEWORK` does not whitelist remote peers by CIDR by default; proxy sanitization and network boundaries are always required. With `NATIVE`, inspect the container's exact trust policy rather than relying on broad defaults.

### 7.1. When to Use NONE?

- The app receives traffic directly with no controlled proxy.
- Host, scheme, and port for callbacks come from **static/approved** public base URL config rather than forwarded metadata.
- You want to `removeOnly` all forwarded data before business handlers read it.
- You are unsure the trust boundary is sealed and choose to fail closed while fixing infrastructure.

Confirm other libraries or custom filters do not still read raw forwarding headers directly. `NONE` only controls the Boot-managed mechanism; it does not automatically strip every header from the HTTP request across all code paths.

### 7.2. When to Use FRAMEWORK?

- An edge proxy already strips/normalizes all forwarded headers.
- Spring MVC needs the external scheme/host/prefix to generate absolute redirects/links.
- You have verified the exact constructor/behavior for your Spring Framework version.
- No overlapping filters/valves are configured that would cause double rewriting.

**Do not enable FRAMEWORK merely to fix a `redirect_uri` error while the backend port remains publicly reachable.** Fix the topology first.

### 7.3. When to Use NATIVE?

- You choose native forwarding support in Tomcat/Jetty/Undertow.
- The container supports trusted proxies and appropriate header parsing.
- Operations can verify exact real socket peers and CIDRs.
- You want client IP/remote address handled at the container before the application.

Do not assume NATIVE handles everything identically to FRAMEWORK, especially regarding prefix/path handling and RFC `Forwarded`. Check container docs and test actual URLs at runtime.

### 7.4. Avoid Processing Twice

If Boot already attaches `ForwardedHeaderFilter` under `framework`, do not manually register another `ForwardedHeaderFilter` that re-consumes headers without understanding ordering. Similarly, do not combine Tomcat `RemoteIpValve` rewriting with a filter that re-parses raw headers, producing inconsistent origin/peer values. Choose **one clear pipeline ownership** and test it.

## 8. ForwardedHeaderFilter and removeOnly Mode

Per Spring Framework, `ForwardedHeaderFilter`:
- Processes `Forwarded` or the `X-Forwarded-*` family depending on configuration/version.
- Wraps request/response so getters for scheme, host, port, remote address, and redirects reflect the public origin.
- Removes forwarded headers from the wrapped request so downstream code does not reinterpret them.
- Must be ordered properly, before filters/components that build request URLs.
- Has a `setRemoveOnly(true)` mode to **only remove headers without using them**.

Conceptual example (not a full bean):
~~~java
// Spring Framework, API/constructor depends on major release:
ForwardedHeaderFilter filter = obtainFrameworkFilterForVersion();
filter.setRemoveOnly(true);
// Register early, so downstream code never consumes untrusted
// Forwarded / X-Forwarded-* values.
~~~

`obtainFrameworkFilterForVersion()` is a placeholder notation representing project registration, **not a Spring method**. In real code, use the constructor/registration API matching your Spring Framework release: some versions have a no-arg constructor, while newer versions offer constructors selecting standard `Forwarded` vs `X-Forwarded`. This snippet is **not an independently compilable class**.

**When `removeOnly=true`, Spring does not use forwarded public scheme/host**. If the app still needs external SSO callbacks, configure the canonical public origin reliably in registration/config, or deploy a proper ingress proxy and re-enable trusted support rather than disabling required functionality.

### 8.1. Filter Ordering Matters

If a filter builds an OAuth2 authorization request/callback URL before the forwarded wrapper is applied, the URL may pick up the internal origin. Spring docs require `ForwardedHeaderFilter` ahead of request-context consumers. When registering manually via `FilterRegistrationBean`, verify `REQUEST`, `ASYNC`, and `ERROR` dispatcher types per framework guidance and ordering relative to `SecurityFilterChain`.

**Do not use a custom filter to "verify trusted peer" after Tomcat/Spring has already rewritten `getRemoteAddr()`**, because the raw peer may already have been replaced. Trust must be enforced at the networking/container stage that knows the true socket peer.

## 9. Tomcat RemoteIpValve and Trusted Proxy Rules

In Servlet Tomcat, `RemoteIpValve` can process:
- `remoteIpHeader`, typically `x-forwarded-for`.
- `protocolHeader`, typically `x-forwarded-proto`.
- `internalProxies` and `trustedProxies` to decide which chain entries are trusted.
- Host/port fields depending on version/valve properties.

**Warning:** Tomcat defaults in some releases trust fairly broad private/loopback ranges as internal proxies. Never assume every pod/host in RFC 1918 is your proxy. **Narrow the CIDR/regex** to your controlled ingress addresses.

A Spring Boot reference configuration for a Tomcat runtime supporting these property names:

~~~yaml
server:
  forward-headers-strategy: native
  tomcat:
    remoteip:
      remote-ip-header: x-forwarded-for
      protocol-header: x-forwarded-proto
      internal-proxies: '10\.23\.0\.(8|9)'
~~~

This is an **example for two proxy IPs 10.23.0.8 and .9** using a matcher pattern; verify property binding and regex/CIDR syntax for your exact Tomcat + Spring Boot versions. Also configure host/port handling or canonical public origin per deployment requirements. In some releases, `server.tomcat.redirect-context-root: false` helps avoid context-root redirects before `X-Forwarded-Proto` is handled; check version docs.

### 9.1. internalProxies vs trustedProxies

Per Tomcat docs, `internalProxies` identifies proxies considered internal and omitted from certain proxy-chain summaries; `trustedProxies` has distinct semantics recorded in `proxiesHeader`. Defaults and formats vary by Tomcat version (regex/CIDR). Never write `.*` or `0.0.0.0/0` to "mark every proxy as trusted."

### 9.2. Risk of App-Side Rewritten remoteAddr

A Tomcat valve can make `request.getRemoteAddr()` reflect the client IP inferred from XFF. Logging must distinguish this "effective IP" from the direct TCP peer. If you then use that rewritten value to check whether a request came from a trusted proxy, the result will be wrong. The fix is network restriction, container trust handling, and telemetry that distinguishes sources.

## 10. WebFlux/Reactive Differs from Servlet

Spring WebFlux applications use `ForwardedHeaderTransformer` instead of Servlet `ForwardedHeaderFilter`. Spring Boot `server.forward-headers-strategy: framework` configures the corresponding transformer. Do not copy a `FilterRegistrationBean<ForwardedHeaderFilter>` configuration into a Reactive stack and conclude it is protected.

Similar security rules apply:
- Edge proxy sanitizes headers.
- Direct backend access is blocked.
- Consistent public origin.
- Never trust arbitrary host/proto/for.
- WebFlux security and gateways have their own routing/filters requiring integration tests.

Spring Cloud Gateway can forward/rewrite headers downstream; never assume every filter strips client-supplied values by default. Consult your exact Gateway release and declare trusted proxies/filter order at each hop.

## 11. OAuth2/OIDC: Impact on redirect_uri

Spring Security OAuth2 Login typically uses the redirect URI template:

~~~text
{baseUrl}/login/oauth2/code/{registrationId}
~~~

Public URL example:
~~~text
https://login.example.org/login/oauth2/code/staff
~~~

If Spring sees the internal backend scheme/host, it may construct:
~~~text
http://10.23.0.21:8080/login/oauth2/code/staff
~~~

The IdP will reject the redirect URI because it is not in the registered callback allowlist. Conversely, if a forged forwarded host is accepted, the application may send an untrusted `redirect_uri` in the authorization request; the exact impact depends on strict IdP redirect URI validation, yet it remains a serious trust bug.

### 11.1. Nature of Failures

| Scenario | Symptom | Cause |
|---|---|---|
| Missing `X-Forwarded-Proto` | `redirect_uri` uses internal HTTP | App unaware of public TLS |
| Missing/wrong `X-Forwarded-Host` | Redirect URI contains private hostname | Wrong host reconstruction |
| Wrong `X-Forwarded-Port` | Appends `:8080` or another port | Port mismatch |
| Forged Host from client | Callback/Location/links contain attacker host | Proxy did not sanitize |
| Forged Prefix | Path added to or stripped from callback | Context path mismatch |
| Multiple host headers | Lib/parser reads different fields | Lack of header normalization |
| Real callback correct, session lost | OAuth2 state missing/invalid | Cookie/SameSite/session/ingress issues |

**Never resolve this by disabling OAuth2 state, nonce, or IdP registered redirect URI checks.** Fix proxy trust and URL construction instead.

### 11.2. Canonical Callback as Defense in Depth

For an application with a fixed public domain, you can pin the redirect URI in ClientRegistration or config:
~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          staff:
            redirect-uri: "https://login.example.org/login/oauth2/code/staff"
~~~

This snippet is a **fragment**; full client/provider configuration is required to sign in. A fixed URI reduces host-influenced callback risk, though the app still needs trusted forwarding for general redirects and session behavior. The IdP must register the **exact URI**; never allow wildcard callbacks to arbitrary domains.

### 11.3. Issuer and Client Identity Do Not Come from Headers

OIDC ID Token `iss` must be validated against trusted provider metadata/configuration. Never accept `X-Forwarded-Host: tenant-b.example.org` and dynamically pick a different IdP or client secret unless routing is allowlisted at the trust boundary and aligns with account/tenant policy.

Even when `redirect_uri` is exact, state/PKCE/nonce/token validation and local authorization remain mandatory.

## 12. SAML2: ACS, Destination, Recipient, EntityID

With Spring Security SAML2 Login, the public request origin affects:
- SP entityID in `RelyingPartyRegistration`.
- Assertion Consumer Service location published in SP metadata.
- IdP `Response.Destination`.
- Assertion `SubjectConfirmationData.Recipient`.
- SAML `AuthnRequest.AssertionConsumerServiceURL` if used.
- SAML single logout URLs and post-login redirects.

Public ACS example:
~~~text
https://login.example.org/login/saml2/sso/staff
~~~

Actual backend:
~~~text
http://10.23.0.21:8080/login/saml2/sso/staff
~~~

If the server builds metadata from the internal origin, the IdP may post to the wrong URL or Spring will reject the response due to Recipient/Destination mismatch. If the app trusts a forged client host, SP metadata/callbacks built on an unapproved origin cause host injection or wrong relying-party selection.

### 12.1. Do Not "Fix SAML" by Disabling Validation

When SAML reports:
- Destination mismatch.
- Recipient mismatch.
- ACS URL invalid.
- SP entityID/audience mismatch.

check the external scheme/host/port/prefix and metadata/config of trusted proxies first. **Never disable SAML signature, audience, Destination, Recipient, or InResponseTo validation.** Those checks protect the SP from accepting assertions not meant for it.

### 12.2. RelyingPartyRegistration Should Use Explicit Public URLs

For environments with a fixed public hostname, configure `entityId` and `assertionConsumerServiceLocation` to approved public HTTPS URLs rather than relying solely on the request Host. Spring APIs/versions may support `{baseUrl}` placeholders, but ensure `baseUrl` derives from a trusted proxy or canonical public config.

**IdP metadata** configuration must also specify the correct public IdP entityID and trusted signing keys; Forwarded headers are **not** a SAML trust anchor. Never derive user identity or roles from HTTP headers.

### 12.3. Separate Trust into Two Layers

**Transport/proxy layer:** verifies public origin and the path from browser to app.

**SAML layer:** verifies XML signature, IdP issuer/signing key, Audience, Recipient, Destination, Conditions, and request correlation.

Even if the public URL is constructed properly, an unsigned SAMLResponse or wrong issuer must still be rejected. Conversely, a properly signed assertion with an ACS mismatch is rightly rejected.

## 13. CAS, Kerberos, and Other Flows

**CAS:** A CAS client's service URL typically contains the public scheme/host/path. If the app trusts a forged forwarded host, the service URL/callback and service ticket validation can miss their target. Use canonical service URLs and CAS server validation—never drop service binding just to "pass."

**Kerberos/SPNEGO:** A Kerberos HTTP service principal is typically tied to the hostname/SPN the browser accesses, such as `HTTP/login.example.org@EXAMPLE.ORG`. Reverse proxy/gateway and backend need an explicit SPNEGO topology, keytab, and hostname contract. Changing `X-Forwarded-Host` does not automatically alter the service principal and cannot make a Kerberos ticket for the wrong service/realm valid.

**Logout/OIDC front-channel callbacks:** Host/proto/prefix can affect logout redirect URIs. Always enforce an allowlist for post-logout redirects and session/cookie policies.

## 14. Session Cookies, HTTPS, and HSTS

When client→proxy uses HTTPS while proxy→app uses HTTP:
- Do not conclude the browser is insecure solely from raw internal `request.isSecure()`; trusted forwarding can convey external HTTPS.
- Even so, **`Secure` cookies should be explicitly enforced** per public HTTPS deployment rather than relying solely on scheme inference.
- Configure Domain, Path, SameSite, HttpOnly, and Secure properly; host injection can affect cookie Domain if code constructs cookies manually.
- HSTS should be set at the public HTTPS edge/domain per policy to avoid mixed-scheme redirects.
- The internal proxy→app connection must still be network-protected; for sensitive data or zero-trust networks, use TLS/mTLS to the backend.

Spring Boot example for a public HTTPS session app:
~~~yaml
server:
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
~~~

This is a fragment and does not solve every SameSite/protocol case. **Cross-site SAML HTTP-POST callbacks** may require tailored SameSite design (in some scenarios `SameSite=None; Secure`), while OAuth2 redirects and form POSTs have different constraints. Do not tweak SameSite arbitrarily merely to mask session correlation bugs; test in real browsers.

### 14.1. CSRF Cannot Be Replaced by Forwarded Headers

`Forwarded`/`X-Forwarded-Proto` are not CSRF tokens. `Origin` or `Referer` headers can also feed CSRF/cross-origin checks; verify origin against approved external origins per policy rather than letting an untrusted forwarded host "validate" a cross-site request.

When a session is lost due to cookie flags, Spring OAuth2 `state` or SAML `InResponseTo` can fail. Fix cookies/proxy trust properly instead of disabling state/CSRF checks.

## 15. IP-Based Policy, Rate Limiting, and Auditing

X-Forwarded-For is often used for:
- IP rate limiting.
- Brute-force protection.
- Fraud/abuse telemetry.
- Geolocation/risk scoring.
- Security audits and operational tracing.
- Conditional allowlists for admin endpoints.

If policy takes **the first address regardless of source**, an attacker can prepend fake IPs and evade limits. You need:
- Raw socket peer inspection to identify trusted proxies.
- Compliant chain parsing for the container/gateway.
- Exact trusted proxy CIDRs.
- Policies for malformed/duplicate/IPv6 headers.
- Treating IP-based checks as one risk-reduction layer, never a replacement for MFA, authentication, or resource authorization.
- Logging inference conditions by stage, distinguishing the observed peer from the effective client IP.

### 15.1. Limits of Using IP as a Durable Identity

NAT, VPNs, mobile networks, IPv6 privacy addresses, and CDNs cause client IPs to fluctuate. Never turn an XFF-derived IP into an immutable user identity or substitute for OIDC `iss+sub`/SAML stable subjects. Forwarded IPs serve only risk/operations per policy.

## 16. Standalone Java 17: Proxy Trust Boundary Model

This example runs standalone on JDK 17, **without Spring, NGINX, or real networking**. It models the requirement that a request may only adopt public scheme/host/for when the transport peer belongs to a trusted proxy and the gateway has **sanitized single-hop headers**.

File `TrustedForwardedDemo.java`:

~~~java
import java.util.Set;

public class TrustedForwardedDemo {

    private static final Set<String> TRUSTED_PEERS =
            Set.of("10.23.0.8");
    private static final String HOST = "login.example.org";

    record Request(
            String socketPeer,
            String forwardedProto,
            String forwardedHost,
            String forwardedFor) {
    }

    static String decide(Request r) {
        if (!TRUSTED_PEERS.contains(r.socketPeer())) {
            return "REJECT_UNTRUSTED_PEER";
        }

        if (!"https".equals(r.forwardedProto())) {
            return "REJECT_PROTO";
        }

        if (!HOST.equals(r.forwardedHost())) {
            return "REJECT_HOST";
        }

        if (r.forwardedFor() == null
                || r.forwardedFor().isBlank()
                || r.forwardedFor().contains(",")) {
            return "REJECT_UNSANITIZED_CHAIN";
        }

        return "ACCEPT:https://" + HOST;
    }

    public static void main(String[] args) {
        Request valid = new Request(
                "10.23.0.8", "https",
                "login.example.org", "198.51.100.77");

        Request direct = new Request(
                "203.0.113.9", "https",
                "login.example.org", "198.51.100.77");

        Request hostSpoof = new Request(
                "10.23.0.8", "https",
                "attacker.invalid", "198.51.100.77");

        Request protoSpoof = new Request(
                "10.23.0.8", "http",
                "login.example.org", "198.51.100.77");

        Request unsanitized = new Request(
                "10.23.0.8", "https",
                "login.example.org",
                "192.0.2.99, 198.51.100.77");

        System.out.println("trusted=" + decide(valid));
        System.out.println("direct=" + decide(direct));
        System.out.println("host-spoof=" + decide(hostSpoof));
        System.out.println("proto-spoof=" + decide(protoSpoof));
        System.out.println("unsanitized=" + decide(unsanitized));
    }
}
~~~

Commands:
~~~bash
javac TrustedForwardedDemo.java
java TrustedForwardedDemo
~~~

**Exact stdout:**
~~~text
trusted=ACCEPT:https://login.example.org
direct=REJECT_UNTRUSTED_PEER
host-spoof=REJECT_HOST
proto-spoof=REJECT_PROTO
unsanitized=REJECT_UNSANITIZED_CHAIN
~~~

**Explanation:**
- Only a trusted peer + scheme + canonical host + sanitized single client-address field is accepted.
- A direct peer, even carrying forged headers, is rejected.
- Spoofed host and proto cannot alter the callback origin.
- The demo rejects multi-hop chains because the policy intentionally supports only an edge that has sanitized to a single address.

**Strict limitation:** The `socketPeer` string in the record merely represents the **transport IP supplied by the network/container**, not a value sent by an HTTP client. Never accept a JSON record from a client and trust it. The code does not parse real IP addresses, IPv6, IPv4-mapped IPv6, RFC 7239 quoted strings, proxy hops, TLS identity, or Host normalization. **Do not use this class as a production ForwardedHeaderFilter or sole protection.** Production enforcement belongs in ingress/network/container trust and audited frameworks.

## 17. Standalone Java 17: Why Not Take the First IP in XFF

The second demo shows walking the XFF list from the **trusted direct socket peer toward the client**, rather than picking the first element. The code handles simple illustrative IPv4 strings only; **it is not a full XFF parser and does not support RFC 7239**.

File `ProxyHopDecisionDemo.java`:

~~~java
import java.util.Set;

public class ProxyHopDecisionDemo {

    static String closestUntrusted(
            String xForwardedFor,
            String socketPeer,
            Set<String> trustedProxies) {

        if (!trustedProxies.contains(socketPeer)) {
            return "REJECT_UNTRUSTED_PEER";
        }

        if (xForwardedFor == null
                || xForwardedFor.isBlank()) {
            return "REJECT_MISSING_CHAIN";
        }

        String[] hops = xForwardedFor.split(",", -1);
        for (int i = hops.length - 1; i >= 0; i--) {
            String hop = hops[i].trim();
            if (hop.isEmpty()) {
                return "REJECT_MALFORMED_CHAIN";
            }

            if (!trustedProxies.contains(hop)) {
                return hop;
            }
        }

        return "REJECT_NO_UNTRUSTED_CLIENT";
    }

    public static void main(String[] args) {
        Set<String> correctTrust = Set.of("10.23.0.8");
        Set<String> dangerouslyBroadTrust =
                Set.of("10.23.0.8", "198.51.100.77");

        System.out.println("sanitized=" +
                closestUntrusted("198.51.100.77",
                        "10.23.0.8", correctTrust));

        System.out.println("client-spoofed-left=" +
                closestUntrusted(
                        "192.0.2.99, 198.51.100.77",
                        "10.23.0.8", correctTrust));

        System.out.println("overtrusted=" +
                closestUntrusted(
                        "192.0.2.99, 198.51.100.77",
                        "10.23.0.8", dangerouslyBroadTrust));

        System.out.println("direct=" +
                closestUntrusted(
                        "198.51.100.77",
                        "203.0.113.9", correctTrust));

        System.out.println("missing=" +
                closestUntrusted("", "10.23.0.8",
                        correctTrust));
    }
}
~~~

Run:
~~~bash
javac ProxyHopDecisionDemo.java
java ProxyHopDecisionDemo
~~~

**Exact stdout:**
~~~text
sanitized=198.51.100.77
client-spoofed-left=198.51.100.77
overtrusted=192.0.2.99
direct=REJECT_UNTRUSTED_PEER
missing=REJECT_MISSING_CHAIN
~~~

In a chain where the edge appends the true address, items on the left may be client-supplied. If the trust set accurately contains only gateway 10.23.0.8, immediately preceding it is the untrusted client 198.51.100.77. If 198.51.100.77 is mistakenly treated as a trusted proxy, the parser continues to the spoofed 192.0.2.99. This is why **trusted proxy CIDRs must be exact**.

**Production caveat:** You need a hardened IP/chain parser rather than `String.split(",")`: IPv6/ports, duplicate headers, whitespace, RFC 7239 `unknown`/obfuscated values, chain length, NAT/CDN, network ACLs, multiple hops, PROXY protocol, and IP canonicalization. Rely on audited container/ingress capabilities instead of copying a demo as security code.

## 18. Servlet Test: Simulating Host/Proto in MockMvc

MockMvc can help verify URL generation and security rules, yet **sending headers directly to MockMvc does not prove the proxy sanitized them or that the backend blocked direct traffic**. A separate full-proxy integration test is mandatory.

A test-only diagnostic controller (Spring MVC fragment):

~~~java
@RestController
class PublicOriginProbeController {

    @GetMapping("/__test/origin")
    String origin(HttpServletRequest request) {
        return request.getScheme() + "://"
                + request.getServerName() + ":"
                + request.getServerPort();
    }
}
~~~

Imports required for the project:
~~~java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
~~~

This is a **Spring class fragment**, not standalone JDK 17. Under a test profile, you can build a request:
~~~java
mvc.perform(get("/__test/origin")
        .header("X-Forwarded-Proto", "https")
        .header("X-Forwarded-Host", "login.example.org")
        .header("X-Forwarded-Port", "443"));
~~~

If the test registers the right filter and policy, the response simulates the effective origin; if forwarding is not enabled, Spring may return the mock request's origin. **Do not attach a universal expected stdout to this fragment**, as output depends on MockMvc filter registration, Spring Boot strategy, and version. Never expose this route in public production, as it can reveal routing internals.

### 18.1. Integration Tests Against Real NGINX/Ingress

Mandatory tests:
- Public HTTPS request carrying **forged X-Forwarded-Host** inbound → backend still sees the canonical host.
- Public HTTPS request carrying **forged Forwarded** → backend neither reads nor prefers the attacker's header.
- Public HTTPS request carrying **forged X-Forwarded-Proto: http** → Spring still generates a public HTTPS redirect.
- Requests with duplicate/combined conflicting headers → rejected or normalized per policy, never using attacker values.
- Direct request to backend IP/port from outside the trusted network → blocked at the network layer.
- Legitimate proxy request → OAuth2 redirect URI/SAML metadata contains the exact public origin.
- Multi-hop with CDN/LB/ingress → scheme/host/client IP correct at every node.
- Reverse proxy restart/rollover → does not reopen direct backend ports.

## 19. Safe curl Smoke Tests

From a test host authorized to reach the public endpoint, inspect response headers (avoid printing cookies/tokens into tickets):

~~~bash
curl -si \
  https://login.example.org/saml2/service-provider-metadata/staff

curl -si \
  -H 'Forwarded: for=192.0.2.99;proto=http;host=attacker.invalid' \
  -H 'X-Forwarded-Host: attacker.invalid' \
  -H 'X-Forwarded-Proto: http' \
  https://login.example.org/saml2/service-provider-metadata/staff
~~~

This is **defensive testing guidance for authorized environments**, never targeting external systems. The test must confirm SP metadata entityID/ACS is **not** changed to `attacker.invalid` and the public scheme remains HTTPS; upstream may reject the headers rather than silently fixing them. Never save raw SAML assertions/cookies from `curl -si` output into public logs.

### 19.1. Checking OAuth2 Authorize Redirect

In a test environment with valid client registrations:
- Request the login initiation URL for the registration.
- Verify `Location` to the IdP contains the URL-encoded `redirect_uri` matching the canonical public callback.
- Repeat with forged Forwarded/X-Forwarded headers.
- Expect the URI to remain the approved public URI, or the request to be rejected; never containing an attacker host.
- Never treat an IdP mismatch rejection as proof the proxy is safe; stop host poisoning at the ingress/app boundary.

### 19.2. Checking SAML Metadata and Assertion Callback

Cross-check:
- SP entityID in generated metadata.
- AssertionConsumerService Location.
- IdP-configured ACS/recipient.
- Response Destination and SubjectConfirmationData Recipient.
- Reverse proxy public scheme/host/port.
- `RelyingPartyRegistration` for the right IdP/tenant.

Test SAML signatures/conditions separately: proxy header sanitization does not replace XML signature validation.

## 20. Checking Host, Port, Scheme, and Prefix Against an Allowlist

A sanitizing proxy is a prerequisite, and the application can add an **origin allowlist** enforcing:
- HTTPS scheme.
- Exact hostname from the approved set, normalized/canonicalized.
- Port 443 (or exact public port).
- Path prefix per registration/tenant.
- No userInfo, control characters, unexpected ports, or untrusted punycode/homograph hosts.
- Unknown host → reject or route to a safe default that does not perform SSO.
- Return/success/logout redirects → only to approved URLs.

**Avoid naive suffix checks**:
~~~java
// INSUFFICIENT: attacker-example.org can bypass
// a careless endsWith("example.org") check.
boolean allowed = userProvidedHost.endsWith("example.org");
~~~

Prefer an exact host allowlist or proper domain-boundary checking with a dot separator after canonicalization/IDNA per security policy. Only use multi-tenant dynamic hosts when tenant mapping and issuer trust are approved server-side.

### 20.1. Do Not Select an IdP from an Unverified Host

An app serving `staff.example.org` and `partners.example.org` may need two SAML registrations. Yet host routing must be decided by the ingress/server allowlist. If a client sends `X-Forwarded-Host: staff.example.org` on the partners entrypoint and the server selects the staff IdP trust, it can cause a tenant/IdP mix-up.

Never infer an approved realm/issuer, signing key, or `localUserId` solely from an HTTP forwarding header.

## 21. Kubernetes, Ingress, and Service Mesh

In Kubernetes:
1. Only the `Ingress Controller`/Gateway API routes Internet traffic to the service.
2. NetworkPolicy blocks unauthorized pods from reaching the backend port.
3. Load balancer/ingress config defines trusted upstream CIDRs.
4. When behind a managed load balancer/CDN, configure real-IP handling only for verified provider IP ranges.
5. Ingress must strip and regenerate Forwarded and X-Forwarded-* via product-specific configuration.
6. Service mesh sidecars can add/modify headers; verify the entire hop sequence.
7. External TLS termination means `X-Forwarded-Proto` may need to be preserved from the outer trusted hop rather than overwritten with the internal HTTP scheme.
8. `X-Forwarded-Prefix` must match the path rewrite, never caller-supplied values.
9. Ingress/SPA/callback routes must share compatible cookie/SameSite/session state.
10. Expose health/actuator only via control plane/private access unless there is a public reason.

**Never paste an ingress annotation** from another Kubernetes distribution without checking controller/version. NGINX Ingress, AWS ALB, Envoy, Traefik, and Spring Cloud Gateway have differing defaults and rules, especially around trusting upstream headers.

### 21.1. PROXY Protocol Differs from HTTP Forwarded Headers

A load balancer may send the **PROXY protocol** on the transport connection to convey the client IP. This is not an HTTP `Forwarded` header. If used, the listener/parser must be configured properly and accept PROXY protocol only from the trusted LB; never allow Internet clients to write a raw PROXY line to a public backend. Never mix raw PROXY protocol data with XFF parsing without a consistent trust chain.

## 22. Header Conflicts, Precedence, and Parser Ambiguities

Cases to reject or strictly canonicalize:

| Input | Risk | Policy |
|---|---|---|
| `Forwarded` host=A, `X-Forwarded-Host`=B | Two libraries pick two different hosts | Edge strips both, emits one canonical family |
| Two differing `X-Forwarded-Proto` lines | Merge/last-value inconsistency | Reject/normalize at ingress |
| Comma-separated list in `X-Forwarded-Host` | One lib picks first, another picks last | Reject unexpected multi-values |
| Non-numeric characters in `X-Forwarded-Port` | URI parser confusion | Validate exact public port |
| `X-Forwarded-Prefix: //evil.example` | Path/URI interpretation | Strip and allowlist prefix |
| `Forwarded: proto=http` on public HTTPS | Mixed-scheme / redirect issues | Overwrite from TLS terminator |
| `X-Forwarded-For` with attacker IP on the left | Rate-limit bypass if taking first | Trust-chain parse from raw peer |
| Wrong `Host`, valid XFH | Host route confusion | Canonical host policy |
| IPv6 in Forwarded with quoted ports | Parser ambiguity | Use an RFC-compliant parser |
| Proxy receives raw UTF-8/control chars | Header injection/response splitting | Reject at gateway/parser |

Do not invent your own precedence order across two header families; choose one contract supported by your exact framework release and ensure the proxy emits only the corresponding canonical headers.

## 23. Negative Tests Must Verify the Exact Boundary

| ID | Scenario | Expected |
|---|---|---|
| T01 | Trusted proxy + canonical https/host/port | App sees approved public origin |
| T02 | Direct external request to backend:8080 | Network deny |
| T03 | Browser sends X-Forwarded-Host attacker.invalid | Edge overwrites/rejects |
| T04 | Browser sends Forwarded host attacker.invalid | Edge strips/rejects |
| T05 | Browser sends X-Forwarded-Proto http | Effective public scheme remains https |
| T06 | Browser sends X-Forwarded-Port 8080 | Effective public port remains 443 |
| T07 | Browser sends X-Forwarded-Prefix /evil | Prefix follows approved routing |
| T08 | Browser prepends fake IP to X-Forwarded-For | Rate limit/audit ignores fake IP |
| T09 | Duplicate Forwarded/XFH conflicts | Rejected/canonicalized |
| T10 | Multi-hop proxy chain with accurate trust | Accurate effective client IP |
| T11 | Overbroad trusted CIDR | Security regression test fails |
| T12 | Unknown Host/SNI | Rejected/safe route, no cross-tenant SSO |
| T13 | OAuth2 redirect_uri after login start | Exact public HTTPS callback |
| T14 | OAuth2 callback with wrong state/nonce | Authentication rejected |
| T15 | SAML metadata SP entityID/ACS | Canonical public URLs |
| T16 | Wrong SAML Destination/Recipient | SAML response rejected |
| T17 | Wrong IdP issuer/signature despite valid headers | SAML response rejected |
| T18 | CAS service URL mismatch | Rejected/fix canonical service |
| T19 | Kerberos SPN wrong hostname | Kerberos validation fails, not fixed via XFH |
| T20 | Callback session cookie lost after TLS redirect | Fix cookie flags/network |
| T21 | SAML POST cross-site cookie behavior | Test SameSite properly |
| T22 | Internal ingress sets XFP=http itself | Regression, fix trusted hop |
| T23 | CDN sends trusted real-IP data from verified peer | IP mapping accurate |
| T24 | Untrusted pod calls backend with spoofed XFH | Network deny |
| T25 | App-generated Location under hostile Host | No attacker host |
| T26 | Post-login return URL points externally unapproved | Reject open redirect |
| T27 | Internal app uses rewritten `getRemoteAddr()` as raw peer | Detect architecture bug |
| T28 | Mixed WebFlux and Servlet deployments | Each uses proper transformer/filter |
| T29 | Spring Boot NATIVE + duplicate FRAMEWORK filter | Detect/remove double handling |
| T30 | Production config accidentally trusts staging proxy domain | Deployment guard fails |

**Tests should run in an authorized environment with real proxies and approved hosts.** MockMvc-only tests do not prove the firewall and NGINX stripped headers.

## 24. Observability and Safe Logging

Logging should distinguish:
- Internal raw transport peer at trusted ingress, if platform permits.
- Trusted proxy identity/cluster.
- Normalized external origin (low-cardinality).
- Effective client IP derived from the proxy chain.
- SSO protocol/registration ID.
- Callback validation outcome.
- Denial category: `UNTRUSTED_PROXY`, `INVALID_FORWARDED_HOST`, `FORWARDED_CONFLICT`, `BAD_EXTERNAL_SCHEME`, `SAML_RECIPIENT_MISMATCH`, `OIDC_REDIRECT_URI_MISMATCH`, `COOKIE_SESSION_LOST`.

Never log raw SAMLResponse, OIDC ID Token/access token, session cookies, Kerberos `Authorization: Negotiate`, client secrets, JWT claims, or sensitive PII. IP addresses can also constitute personal data under law/policy; retention and access controls must match.

### 24.1. Useful Metrics

The metric names below are **suggestions**, not emitted by Spring by default:
- `proxy_forwarded_header_rejected_total`.
- `proxy_trust_peer_denied_total`.
- `invalid_public_host_total`.
- `oauth2_redirect_uri_mismatch_total`.
- `saml_destination_recipient_rejected_total`.
- `session_cookie_persistence_failure_total`.
- `proxy_header_conflict_total`.
- `origin_normalization_failure_total`.

Never attach raw `Host`, full forwarded headers, client IPs, or arbitrary XFF chains as metric labels: they have high cardinality and can hold attacker-controlled data. Use approved labels such as registration, gateway ID, known environment, and failure category.

## 25. Practical Troubleshooting

| Symptom | Likely Cause | Diagnosis |
|---|---|---|
| OAuth2 IdP reports redirect_uri_mismatch | App generates internal http/host/port | Check public Origin vs effective request |
| OAuth2 callback arrives but state invalid | Session/cookie lost across nodes or hosts | Cookie flags, Secure/SameSite, session store |
| SAML Recipient mismatch | Wrong ACS scheme/host/prefix | Compare SAML data with trusted public ACS |
| SAML Destination mismatch | Proxy wrote wrong public scheme | Check XFP from the right TLS terminator |
| SP metadata contains internal IP | Forwarded strategy off/wrong or static URLs missing | Check registration and proxy |
| Location header points to attacker.invalid | Host poisoning or untrusted XFH | Strip at edge, allowlist public host |
| Cookies lack Secure | App thinks external is http or wrong cookie policy | Secure=true, external HTTPS |
| HTTPS redirect loop | HSTS/scheme mismatch | Check forwarded proto and redirect chain |
| Audit IP is always the proxy | XFF not processed with right trust | NATIVE/gateway client IP config |
| Audit IP arbitrarily changed by user | Picked first XFF from untrusted input | Sanitize/chain trust |
| CSRF fails after login | Wrong Host/Origin, cookie session, token | Origin policy/session/CSRF |
| User lands in wrong tenant | Untrusted XFH/Host-driven routing | Approved tenant hostname mapping |
| FRAMEWORK enabled yet forged XFH works | Backend reachable directly | Firewall/NetworkPolicy ingress |
| NATIVE works on node A but not B | Tomcat/container versions differ | Sync config/trust CIDRs |
| `/portal` callback missing prefix | Wrong X-Forwarded-Prefix/rewrite | Check path routing and registration |
| `Forwarded` and XFH headers conflict | Proxy did not strip the other family | Normalize at edge |
| IdP signing key error after proxy change | Possibly unrelated protocol trust | Separate key verification vs URI mismatch |
| CAS service ticket invalid | CAS service URL host/scheme mismatch | Canonical public service config |
| Kerberos fails to log in on new hostname | SPN/keytab/service principal mismatch | Check public hostname/SPN |
| WebFlux request URL wrong | Using wrong Servlet assumptions | ForwardedHeaderTransformer / gateway |
| One CDN POP breaks login | Upstream trust/proto mismatch | Compare config per edge/site |
| Adding an LB drops client IP | Hop chain not updated | Trusted proxy policy inventory |

### 25.1. Short Debugging Sequence

1. Identify the approved public URL/host/port/prefix.
2. Diagram every hop: browser → CDN/LB → ingress → service mesh → Spring.
3. Note who terminates TLS and who sets/strips forwarded headers.
4. Check whether the backend has any direct access path.
5. Check Spring Boot strategy and native valve/filter ownership.
6. Test both valid requests and requests with forged `Forwarded`/`X-Forwarded-*`.
7. Compare public callback `redirect_uri`, SAML ACS, and metadata.
8. Check session cookies, state, CSRF, and HTTP redirect chains.
9. Verify authority/tenant rules independently—never conflate proxy with IdP.
10. Add integration regression tests and a release guard.

## 26. Dangerous Anti-Patterns

1. Enabling `server.forward-headers-strategy: framework` while the backend port is public.
2. Treating every private IP in 10/8 as a trusted proxy.
3. Using raw `request.getHeader("X-Forwarded-Host")` to choose a tenant/issuer.
4. Using raw `X-Forwarded-For.split(",")[0]` for an IP allowlist.
5. Letting the proxy strip only XFH while leaving Internet `Forwarded` intact.
6. Using `$proxy_add_x_forwarded_for` at an untrusted public edge without normalizing.
7. Using raw `$http_host` to build SSO callbacks without domain validation.
8. Taking `X-Forwarded-Proto` from a downstream HTTP hop instead of the external TLS terminator.
9. Trusting both `Forwarded` and XFF/XFH when they hold conflicting values.
10. Enabling NATIVE and FRAMEWORK together without understanding ordering.
11. Treating rewritten `getRemoteAddr()` as proof of the raw socket peer.
12. Disabling OAuth2 state/nonce to work around a wrong `redirect_uri`.
13. Disabling SAML Recipient/Destination/Audience validation because of an ACS mismatch.
14. Allowing wildcard IdP redirect URIs or arbitrary success URLs.
15. Failing to restrict the backend from other K8s pods in the same cluster.
16. Trusting CDN-specific client-IP headers from requests not coming from the CDN.
17. Copying private keys/identity claims into debug logs.
18. Granting `ROLE_ADMIN` based on a client-provided origin/tenant header.
19. Assuming browser HTTPS means the backend needs no network security.
20. Skipping Host/virtual-host checks because "we already have TLS."
21. Changing cookie SameSite without testing cross-site SAML POST.
22. Mixing TLS certificates with SAML signing/decryption credentials.
23. Putting test/staging hosts into the production allowlist unchecked.
24. Turning off rate limiting when post-proxy IPs are wrong instead of fixing the trusted hop.
25. Testing only with MockMvc headers and concluding NGINX/firewalls are verified.

## 27. Deployment/QA Checklist

- [ ] Public origin, approved hosts/ports, and prefix are defined.
- [ ] All proxy/CDN/LB/ingress/service mesh hops are diagrammed and reviewed.
- [ ] Backend accepts connections only from trusted proxy identities/networks.
- [ ] Edge strips both incoming `Forwarded` and all `X-Forwarded-*` headers.
- [ ] Edge sets public proto/host/port from a trusted listener/vhost.
- [ ] Edge sets XFF from observed peer/trusted prior-hop data, not raw client values.
- [ ] Multi-hop setup defines hop ownership and right-to-left trust rules.
- [ ] Unknown Host/SNI and duplicate/conflicting headers are rejected/normalized.
- [ ] Spring Boot selects the right NONE/NATIVE/FRAMEWORK strategy for the runtime.
- [ ] Tomcat internalProxies/trustedProxies are narrowed, not trusting all RFC 1918.
- [ ] No double header parsing/rewriting with unclear ownership.
- [ ] WebFlux uses `ForwardedHeaderTransformer` properly when applicable.
- [ ] Public OIDC `redirect_uri` matches the IdP registration exact allowlist.
- [ ] SAML SP metadata ACS/entityID use the canonical HTTPS domain.
- [ ] SAML Destination/Recipient/InResponseTo checks remain intact.
- [ ] CAS service URL and Kerberos SPN topology are verified where applicable.
- [ ] Session cookie Secure/HttpOnly/Path/SameSite match the browser SSO flow.
- [ ] HSTS/TLS policy at the public edge and proxy→app transport are protected.
- [ ] CSRF/cross-origin policy never trusts an unverified Host.
- [ ] Tenant routing and local identity mapping do not rely on untrusted HTTP headers.
- [ ] Positive public redirect + full SAML/OIDC integration tests exist.
- [ ] Negative tests cover forged Forwarded, XFH, XFP, XFF, Prefix, and duplicates.
- [ ] Direct backend requests are blocked in network security tests.
- [ ] Logs distinguish raw peer/effective client IP without leaking tokens.
- [ ] Low-cardinality metrics and alerts exist for proxy header conflicts.
- [ ] Deployment docs identify owners for trust-set management and key rotation.
- [ ] Every ingress/CDN/gateway change triggers an SSO regression test.
- [ ] Authentication/authorization is never bypassed to mask header mismatches.

## 28. Review Questions

1. **Why can't X-Forwarded-Host be trusted directly?** Clients can send that value themselves.
2. **Who must strip forwarded headers from the Internet?** The proxy at the edge of the trust boundary.
3. **Is stripping only X-Forwarded-Host enough?** No; both `Forwarded` and other `X-Forwarded` variants must be handled.
4. **What is X-Forwarded-Proto used for?** It conveys the external HTTP/HTTPS scheme observed by a trusted proxy.
5. **Is X-Forwarded-For absolute proof of client IP?** No; trusted hops and sanitization are required.
6. **Why is taking the first XFF dangerous?** Clients can prepend values on the left before the proxy appends.
7. **Is a proxy using IP 10.0.0.8 automatically trustworthy?** No; it must be in the allowlist and network trust boundary.
8. **What does `server.forward-headers-strategy=NONE` mean?** Boot does not apply native/framework forwarding support via this property, though custom code still needs review.
9. **How do NATIVE and FRAMEWORK differ?** Container-native handling versus Spring Framework filter/transformer.
10. **Does ForwardedHeaderFilter determine on its own whether a header came from a trusted proxy?** No; trust starts with the proxy/network.
11. **What does `removeOnly` do?** Strips forwarded headers without using them to rewrite the request.
12. **Why avoid double handling?** It can corrupt scheme, host, port, or IP.
13. **Where should a wrong OAuth2 `redirect_uri` be fixed?** Public origin/proxy config and ClientRegistration—never by dropping state.
14. **Should the validator be turned off for a SAML Recipient mismatch?** No; fix ACS/public origin.
15. **Can a public HTTPS ACS with an HTTP backend be valid?** Yes, if TLS terminates at a trusted proxy and the backend is protected.
16. **Do Forwarded headers replace the IdP signing key or issuer?** No.
17. **Does a Kerberos SPN change automatically when XFH changes?** No.
18. **Does a CORS error prove forwarding is unsafe?** Not by itself, though origin/proxy should be checked alongside security routing.
19. **Why is cookie `Secure` important?** Browsers send the cookie only over HTTPS, preventing session leakage over HTTP.
20. **Is `SameSite=Lax` always suitable for SAML POST?** No; test browsers/cross-site callbacks and policy.
21. **Why is a Host allowlist needed even with TLS?** Host remains request metadata used to select tenants/links.
22. **When should static canonical public URLs be used?** When the app has a fixed domain or forwarding trust cannot be guaranteed.
23. **Does a private Kubernetes Service guarantee only ingress can call it?** No; NetworkPolicy/firewall is needed.
24. **Can the Java 17 demo replace Tomcat RemoteIpValve?** No; it only illustrates trust invariants.
25. **If the backend port is direct and public, is enabling FRAMEWORK safe?** No.
26. **Can a CDN client-IP header be trusted on any request?** No, only from a verified CDN peer.
27. **What should be checked to debug a login loop?** Redirect URI, public scheme/host, cookie/session, and request correlation.
28. **What must be tested after fixing a proxy?** OIDC authorize/callback, SAML metadata/ACS, Host spoofing, session, and role policies.
29. **Is `Forwarded` evidence that a user has logged in?** No.
30. **General rule?** Accept only metadata generated by a controlled proxy at a protected trust boundary before letting Spring use it.

## 29. Official References

- Spring Framework – Servlet Filters, ForwardedHeaderFilter and Security Considerations: https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html
- Spring Framework – ForwardedHeaderFilter Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/filter/ForwardedHeaderFilter.html
- Spring Boot – Embedded Web Servers, Running Behind a Front-end Proxy: https://docs.spring.io/spring-boot/how-to/webserver.html
- Spring Boot – server.forward-headers-strategy application property: https://docs.spring.io/spring-boot/appendix/application-properties/
- Spring Security – OAuth2 Login Core, default redirect URI: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html
- Spring Security – OAuth2 Authorization Requests/redirect-uri template: https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorization-grants.html
- Spring Security – SAML2 Login Overview: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security – SAML2 RelyingPartyRegistration: https://docs.spring.io/spring-security/reference/servlet/saml2/login/relying-party.html
- Apache Tomcat – RemoteIpValve configuration (Tomcat 11, check your runtime version): https://tomcat.apache.org/tomcat-11.0-doc/config/valve.html
- NGINX – proxy_set_header and $proxy_add_x_forwarded_for: https://nginx.org/en/docs/http/ngx_http_proxy_module.html
- IETF RFC 7239 – Forwarded HTTP Extension, §8 Security Considerations: https://www.rfc-editor.org/rfc/rfc7239
- OWASP – Unvalidated Redirects and Forwards: https://cheatsheetseries.owasp.org/cheatsheets/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.html
- OWASP – Cross-Site Request Forgery Prevention: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
- OWASP – Session Management: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- OWASP – HTTP Security Response Headers: https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html

**Summary:** Spring Security needs to know the public scheme, host, port, and prefix when running behind a proxy, especially to build OAuth2/OIDC `redirect_uri` and SAML2 ACS/metadata. Yet `Forwarded`/`X-Forwarded-*` are themselves **HTTP input that clients can forge**. The right implementation is **block direct backend traffic → edge strips all incoming forwarding headers → trusted proxy reconstructs the public origin from verified sources → Spring picks the right NONE/NATIVE/FRAMEWORK strategy → validate canonical origin → keep SAML/OIDC authentication, CSRF, and authorization checks intact**. Never trade security by trusting every private IP, reading the first XFF, or turning off security validators just to make login callbacks work.
