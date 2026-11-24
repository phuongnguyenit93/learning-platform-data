# Reviewing identity spoofing risks across multiple reverse proxy layers

**Module:** Spring Security – federation  
**Parent topic:** Proxy Authentication  
**Scope:** Spring Boot 3.x / Spring Security 6.x applications behind CDNs, WAFs, ingresses, authentication gateways, service meshes, and internal reverse proxies; Java 17+. Focuses on **identity spoofing** and **multi-hop trust boundaries**, distinct from general proxy tuning or broad network security.

## 1. The core problem

In many systems, the Spring application does not authenticate users with passwords/OIDC/SAML on every request. An **authentication proxy** authenticates the user and puts the identity into an HTTP header, such as **X-Verified-Subject: employee-42**. The app can then use **`RequestHeaderAuthenticationFilter`** to construct a Spring Security Authentication from that header.

This mechanism is safe **only when the header is genuinely produced by a trusted component after properly authenticating the user**, and attackers **have no path** to send arbitrary values to Spring or trick an intermediate hop into trusting an unverified header.

Architecture example:

~~~text
Internet browser / attacker
       |
       v
P0: CDN / WAF / public edge
       |
       v
P1: Login / OIDC / SAML / mTLS authentication gateway
       |
       v
P2: Kubernetes ingress / internal reverse proxy
       |
       v
Spring Boot application
       |
       v
Business authorization + database
~~~

In this architecture, a request can carry dozens of headers, yet four distinct categories must be separated:

1. **Routing/origin headers**: `Forwarded`, `X-Forwarded-For`, `X-Forwarded-Host`, `X-Forwarded-Proto`, `X-Forwarded-Port`, `X-Forwarded-Prefix`. These describe the proxy chain, IP, host, and scheme of the request.
2. **Authentication identity headers**: `X-Verified-Subject`, `X-Remote-User`, `Remote-User`, `X-Forwarded-User`, `SM_USER`, or custom gateway-emitted headers. These assert user identity, **not the `Forwarded` standard**.
3. **Authorization/role claims**: `X-Roles`, `X-Groups`, `X-Tenant`, `X-Email`, `X-Admin`, or signed identity contexts. These can directly alter permissions if the app trusts them.
4. **Transport attestations**: hop-by-hop mTLS verification, network policies, service identities, and API gateway access rules. This is the actual proof letting the app trust **who delivered the header to it**; the header itself provides zero proof.

**Primary risk:** A client pre-sends **X-Verified-Subject: administrator**. One proxy fails to strip that header and forwards it. If Spring reads the header and builds an `administrator` principal, that is an **authentication bypass** even while WAF/ingress/TLS are all active.

**Minimum rule:** **Untrusted client input must stop at the trust boundary.** The edge strips/overwrites every header capable of influencing identity or origin; the authentication gateway produces a verified assertion; internal hops forward that assertion solely over controlled channels; Spring rejects whenever provenance is insufficient.

## 2. Before auditing: define clearly who trusts whom

You cannot audit merely by listing IP addresses. Describe every hop:

| Hop | Who may send requests to it? | May it authenticate users? | Which headers may it create/modify? |
| --- | --- | --- | --- |
| Browser/client | Internet or internal devices | Untrusted from HTTP headers alone | Can send arbitrary headers, including forged ones |
| **P0 public edge** | Internet, CDN, or upstream gateway | Usually does not fully authenticate users | **Strips inbound external identity headers**; sets origin metadata per policy |
| **P1 auth gateway** | Only P0 or verified upstream | **Yes**: verifies session/OIDC/SAML/mTLS | Strips old identities; **creates new identity from trusted auth result** |
| **P2 internal ingress** | Only P1 | Should not infer users from IP | Accepts/forwards identity only by allowlist, preserving semantics and protecting transport |
| **Spring app** | Only P2 or approved mesh sidecar | Uses trusted identity or verifies signed claims itself | Never accepts raw Internet headers to log in |

Mandatory audit questions:

- Does P1 actually **authenticate**, or merely trust a header forwarded by P0?
- Does P0 strip **all variants** of identity headers, including hyphen/underscore forms, aliases, and duplicate headers?
- Can P2 accept requests from any pod other than P1? If so, can that pod forge headers?
- Does the app expose internal services, debug ports, NodePorts, LoadBalancers, localhost port-forwards, or other endpoints straight to the backend?
- Are hops authenticated **mutually** via mTLS/service identity, or only relying on private `10.x` addresses?
- Is `X-Forwarded-For` used for **rate limiting**, IP allowlists, admin bypasses, or logging only?
- Is the identity from P1 bound to the right **tenant, issuer, subject, session, and audience**?
- Does configuration treat **`X-Forwarded-User`** as a shortcut bypassing Spring Security?
- Was a new ingress or second CDN added without updating the trusted proxies list?
- When a proxy fails, does it fail open, fail closed, or skip auth to preserve availability?

**Audit deliverables** should include a hop-by-hop diagram, sanitization configs, actual network reachability paths, an inventory of identity claims/owners, allowlist/mTLS policies, integration tests, and bypass detection.

## 3. Trust boundaries and the "never promote data to authority" rule

An HTTP header is **data**. It becomes an **authoritative claim** only when the receiver is certain of:

1. **Source authenticated**: the connection genuinely came from the right authorized gateway.
2. **Source authorized**: that gateway is authorized to assert user identities, not merely act as a transport ingress.
3. **Header integrity**: clients and prior hops cannot alter values after gateway authentication.
4. **Correct binding**: the identity corresponds to the current request/tenant/audience, not borrowed from an old request or another user.
5. **Freshness/revocation**: the session or identity assertion remains valid under policy.
6. **Backend authorization**: this user is permitted to perform the requested action on the specific resource.

A source address in a private network is not automatically an authenticated source. IPs can be reused, NATed, exposed via NodePort, shared by rogue pods in the same VPC, or misrouted.

**Data flow must be unidirectional:** clients propose host, path, and credentials; the gateway verifies and **strips all client-asserted identities**; the gateway emits an identity with provenance; the app uses only the verified gateway result or a self-verified signed identity token.

## 4. Attack 1: spoofing identity headers at the outer layer

A client sends a probe request:

~~~http
GET /admin/reports HTTP/1.1
Host: portal.example.org
X-Verified-Subject: administrator
X-Forwarded-User: administrator
X-Groups: ADMINS
~~~

If P0/P1/P2 follow **"preserve header if already present"** logic, the app reads the forged username/roles and can build an Authentication.

**One single hop forgetting to strip headers breaks safety.** Some systems use multiple aliases with the same meaning: `X-Auth-User`, `X-Authenticated-User`, `X-Forwarded-User`, `X-Remote-User`, `Remote-User`, `X-User-Email`, `X-Email`, `SM_USER`. Every name affecting identity and roles must be inventoried; never block only one name while other code trusts an alias.

**Countermeasures:**

- External callers **must never be able to inject** any identity header into the app with pre-authentication authority.
- The gateway strips identity headers **before authenticating** and sets values itself **from the validated result**.
- Spring trusts **one explicit schema/issuer**; never try 5 headers in turn until a user is found.
- Never take roles from caller-supplied `X-Groups`/`X-Admin`. Load authorities from DB/LDAP/policy engine or verify signed claims with audience/issuer/expiry.
- If an identity header appears on an unauthorized path, reject and audit rather than continuing.
- Never use bare emails as global user keys across multiple IdPs/tenants; use issuer + subject and local account mapping per the identity contract.

**Lesson:** **`RequestHeaderAuthenticationFilter` does not verify whether a header is signed or comes from a trusted source.** It assumes external authentication is already complete. If a proxy emits an unverified identity, Spring Security cannot fix that mistake just because the class is named "AuthenticationFilter".

## 5. Attack 2: direct paths bypassing straight to the backend

Even with perfect sanitization at P0 and P1, the backend may have alternate paths:

~~~text
Internet -> P0 -> P1 -> P2 -> Spring   (intended path)

Attacker -> exposed NodePort -> Spring (bypass P0/P1/P2)
Developer VPN -> 10.x backend:8080    (bypass P1)
Compromised pod -> Kubernetes Service -> Spring
Public LoadBalancer -> internal ingress -> Spring
~~~

If Spring reads **`X-Verified-Subject`** without verifying provenance, direct callers can pick any user. That completely bypasses the proxy identity assertion.

**Layered defenses:**

- Backend is **not public** and is unreachable from unauthorized network segments/pods.
- Ingress/network ACLs, security groups, and Kubernetes NetworkPolicy allow the backend to accept traffic solely from the **exact P2/service identity**; verify real default-deny enforcement.
- Enable **mTLS between workloads and trusted gateways** when the security model demands it; the receiver verifies the peer's identity certificate/service account, not merely "TLS exists".
- Restrict service-to-service traffic and developer port-forwarding so arbitrary cluster pods cannot send identity headers to the backend.
- Prefer **short-lived signed identity assertions with audience** that the app verifies itself when airtight transport isolation is hard to guarantee.
- Negative tests: probe the backend across every reachable public/internal address with a fake identity header; all untrusted paths must block **before returning any business response**.

**Never conclude "it is safe because the app binds 0.0.0.0 inside a VPC".** Binding 0.0.0.0 can expose extra interfaces; VPCs and cluster networks are not identity security boundaries on their own.

## 6. Attack 3: X-Forwarded-For and forged IP chains

**`X-Forwarded-For` (XFF)** carries routing metadata, **not user authentication**. It typically holds a comma-separated list of IPs:

~~~http
X-Forwarded-For: 198.51.100.23, 10.0.0.10, 10.0.0.11
~~~

In the illustrative model:

~~~text
Browser client     198.51.100.23
P0 edge            10.0.0.10
P1 auth gateway    10.0.0.11
P2 ingress         10.0.0.12  (TCP peer of app)
~~~

If P0 fails to strip browser-supplied XFF, an attacker can send:

~~~http
X-Forwarded-For: 203.0.113.77
~~~

And if proxies only append, the app sees:

~~~http
X-Forwarded-For: 203.0.113.77, 198.51.100.23, 10.0.0.10, 10.0.0.11
~~~

**Taking the leftmost element is dangerous.** The attacker injected **203.0.113.77** to bypass rate limits, IP allowlists, or attribution logging.

### 6.1. Right-to-left IP extraction rule

Given a **verified** trusted-proxy topology, the receiver can:

1. Verify the immediate TCP peer is an **authorized** P2 using network/transport identity.
2. Walk the XFF list **from right to left** across hops known with certainty to be trusted proxies.
3. Select the **first hop not in trusted proxies** as the closest observed source outside the trust boundary.
4. Distrust any IPs **to the left** of that hop: clients or untrusted proxies could have fabricated them.
5. If the immediate peer is untrusted, **ignore all of XFF**; use the real peer for network logging or drop the connection per policy.

This is a **conceptual model**, not a production parser. Trusted CIDRs must match real topology, supporting IPv4/IPv6, NAT, IPv6 port notation, multiple header values, and hop counts. Nor can XFF output serve as proof of user identity.

**Safer when you control the edge:** P0 **resets XFF to the real `remote_addr` P0 observed**, and trusted proxies only append their own hop metadata. Attackers then cannot smuggle fake IPs at the start of the list.

### 6.2. Common vulnerabilities

- Taking **`XFF[0]`** directly to permit `/admin` if the IP looks like an office IP.
- Using XFF as the sole key for rate limiting when clients can rotate it per request.
- Trusting all private `10.0.0.0/8` IPs when untrusted workloads live in the VPC.
- Letting clients reach the origin directly and insert valid-looking XFF values themselves.
- Updating proxy fleets while forgetting to update trusted hops.
- Parsing IPv6 or repeated XFF headers differently between WAF and app, causing policy mismatches.
- Using XFF/`Forwarded` to build OIDC/SAML callback URLs without verifying host/scheme.
- Attributing identity based on an IP shared across many users behind NAT.

**IPs can assist fraud detection or rate limiting**, yet authorizing users still requires identity from a trusted authentication provider/gateway.

## 7. RFC 7239 Forwarded and the X-Forwarded-* family

RFC 7239 defines **`Forwarded`**, for example:

~~~http
Forwarded: for=198.51.100.23;proto=https;host=portal.example.org
Forwarded: for=198.51.100.23;proto=https;host=portal.example.org, for=10.0.0.10;by=10.0.0.11
~~~

- **for**: node sending the request to the proxy.
- **by**: client-facing interface of the proxy.
- **proto**: observed external scheme.
- **host**: Host header at the chosen hop.
- Pairs are semicolon-separated; multiple hops are comma-separated. Quoted values, IPv6 addresses, and proxy-specific variants can appear.

Meanwhile, the proxy ecosystem uses:

~~~http
X-Forwarded-For: 198.51.100.23, 10.0.0.10
X-Forwarded-Host: portal.example.org
X-Forwarded-Proto: https
X-Forwarded-Port: 443
X-Forwarded-Prefix: /app
~~~

**Do not equate `Forwarded` with `X-Forwarded-For`.** RFC 7239 groups parameters per hop, whereas `X-Forwarded-*` splits them across separate headers, making it hard to tell whether values came from the same hop. Proxies may support one or both and resolve precedence differently.

**Never do this:** trust RFC `Forwarded` because it has a standard name while treating `X-Forwarded-*` as less safe. **Both can be forged by clients.** RFC 7239 Security Considerations explicitly warn values may be modified by any node, including clients.

**Recommended design:**

- Specify **one canonical forwarded metadata model** in the ingress contract, avoiding guesswork across conflicting header sets.
- **P0 strips both `Forwarded` and `X-Forwarded-*` coming from outside**, not just the one currently read.
- P0 or the trusted edge regenerates host/proto/client-origin metadata from what it observed plus an allowlist.
- Subsequent trusted hops forward/append strictly per audited policy.
- Backend must use the framework/container's forwarded-header parser rather than a hand-rolled `split(",")` for real HTTP parsing.
- If the app does not need forwarded headers, **ignore or `removeOnly`** them to shrink attack surface.

## 8. Attack 4: Host/Proto/Prefix poisoning

Suppose a browser visits HTTPS:

~~~text
https://portal.example.org/login
~~~

while the Spring backend runs plain internal HTTP:

~~~text
http://app-service:8080/login
~~~

The app may need the public host/scheme to generate OIDC redirects, SAML ACS URLs, absolute links, cookie flags, or password-reset links. An attacker sends:

~~~http
X-Forwarded-Host: attacker.example
X-Forwarded-Proto: http
X-Forwarded-Prefix: /unexpected
Forwarded: proto=http;host=attacker.example
~~~

If the app trusts unsanitized headers, consequences can include:

- **Password-reset link poisoning**: recovery emails contain an attacker-controlled host.
- **SSO/OIDC `redirect_uri` poisoning** or callback URL mismatches causing login failures or redirect leaks.
- **SAML ACS/entityID URL mismatches** from wrong public URLs.
- **Open redirects/phishing** via `Location` headers built from `Host`/`Forwarded`.
- **Broken `Secure` cookies/HTTPS redirects**, especially with proxy TLS termination.
- **Tenant routing confusion** if tenants are selected solely from a client-supplied `X-Forwarded-Host`.
- **Absolute URL validation bypasses** when WAF, gateway, and app see different hosts/protos.
- **Path traversal/routing policy mismatches** if `X-Forwarded-Prefix` is processed inconsistently across hops.

**Defense:** allowlist public hostnames at edge/gateway and app. For sensitive SSO/login flows, prefer a **server-side configured external `baseUrl`** over assembling URLs from untrusted headers. When `Forwarded`/`Host` is needed, accept only values emitted by trusted proxies consistently across all hops. Spring Boot's forward-header strategy does not replace a host allowlist or real trust boundary.

## 9. Attack 5: header aliases, duplicated headers, and HTTP parsing

A request can carry the same header twice:

~~~http
X-Verified-Subject: employee-42
X-Verified-Subject: administrator
~~~

Or casing/normalization variants:

~~~http
x-verified-subject: employee-42
X-Verified_Subject: administrator
~~~

**HTTP header names are case-insensitive**, yet Nginx, Envoy, Tomcat, gateways, and security modules can handle duplicate values, underscores, commas, and invalid header bytes differently. One hop may inspect the first value while the next uses the last; one proxy blocks hyphenated names while the backend maps underscored names to the same variable.

Additionally, **HTTP request smuggling / message framing desynchronization** attacks can make P0/P1 and the backend disagree on request boundaries, causing a gateway-authenticated request to merge with another request's headers or body. An identity header allowlist alone does not solve that risk.

**Recommended controls:**

1. At the public edge, strip **all** identity-related headers, including aliases and canonical/legacy names.
2. At the authentication gateway, reject requests with **duplicate/conflicting identity headers**; after verification, emit **exactly one value** per schema.
3. Configure proxies/Servlets to reject invalid headers, underscore/hyphen ambiguities, and bad framing.
4. Never emit two competing identity schemes (e.g., `X-User` and `X-Verified-Subject`) for the app to pick from.
5. Never accept identity claims from query parameters, cookies, or request bodies as a fallback when headers are missing.
6. Harden edge/origin with HTTP parser compatibility tests, strict `Content-Length`/`Transfer-Encoding` policies, and safe upstream keep-alive/protocol-upgrade settings.
7. Never convert raw proxy headers straight into SQL strings or role enums without canonical mapping and authorization.

**Important:** `RequestHeaderAuthenticationFilter` reads the principal header and **does not guarantee detecting duplicate headers or parser ambiguities**. Those checks belong at the trust boundary/gateway and in infrastructure design.

## 10. Attack 6: a trusted proxy forwarding an untrusted proxy's identity

Multi-hop setups often suffer from the "trusted tunnel fallacy":

~~~text
Untrusted workload U
      |
      | sends X-Verified-Subject: admin
      v
P2 ingress (trusted by app)
      |
      | forwards header verbatim
      v
Spring app
~~~

Spring sees a connection from P2 with a valid mTLS cert/service identity, yet **P2 never authenticated the user**. P2 is a trusted **transport hop**, not a trusted **identity issuer**. If P2 admits traffic from U, the app is still bypassed.

**Audits must ask at every hop:**

- Who may send requests to this hop? Default deny, or wide-open namespace?
- Does this hop authenticate users, or merely forward identity metadata?
- Does this hop **strip and regenerate** identity headers, or merely preserve strings from the request?
- Does the next hop verify this hop is the **exact issuer authorized to assert identity**?
- Does any proxy reroute to another upstream, skip auth, or enable "auth optional" per path?
- Do any health/metrics/admin routes on the same backend hit the identity filter without auth?
- If P1 suffers an outage, does traffic fail open?
- When adding a new proxy, who updates mTLS policies and service-to-service allowlists?

**Separate two trust roles:** "permitted to forward bytes" **differs from** "authorized to certify Alice is the user". If only P1 performs authentication, the backend should trust identities whose provenance **from P1** is verifiable across protected hops, rather than blindly trusting any final proxy.

## 11. Defense architecture: strip → authenticate → attest → authorize

A practical design:

~~~text
Browser
  |
  | untrusted request, arbitrary headers
  v
P0 public edge
  - Allowlisted public host/scheme
  - Remove incoming Forwarded, X-Forwarded-* and identity headers
  - Reconstruct canonical routing info from observed connection
  |
  v
P1 authentication gateway
  - Validate user session/OIDC/SAML/mTLS according to policy
  - Map verified issuer+subject to a stable internal subject
  - Drop client-influenced identity again
  - Create ONE X-Verified-Subject (or signed identity assertion)
  |
  | authenticated P1 -> P2 connection (mTLS/ACL)
  v
P2 internal ingress
  - Accept only trusted P1 workload identity
  - Never overwrite trusted subject from untrusted inputs
  - Forward subject only to explicitly authorized backend
  |
  | authenticated P2 -> app connection (mTLS/ACL)
  v
Spring Security
  - Trust source only under configured boundary; preferably verify signed token
  - Pre-authentication from verified subject, not from XFF
  - Load local account and roles; tenant/resource checks
  |
  v
Business service and DB
~~~

**Defense in depth:**

- Use a **signed JWT/OIDC ID assertion** from the authentication gateway to the backend when **end-to-end** provenance proof is needed. The backend verifies signatures via trusted JWKS/certificates, **issuer, audience, expiry, not-before, key ID/rotation**, allowlisted algorithms, and relevant claims. JWTs do not stop replay without session/request/nonce binding or short TTLs/anti-replay per threat model.
- Use mTLS between each proxy hop and block all bypass paths. Still, mTLS **guarantees only the peer**, not that the peer minted the header after user auth; strip-and-overwrite contracts remain essential.
- Proxy-side SAML/OIDC identities must retain **issuer + subject**, not bare emails/usernames in multi-IdP environments.
- Every backend service must enforce independent **authorization**: an authenticated principal alone cannot read documents outside its tenant.

## 12. Public edge Nginx example: stripping client headers and setting canonical origin

**The snippet below illustrates one `location` on P0 Nginx, not a complete production Nginx config.** TLS listeners/certificates, upstream resolution, limits, service mesh, and other routes must be completed separately.

~~~nginx
server {
    listen 443 ssl;
    server_name portal.example.org;

    # ssl_certificate /etc/nginx/tls/fullchain.pem;
    # ssl_certificate_key /etc/nginx/tls/private.key;

    location / {
        # Strip Forwarded headers sent by client.
        # proxy_set_header with empty value -> not sent upstream.
        proxy_set_header Forwarded "";
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Host portal.example.org;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Port 443;
        proxy_set_header X-Forwarded-Prefix "";

        # Prevent client from self-asserting identity/roles.
        proxy_set_header X-Verified-Subject "";
        proxy_set_header X-Authenticated-User "";
        proxy_set_header X-Forwarded-User "";
        proxy_set_header X-Remote-User "";
        proxy_set_header X-Groups "";
        proxy_set_header X-Tenant "";
        proxy_set_header SM_USER "";

        proxy_set_header Host portal.example.org;
        proxy_pass http://authentication-gateway.internal:8080;
    }
}
~~~

**Configuration explanation:**

1. P0 terminates TLS for a configured hostname; with multiple virtual hosts, add a **default server reject/allowlist** so requests never fall into the wrong host.
2. `X-Forwarded-For` is **reset to the `$remote_addr` P0 actually observed**, rather than calling `$proxy_add_x_forwarded_for` on unstripped client input at the public edge.
3. RFC 7239 `Forwarded` is stripped; if downstream needs `Forwarded`, the trusted edge must **recreate** it per policy and pick **one standard**.
4. `Host`/`Proto` are pinned to approved canonical values. If a CDN sits ahead of Nginx so this is **not the first edge**, `$remote_addr` is the CDN IP; P0 must verify the CDN and extract client IP under a trusted CDN contract, **never assuming it is the browser IP**.
5. Client identity and role headers are stripped; P0 does **not** emit `X-Verified-Subject` itself because P0 does not authenticate users.
6. **Auth gateway P1** must verify the user and **recreate** a single identity header. Never merely preserve client headers or skip auth if a header is already present.
7. The P0→P1 hop in the snippet uses **internal HTTP to illustrate structure**, providing **no transport security yet**. Production must use mTLS/HTTPS or appropriate protected networks, blocking bypasses; never copy the snippet verbatim and call it secure.

**Real-world gotcha:** configuring a single Nginx `location` does not cover all ingress routes if other `location` blocks, auth bypass paths, protocol upgrades, or separate proxies exist. Audit every route and virtual host, including health/admin endpoints and alternate domains.

## 13. Authentication gateway must emit subject from verified results

P1 is where a real authentication flow runs, such as:

- OIDC Authorization Code + PKCE with a configured provider, verifying session/callback/ID Token.
- SAML Web Browser SSO with signed assertions validated for Issuer/Audience/Recipient/timestamps/response correlation.
- mTLS client certificates with clear truststores and identity mapping.
- Real Kerberos/SPNEGO validation, not merely seeing `Authorization: Negotiate`.

Pseudocode (**not copy-pasteable Nginx config**):

~~~text
handle(incomingRequest):
    reject if connection is not from an approved P0 identity
    remove all incoming identity/authorization-claim aliases
    authenticatedUser = authenticationEngine.verify(incomingRequest)
    if authenticatedUser is absent:
        return 401 or redirect to login, never synthesize a user

    stableSubject = map(verifiedIssuer, verifiedSubject, tenant)
    if mapping is unapproved or account disabled:
        deny

    forward only one canonical identity:
        X-Verified-Subject = stableSubject

    drop any other X-Role/X-User/X-Admin client input
    send request to P2 over authenticated transport
~~~

**Critical data provenance:** Verified issuer/subject must come from validated SAML/OIDC/Kerberos outcomes; never use a `user` query param, self-asserted cookie, unverified email attribute, or client IP/User-Agent as the subject.

If P1 must send roles, emit grants under a **verified, revocation-aware schema**, or have the backend load local permissions itself. In multi-IdP setups, include issuer/tenant scope in the user link key to prevent identity collisions.

### When to use a signed identity assertion?

**Strongly consider it** when:

- Multiple independent hops or administrative domains exist.
- The app can be called from multiple namespaces or a service mesh.
- You cannot guarantee P2 accepts traffic exclusively from P1.
- The backend needs proof of issuer/audience and lifetime directly.
- Operations are sensitive, needing strict auditing, revocation, and freshness.

In this setup, the **app uses Spring Security OAuth2 Resource Server/JWT validation** to verify the gateway's token (when the schema fits), rather than trusting bare usernames. Network/mTLS controls may still be needed to protect the backend. Never invent a custom `X-Signature=SHA256(username)` header; checksums are not authentication, and ad-hoc HMACs without full replay/issuer/audience policies are error-prone.

## 14. Spring Boot 3: ForwardedHeaderFilter and forward-header strategy

**Forwarded headers for URLs/IPs are not pre-authentication identities.** Spring Boot supports:

~~~yaml
server:
  forward-headers-strategy: none
~~~

Depending on Spring Boot 3.x, main modes are:

| Strategy | How it works | Security implication |
| --- | --- | --- |
| **NONE** | Ignores forwarded headers when adjusting requests | Suits apps needing no external URL generation or using a fixed canonical `baseUrl` |
| **NATIVE** | Handled by the Servlet container, e.g., Tomcat `RemoteIpValve` | Requires accurate **trusted proxy/`internal-proxies`** and header policies |
| **FRAMEWORK** | Spring Framework **`ForwardedHeaderFilter`** | Relies on forwarded headers already **sanitized** by a trusted edge; filter **does not verify proxy source** |

The following setting **fits only when edge/ingress guarantees forwarded headers are safely rewritten**:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Spring Framework's **`ForwardedHeaderFilter`** reads `Forwarded`/`X-Forwarded-*` so `request.getScheme()`, `getServerName()`, `getServerPort()`, and redirects reflect the external URL. It also strips forwarded headers after processing so downstream components do not read them directly, yet **consuming and stripping a header does not prove the original header was legitimate**.

If you want to ignore those headers and remove them from requests, Spring provides **`ForwardedHeaderFilter.setRemoveOnly(true)`**. Register the filter in the right order/scope and avoid double registration alongside Boot auto-configuration. Never enable `FRAMEWORK` while also adding another unmanaged `ForwardedHeaderFilter`.

### 14.1. Tomcat Native and trusted proxy lists

With **NATIVE** on embedded Tomcat, `RemoteIpValve` matches internal/trusted proxies; by default it may trust private ranges depending on version. Never let the trusted-proxy list exceed the networks actually allowed to send headers to the app.

**Never set `internal-proxies` to empty to trust all hosts in production.** In Kubernetes, understand pod IPs, load-balancer source IPs, SNAT, node IPs, and mesh sidecars before choosing CIDRs/regexes. If misconfigured, the app can treat an attacker-supplied `X-Forwarded-For` as the legitimate `remoteAddr`.

### 14.2. Security Headers do not solve Identity Header Spoofing

Spring Security provides header writers (HSTS, cache control, `X-Content-Type-Options`, CSP...). They protect **HTTP responses**, not **request identity headers**. An app with HSTS/CSP enabled can still suffer account takeover if it trusts a client-sent `X-Verified-Subject`.

**Section takeaway:** Forwarded-header configuration governs **request metadata**, whereas pre-authentication headers govern **user identity**; both decisions must be verified independently and anchored in trusted boundaries.

## 15. Spring Security RequestHeaderAuthenticationFilter: heavily proxy-dependent

Per Spring Security's pre-authentication docs, **`RequestHeaderAuthenticationFilter`** extracts a username from a header and **performs no external authentication itself**. Its default header name is **`SM_USER`** (SiteMinder history), though apps can configure a custom header.

Flow:

~~~text
trusted gateway:
  verifies human / machine identity
  emits X-Verified-Subject: employee-42
        |
        v
Spring Security
  RequestHeaderAuthenticationFilter:
     reads employee-42 from header
        |
        v
PreAuthenticatedAuthenticationProvider
  UserDetailsByNameServiceWrapper / UserDetailsService
     verifies local account enabled, loads authorities
        |
        v
AuthorizationFilter / method security / business policy
     checks resource/tenant/action permissions
~~~

**Vulnerability when boundaries are missing:** An attacker calls the app directly with **`X-Verified-Subject: employee-42`**, and the filter can authenticate them as `employee-42`. Therefore **the right classes, Java APIs, and role mappings are worthless if the network/auth gateway lets clients forge headers**.

**Never mix casually with `formLogin`/`BasicAuth` fallbacks** on the same endpoints when bypassing the authentication gateway violates policy. When multiple authentication mechanisms are required, isolate filter chains/routes and trust contracts clearly.

## 16. Spring Boot 3 / Security 6.x / Java 17 example: pre-auth with gateway-only headers

**Execution model:** The app must run behind a **real auth gateway**; the backend must never be directly reachable. Prior to granting access, the gateway must verify the user and overwrite `X-Verified-Subject`. This code contains **NO** logic to verify header origin independently; never run it standalone on a public backend.

### 16.1. Maven dependencies

In a `pom.xml` with a Spring Boot parent/BOM compatible with Security 6.x:

~~~xml
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
~~~

The Java classes below form an illustrative **Spring MVC Servlet** project. No Spring Security SAML2/OIDC dependencies are required for **pre-auth headers**; if the gateway issues JWTs for the app to verify itself, configure a resource server instead rather than mixing the two designs.

### 16.2. application.yml

**src/main/resources/application.yml**

~~~yaml
server:
  forward-headers-strategy: none
  servlet:
    session:
      timeout: 20m
~~~

The example intentionally sets **`none`** so the app does not interpret forwarded origin headers itself. If production must build absolute redirects for external hosts, use a server-configured canonical URL or enable `FRAMEWORK`/`NATIVE` only after verifying edge sanitization and trusted-proxy settings.

### 16.3. Main class

**src/main/java/com/example/proxyauth/ProxyIdentityApplication.java**

~~~java
package com.example.proxyauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ProxyIdentityApplication {

    public static void main(String[] args) {
        SpringApplication.run(ProxyIdentityApplication.class, args);
    }
}
~~~

### 16.4. SecurityConfig

**src/main/java/com/example/proxyauth/ProxySecurityConfig.java**

~~~java
package com.example.proxyauth;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UserDetailsByNameServiceWrapper;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.Http403ForbiddenEntryPoint;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationProvider;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationToken;
import org.springframework.security.web.authentication.preauth.RequestHeaderAuthenticationFilter;
import org.springframework.security.web.context.NullSecurityContextRepository;

@Configuration
public class ProxySecurityConfig {

    @Bean
    UserDetailsService approvedUsers() {
        // Demo only. Production needs database/IdP
        // identity-link mapping + tenant/account state.
        return username -> {
            if (!"employee-42".equals(username)) {
                throw new org.springframework.security.core.userdetails
                    .UsernameNotFoundException("Unapproved identity");
            }
            return User.withUsername(username)
                .password("{noop}unused-for-proxy")
                .roles("READER")
                .build();
        };
    }

    @Bean
    PreAuthenticatedAuthenticationProvider preauthProvider(
            UserDetailsService approvedUsers) {

        UserDetailsByNameServiceWrapper<PreAuthenticatedAuthenticationToken>
            wrapper = new UserDetailsByNameServiceWrapper<>();
        wrapper.setUserDetailsService(approvedUsers);

        PreAuthenticatedAuthenticationProvider provider =
            new PreAuthenticatedAuthenticationProvider();
        provider.setPreAuthenticatedUserDetailsService(wrapper);
        return provider;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            PreAuthenticatedAuthenticationProvider provider)
            throws Exception {

        // Stateless mode in this example:
        // gateway verifies and sets header on each request.
        NullSecurityContextRepository noSession =
            new NullSecurityContextRepository();

        // Exists only inside Spring Security chain; do not
        // declare @Bean Filter and auto-register in Servlet.
        RequestHeaderAuthenticationFilter preauth =
            new RequestHeaderAuthenticationFilter();
        preauth.setPrincipalRequestHeader("X-Verified-Subject");
        preauth.setExceptionIfHeaderMissing(false);
        preauth.setAuthenticationManager(
            new ProviderManager(provider));
        preauth.setSecurityContextRepository(noSession);

        http
            .securityContext(sc -> sc
                .securityContextRepository(noSession))
            .sessionManagement(sm -> sm
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(
                    new Http403ForbiddenEntryPoint()))
            .addFilterBefore(
                preauth, UsernamePasswordAuthenticationFilter.class);

        return http.build();
    }
}
~~~

**Reading the code accurately:**

- **`RequestHeaderAuthenticationFilter`** only reads `X-Verified-Subject`. It **does not verify signatures, sessions, mTLS, or gateway identity**.
- **`PreAuthenticatedAuthenticationProvider`** loads `UserDetails` through the wrapper; `UserDetailsService` in the demo admits only **`employee-42`** with role **`ROLE_READER`**.
- **`NullSecurityContextRepository` + `STATELESS`** keeps the demo from persisting Authentication across `HttpSession`. Each request is verified by the **trusted gateway** and carries a fresh header. For stateful models, use `HttpSessionSecurityContextRepository` with dedicated logout/revocation/principal-change handling.
- **`Http403ForbiddenEntryPoint`** handles missing Authentication on selected endpoints; it cannot fix an attacker's ability to forge headers.
- Do not enable `formLogin`/`BasicAuth` or add branches reading arbitrary `X-User` headers. All endpoints in this example follow the same pre-auth model.
- **Never declare the filter as a standalone Servlet Filter bean**; attach it inside the chain only.
- Any state-changing actions driven by browser cookies must retain CSRF protection per threat model. Even though the demo uses request headers and stateless mode, **stateless does not automatically eliminate browser CSRF risk** if the gateway holds a cookie session or injects identity headers on cross-site browser requests.
- Production must enforce tenant/resource authorization rather than treating `ROLE_READER` as permission to read every object.

### 16.5. Controller

**src/main/java/com/example/proxyauth/IdentityController.java**

~~~java
package com.example.proxyauth;

import java.security.Principal;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityController {

    @GetMapping("/me")
    public Map<String, String> me(Principal principal) {
        return Map.of(
            "subject", principal.getName(),
            "source", "trusted-gateway-preauth-demo");
    }
}
~~~

### 16.6. Proper execution steps

In a Java 17+ project with Maven:

~~~bash
mvn spring-boot:run
~~~

**This is a pre-auth demo, not end-to-end gateway authentication.** If a developer calls `http://localhost:8080` directly with `X-Verified-Subject: employee-42`, the app **will accept the spoof** because the code intentionally assumes upstream authenticated. Use that as a **negative/security-education test**; never deploy a public backend with this setup.

In a real integrated environment:

1. Backend accepts connections solely from the authorized auth gateway/ingress; verify ACLs/mTLS.
2. Gateway strips all inbound identity headers.
3. Gateway authenticates real users and emits `X-Verified-Subject` from a verified issuer+subject mapping.
4. Send `GET /me` through the **public gateway** and verify the right subject.
5. Attempt to send fake `X-Verified-Subject: administrator` from the browser through the gateway; the gateway must overwrite/drop it so the app never sees `administrator`.
6. Attempt to connect straight to the backend with a fake identity: must be blocked by network/transport policy before reaching the app.
7. Modify/revoke user privileges in the DB; new requests must be denied or reflect updated policies within SLA.
8. Test host/proto/header poisoning, duplicate headers, multi-tenancy, and request tracing.

**There is no fixed "SSO succeeded" stdout**, because the auth gateway and real user identities depend on the environment. `/me` returns JSON only after pre-auth succeeds per contract.

## 17. Standalone Java 17 demo: trusted-hops and identity-boundary model

The following program runs **standalone on JDK 17** without Spring, Nginx, or Kubernetes. It illustrates selecting the **first untrusted hop from right to left** in an `X-Forwarded-For` chain and enforcing a policy that accepts an identity only with a **trusted immediate peer and authenticated transport**.

This is a **logic simulation**, not a production IP/CIDR/IPv6/HTTP-header parser, and the mTLS boolean in the demo represents **simulated data from trusted infrastructure**, not an HTTP header an attacker could send.

**File: ProxyTrustBoundaryDemo.java**

~~~java
import java.util.List;
import java.util.Set;

public final class ProxyTrustBoundaryDemo {

    private static final Set<String> TRUSTED_PROXIES =
        Set.of("10.0.0.10", "10.0.0.11", "10.0.0.12");

    enum Decision {
        ELIGIBLE_FOR_ACCOUNT_LOOKUP,
        REJECT_UNTRUSTED_PEER,
        REJECT_NO_AUTHENTICATED_TRANSPORT,
        REJECT_NO_IDENTITY,
        REJECT_ORIGIN_MISMATCH
    }

    record GatewayRequest(
        String tcpPeer,
        boolean peerTransportAuthenticated,
        String verifiedSubject,
        String publicHost,
        String publicScheme) { }

    static String observedClientHop(
            String tcpPeer, List<String> xForwardedFor) {

        // If TCP peer is untrusted, ignore self-asserted header.
        if (!TRUSTED_PROXIES.contains(tcpPeer)) {
            return tcpPeer;
        }

        // Trust only known hops from right to left.
        for (int i = xForwardedFor.size() - 1; i >= 0; i--) {
            String hop = xForwardedFor.get(i).trim();
            if (!TRUSTED_PROXIES.contains(hop)) {
                return hop;
            }
        }
        return "UNKNOWN";
    }

    static Decision evaluate(GatewayRequest request) {
        if (!"10.0.0.12".equals(request.tcpPeer())) {
            return Decision.REJECT_UNTRUSTED_PEER;
        }
        if (!request.peerTransportAuthenticated()) {
            return Decision.REJECT_NO_AUTHENTICATED_TRANSPORT;
        }
        if (request.verifiedSubject() == null
                || request.verifiedSubject().isBlank()) {
            return Decision.REJECT_NO_IDENTITY;
        }
        if (!"portal.example.org".equals(request.publicHost())
                || !"https".equals(request.publicScheme())) {
            return Decision.REJECT_ORIGIN_MISMATCH;
        }
        return Decision.ELIGIBLE_FOR_ACCOUNT_LOOKUP;
    }

    public static void main(String[] args) {
        List<String> cleanChain = List.of(
            "198.51.100.23", "10.0.0.10", "10.0.0.11");
        List<String> spoofedLeftmost = List.of(
            "203.0.113.77", "198.51.100.23",
            "10.0.0.10", "10.0.0.11");

        System.out.println("cleanClient=" +
            observedClientHop("10.0.0.12", cleanChain));
        System.out.println("spoofedClient=" +
            observedClientHop("10.0.0.12", spoofedLeftmost));
        System.out.println("directBypass=" +
            observedClientHop("203.0.113.77", cleanChain));

        GatewayRequest good = new GatewayRequest(
            "10.0.0.12", true,
            "employee-42", "portal.example.org", "https");
        GatewayRequest wrongPeer = new GatewayRequest(
            "203.0.113.77", true,
            "administrator", "portal.example.org", "https");
        GatewayRequest noMtls = new GatewayRequest(
            "10.0.0.12", false,
            "administrator", "portal.example.org", "https");
        GatewayRequest noSubject = new GatewayRequest(
            "10.0.0.12", true,
            null, "portal.example.org", "https");
        GatewayRequest wrongHost = new GatewayRequest(
            "10.0.0.12", true,
            "employee-42", "attacker.example", "http");

        System.out.println("good=" + evaluate(good));
        System.out.println("wrongPeer=" + evaluate(wrongPeer));
        System.out.println("noMtls=" + evaluate(noMtls));
        System.out.println("noSubject=" + evaluate(noSubject));
        System.out.println("wrongHost=" + evaluate(wrongHost));
    }
}
~~~

Run:

~~~bash
javac ProxyTrustBoundaryDemo.java
java ProxyTrustBoundaryDemo
~~~

**Exact stdout on Java 17:**

~~~text
cleanClient=198.51.100.23
spoofedClient=198.51.100.23
directBypass=203.0.113.77
good=ELIGIBLE_FOR_ACCOUNT_LOOKUP
wrongPeer=REJECT_UNTRUSTED_PEER
noMtls=REJECT_NO_AUTHENTICATED_TRANSPORT
noSubject=REJECT_NO_IDENTITY
wrongHost=REJECT_ORIGIN_MISMATCH
~~~

**Explanation:**

- Prepending **203.0.113.77** on the left does not alter the first untrusted hop when P2, P1, and P0 are genuinely trusted and the hop list is accurate.
- An **untrusted** direct TCP peer renders all its XFF values worthless for determining the trusted client IP.
- The request model qualifies for **local account lookup** only when the peer is right, transport is infrastructure-authenticated, a subject is present, and the public origin is on the allowlist.
- **`ELIGIBLE_FOR_ACCOUNT_LOOKUP` does not mean the user is authenticated**. The application must still rely on proof that the identity header was **actually generated by P1 after authentication**, rather than merely forwarded by an mTLS-authenticated P2 from an attacker, and must resolve account/permissions.

**Never copy `observedClientHop` as production protection:** it matches exact IP strings and ignores IPv6/brackets, RFC 7239, duplicate headers, CIDRs, NAT/meshes, and parser ambiguities. Use the server/ingress/framework's trusted-proxy support with proper edge reset policies.

## 18. Risk and control matrix across multiple reverse proxies

| Scenario | Trust flaw | Potential consequence | Control |
| --- | --- | --- | --- |
| Browser sends `X-Verified-Subject` | Gateway preserves client header | Wrong admin login | Strip/overwrite after auth |
| Browser sends `X-Groups`/`ROLE_ADMIN` | Backend grants roles from header | Privilege escalation | Local authorization or signed claims |
| Direct HTTP to backend | Bypasses trusted edge/auth gateway | User spoofing | ACL/NetworkPolicy/mTLS + route audit |
| Internal pod impersonates P1 | Trusts all private IPs | Lateral user spoofing across cluster | Service identity authorization |
| P0 forgets to reset XFF | App reads leftmost IP | Rate-limit/IP-allowlist bypass | Edge reset + trusted-hop policy |
| P2 appends identity from U | Transport proxy mistaken for identity issuer | Header spoof across trusted hop | P1 signed provenance; P2 ingress allowlist |
| `Forwarded` + `XFH` conflict | Gateway/app pick different precedence | Host/redirect spoofing | Canonical single-format policy |
| Fake `X-Forwarded-Proto=http` | App trusts wrong scheme | Insecure redirects/cookies | Trusted edge overwrite |
| Malicious `X-Forwarded-Host` | App builds absolute links | Password-reset/SSO redirect poisoning | Host allowlist; configured public URL |
| Malicious `X-Forwarded-Prefix` | Inconsistent prefix rewriting | Routing/policy bypass | Path allowlist and proxy normalization |
| Duplicated `X-Auth-User` | Two hops pick different values | Identity confusion | Reject duplicates; one canonical header |
| `X_Auth_User` alias | Proxy/app normalize differently | Bypasses header denylist | Strict header schema/normalization |
| HTTP request smuggling | Framing mismatch across hops | Request/identity desynchronization | HTTP parser alignment/hardening |
| P1 auth disabled for one path | Gateway fails open | Auth bypass | Fail closed; path-coverage tests |
| P1 session expired yet header cached | Stale identity | Revocation lag | No shared caching; TTL/freshness |
| Signed JWT unchecked for `aud`/`iss` | Token from another service reused | Cross-service impersonation | Verify signature, `aud`, `iss`, `exp` |
| Tenant chosen from untrusted `Host` | Mixes identities across tenants | Cross-tenant data access | Tenant source binding/allowlist |
| P2 compromised | Gateway identity abused | Impersonation | Defense in depth; signed assertion to app |
| Backend logs raw identity tokens | Secret/PII leakage | Session replay/privacy risk | Structured redacted logs |
| Service allows both header auth and Basic | Alternative auth bypasses proxy | Policy bypass | Separate routes/chains and deny defaults |

## 19. End-to-end negative testing plan

Key tests should run in an **authorized staging environment** using non-sensitive test accounts and dummy IDs. Never probe real users or production without an approved testing procedure.

1. **Public forged identity header:** send `X-Verified-Subject: administrator` from a client through P0; gateway must drop/overwrite it, never logging in as admin.
2. **Header aliases:** test `X-Authenticated-User`, `X-Forwarded-User`, `Remote-User`, `SM_USER`; none may grant privileges.
3. **Duplicate identity:** send two differing `X-Verified-Subject` headers; policy rejects or keeps solely the single gateway-minted value.
4. **Header name normalization:** test mixed casing and underscores/hyphens; none may bypass sanitization.
5. **Forged roles:** send `X-Groups: ADMINS` or `X-Admin:true`; backend never elevates roles.
6. **Direct origin bypass:** call backend/NodePort/LoadBalancer with fake headers; must fail to reach app or be rejected.
7. **Lateral pod:** call backend from an unauthorized test pod; NetworkPolicy/mTLS rejects.
8. **Untrusted P2 upstream:** a non-P1 workload sends an identity header to P2; P2 does not pass it as a valid user.
9. **XFF leftmost spoof:** send a fake admin IP at the start of XFF; trusted client-IP policy ignores it.
10. **XFF malformed/IPv6:** repeated headers, IPv6 literals, brackets, ports; parser stays consistent and fail-safe.
11. **`Forwarded` precedence:** send conflicting `Forwarded` and `X-Forwarded-*`; edge canonicalizes/rejects rather than app guessing.
12. **Host poisoning:** `X-Forwarded-Host: attacker.example`; `Location`/links/password-reset callbacks never use the attacker host.
13. **Proto poisoning:** `X-Forwarded-Proto: http`; app emits no insecure absolute redirects when the public endpoint is HTTPS.
14. **Prefix poisoning:** `X-Forwarded-Prefix:/admin`; path matching/authz cannot be bypassed.
15. **Real gateway authentication:** send a request missing an OIDC/SAML session; P1 rejects and emits no `X-Verified-Subject`.
16. **Revoked session:** revoke auth gateway session; new requests do not retain old identity beyond policy limits.
17. **User disabled locally:** gateway authenticates cleanly while local user is disabled; app grants no business access.
18. **Wrong tenant:** valid user in tenant A sends host/claims for tenant B; app denies cross-tenant access.
19. **Signed identity wrong `aud`/`iss`/`exp`:** app verifies JWT/token itself and rejects with the right reason.
20. **P1 outage:** ingress does not fail open or fabricate anonymous/admin identities.
21. **Authentication filter mismatch:** `X-Verified-Subject` exists on a verified request yet the endpoint hits the wrong Spring `SecurityFilterChain`; detect and fix chain matching.
22. **Mixed auth schemes:** attempt Basic/form/cookie fallbacks when policy permits proxy auth only; zero gateway bypasses.
23. **Cookies/CSRF:** gateways using session cookies must block unsafe cross-site state changes, even with stateless backend pre-auth.
24. **Request smuggling regression:** test h1/h2/transfer-encoding protocols in authorized setups across WAF/proxy/backend.
25. **Audit consistency:** a request traversing all hops carries a trace ID, sanitized identity provenance, and decision, logging zero raw credentials.

### Manual testing illustration

A command solely for an **owned test/staging domain**:

~~~bash
curl -i \
  -H "X-Verified-Subject: administrator" \
  -H "X-Forwarded-For: 203.0.113.77" \
  -H "X-Forwarded-Host: attacker.example" \
  https://portal.staging.example.org/me
~~~

**Expected outcome:** no `administrator` principal ever appears from the forged headers. The request may be rejected, challenged to log in, or return the real principal verified by the auth gateway. Even inside a valid staging session, the gateway must overwrite the identity rather than taking curl's value.

Never infer from a single HTTP 200 that a bypass succeeded: the endpoint might be public or return anonymous data. Verify the **logged `SecurityContext` principal, local account ID, tenant/role decision, and resource response** safely.

## 20. Logging, detection, and investigation

Requests traversing multiple hops should carry a **trace/correlation ID** minted or normalized at the trusted edge. Note that clients can also forge trace headers; reset/sanitize them at the edge if used for identity/audit correlation.

**What to log (per data policy):**

- Actual trusted ingress/hop identity and carefully normalized client IP.
- Which component authenticated the user: P1 issuer, session/authentication method in log-safe form.
- Internal user ID or pseudonymous hash rather than email/raw tokens.
- Selected tenant, route, HTTP method, security rule, and allow/deny reason.
- Normalized `X-Forwarded` origin metadata; on conflicts, log an error flag rather than raw injection payloads.
- Proxy config version, mTLS service identity, and authentication gateway policy version.
- Anomaly counts: identity headers arriving at the public edge, duplicate headers, direct-backend attempts, wrong audiences, host spoofs, and 403 spikes.

**Never log** raw `Authorization` headers, OIDC/SAML tokens, cookies, mTLS private keys, session IDs, password-reset tokens, or full untrusted `Forwarded` values containing unnecessary PII.

**Alerts to configure:** backend requests arriving from non-allowlisted IPs/service identities, missing trusted authentication assertions on protected routes, invalid signed-claim audiences, gateway fail-open events, direct NodePort access, auth user changes between hops, non-allowlisted `X-Forwarded-Host`, duplicate `X-Verified-Subject`, or spikes in rate-limit exemptions.

Audit trails must resist header spoofing: never rely solely on a browser-supplied username or trace ID to attribute an event.

## 21. Production review checklist

- [ ] Diagrammed all P0/P1/P2/sidecar hops to the app; kept current whenever CDNs, WAFs, ingresses, or network routes change.
- [ ] Clearly separated the **real identity issuer** (P1) from **transport proxies** (P0/P2).
- [ ] Public edge strips inbound client **`Forwarded` and all `X-Forwarded-*`** headers, regenerating safe metadata.
- [ ] Public edge strips **all identity/role/tenant header aliases**, not just a single header name.
- [ ] Authentication gateway **verifies** real users before emitting `X-Verified-Subject` or a signed assertion.
- [ ] Backend accepts traffic solely from the right trusted gateway/ingress; direct NodePort/LoadBalancer/debug paths are blocked.
- [ ] Enforced ACLs/NetworkPolicies and, where appropriate, **mTLS service identities** on hops; private IPs alone are insufficient.
- [ ] If P2 accepts traffic from multiple sources, only P1 may emit identity assertions; headers from other workloads are never preserved.
- [ ] XFF trusted-hop policy knows exact TCP peers/hops and never picks an untrusted leftmost IP.
- [ ] `Host`/`Proto`/`Port`/`Prefix` are canonicalized; public domains are allowlisted and callback URLs/redirects are safe.
- [ ] Explicit single-standard `Forwarded`/`X-Forwarded-*` policy and conflict handling exist.
- [ ] Duplicate identity headers, underscore/hyphen aliases, and invalid HTTP framing are rejected/normalized per proxy contract.
- [ ] Spring Boot forwarded strategy (`NONE`/`NATIVE`/`FRAMEWORK`) is deliberately chosen; `ForwardedHeaderFilter` is not treated as an authenticator.
- [ ] If using `RequestHeaderAuthenticationFilter`, documentation explicitly notes **it does not verify identity itself**.
- [ ] Local account/tenant/role/resource permissions are checked independently; self-asserted `X-Groups`/`X-Admin` are never trusted.
- [ ] If using signed identity tokens, the backend verifies issuer/audience/signature/`exp`/`nbf`/key rotation and replay policy.
- [ ] No unintended form/Basic/API fallback bypasses proxy authentication.
- [ ] Backend session/cookie/CSRF, proxy auth session, and logout/revocation lifecycles are tested independently.
- [ ] Identity headers are re-emitted per request under policy or backed by explicit session binding and absolute lifetimes.
- [ ] Tests cover public edge, internal networks, untrusted pods, alternate ingress routes, and multi-tenancy.
- [ ] Tests cover bad XFF, `Forwarded`, `Host`, `Proto`, `Prefix`, repeated headers, forged roles, and request smuggling.
- [ ] Logging/tracing redaction prevents leaking credentials/PII or letting clients spoof audit identities.
- [ ] Alerts exist for direct backend access, forged identity headers, gateway fail-open, issuer mismatches, and proxy topology drift.
- [ ] Whenever proxy configs change, regression tests run for authentication, authorization, callbacks, and redirects before rollout.

**Key takeaway:** Across multiple reverse proxy layers, **an identity header is only as strong as the weakest hop in the trust chain**. Treat it as an **assertion with provenance**: strip client input → authentication gateway verifies → regenerate identity → protect and verify provenance across every hop → Spring checks local accounts and permissions. **`X-Forwarded-For`, `Forwarded`, mTLS peers, and `X-Verified-Subject` answer different questions**; never use one signal as proof of something it does not verify.

## 22. References

- [RFC 7239 – Forwarded HTTP Extension, Section 8 Security Considerations](https://www.rfc-editor.org/rfc/rfc7239.html): `Forwarded` can be modified by both clients and proxies; trust depends on trusted hops and transport.
- [Spring Framework 6.2 – Forwarded Headers and ForwardedHeaderFilter](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/filters.html): edge reset, `ForwardedHeaderFilter`, `removeOnly`, and filter ordering.
- [Spring Boot 3.5 – Running Behind a Front-end Proxy Server](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html): `NONE`/`NATIVE`/`FRAMEWORK`, Tomcat `RemoteIpValve`, `internal-proxies`, and forwarded header support.
- [Spring Security 6.5 – Pre-Authentication Scenarios](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/preauth.html): `RequestHeaderAuthenticationFilter` only extracts principals; external auth must protect headers.
- [Spring Security 6.5 – RequestHeaderAuthenticationFilter API](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/authentication/preauth/RequestHeaderAuthenticationFilter.html): `principalRequestHeader`, `exceptionIfHeaderMissing`.
- [Spring Security 6.5 – AbstractPreAuthenticatedProcessingFilter API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/preauth/AbstractPreAuthenticatedProcessingFilter.html): `AuthenticationManager`, `SecurityContextRepository`, principal changes.
- [MDN – X-Forwarded-For Security and Privacy Concerns](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/X-Forwarded-For): trusted proxy selection, direct origin reachability, and risks for IP-based security policies.
- [MDN – Forwarded HTTP Header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Forwarded): `for`/`by`/`host`/`proto` syntax, multiple proxies, and privacy.
- [OWASP – HTTP Headers Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html): classification and policies for HTTP response/request headers.
- [OWASP – Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): least privilege, deny by default, resource-level authorization.
- [OWASP – HTTP Request Smuggling](https://owasp.org/www-community/attacks/HTTP_Request_Smuggling): parser/proxy differentials that can create trust-boundary desynchronization.
