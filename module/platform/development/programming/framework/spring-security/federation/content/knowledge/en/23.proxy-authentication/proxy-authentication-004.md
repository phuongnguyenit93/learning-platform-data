# Restricting network sources and preventing direct backend access bypassing the proxy in Spring Security

## 1. Why can an authenticating reverse proxy still be insecure?

Suppose an organization places an **identity-aware reverse proxy** in front of a Spring Boot application. The proxy performs SSO using OIDC, SAML, Kerberos/SPNEGO, or an approved mechanism, then forwards a header such as `X-Authenticated-User` to the backend. The backend uses Spring Security **pre-authentication** to read the username from the header and load local permissions.

Expected flow:

~~~text
Internet / employees
       |
       v
HTTPS public hostname: portal.example.org
       |
       v
[Trusted authentication proxy]
  - authenticates user
  - enforces edge access policy
  - strips client-supplied headers
  - creates identity assertion for backend
       |
       v
[Spring Boot backend accepts requests only from proxy]
  - verifies peer/proxy boundary
  - accepts valid identity assertion
  - checks account and application permissions
       |
       v
Business endpoints
~~~

If the backend still exposes a direct port, such as `http://app-node:8080`, a `NodePort`, a secondary `LoadBalancer`, or `hostNetwork`, callers can **bypass the proxy**. If Spring obtains identity via `RequestHeaderAuthenticationFilter` without verifying the request came from a trusted source, a self-supplied header can turn into an authenticated principal.

**This is a critical trust-boundary flaw**, not merely a missing `@PreAuthorize` annotation. When a pre-auth filter accepts identity data from an untrusted source, downstream authorization checks see a forged user who appears authenticated.

This Knowledge article belongs to **Spring Security - federation → Proxy Authentication**, topic **"Restricting network sources and preventing direct backend access bypassing the proxy"**.

### Learning outcomes

After this lesson, you will be able to:

1. Distinguish **proxy authentication**, the **proxy→backend transport channel**, **Spring pre-authentication**, and **application authorization**.
2. Understand why `RequestHeaderAuthenticationFilter` does not authenticate the username inside the header itself.
3. Design **deny-by-default** at the network layer (security groups/firewalls/Kubernetes NetworkPolicy), eliminating public backend listeners and secondary ingresses.
4. Know how to use **mTLS/workload identity** to authenticate the proxy→backend hop when higher assurance than an IP allowlist is needed.
5. Strip/overwrite forged headers such as `X-Authenticated-User`, `Remote-User`, `X-Forwarded-User`, and `Forwarded/X-Forwarded-*` at the **trust boundary**.
6. Avoid confusing the **socket peer address** with the **client IP taken from X-Forwarded-For**; never use browser-controlled values to decide whether a proxy is trusted.
7. Configure Spring Security pre-auth to fail closed without unintended form login/basic auth fallbacks.
8. Audit bypass paths across direct pod IPs, NodePorts, secondary LoadBalancers, admin/actuator ports, localhost sidecars, IPv6, and other internal paths.
9. Apply NGINX, Kubernetes NetworkPolicy, Spring Security config examples, and a standalone Java 17 program.
10. Execute negative tests, inspect logs/metrics, and perform rollouts/rollbacks without loosening permissions carelessly.

**Context:** Java 17+, Spring Boot 3.x, Spring Security Servlet 6.x/7.x, NGINX, and Kubernetes are used as examples. Configurations vary by cloud, CNI, ingress, service mesh, and version. Addresses like `example.org` and network `10.42.0.0/16` are illustrative only, not valid configurations for every deployment.

---

## 2. Trust model: who actually verified the identity?

A browser request may carry:

~~~http
GET /admin/reports HTTP/1.1
Host: portal.example.org
X-Authenticated-User: administrator
X-Forwarded-For: 10.0.0.20
X-Forwarded-Proto: https
~~~

**Never treat any of the headers above as proof of identity.** A browser, mobile client, or HTTP script can craft them freely. Only when a **trusted proxy** has:
- Authenticated the browser/token per policy;
- Stripped all caller-supplied versions of the header;
- Regenerated the identity assertion from a **verified authentication context**;
- Sent it over a channel where **only the proxy is permitted to connect to the backend**;
- And the backend verifies/restricts the connection source;

does the backend have grounds to use the assertion.

### Five independent layers of defense

| Layer | Verification question | Example controls |
| --- | --- | --- |
| **L1: Network reachability** | Can any non-proxy party open a connection to the backend? | Firewalls, SGs, NetworkPolicy, private Service, no public NodePort |
| **L2: Proxy workload identity** | Is the peer reaching the backend truly the approved proxy? | mTLS certificate/SPIFFE ID, private endpoint + policy; IP allowlist as supplement |
| **L3: Header provenance/integrity** | Was the identity header written by the proxy after authentication? | Strip inbound, overwrite canonical header, reject duplicates |
| **L4: Spring pre-authentication** | Is the username read only from a trusted channel under a strict contract? | RequestHeaderAuthenticationFilter + provider + fail closed |
| **L5: Business authorization** | Is this user permitted to access this resource/action? | UserDetails/account status, tenant/ACL, @PreAuthorize/AuthorizationManager |

**Do not pick one of the five to replace all the others.** Public TLS from browser to proxy does not protect internal connections if the backend still exposes a direct port. Conversely, a correct NetworkPolicy does not prove the proxy actually authenticated the user before emitting the header.

## 3. The danger of RequestHeaderAuthenticationFilter

Spring Security describes `RequestHeaderAuthenticationFilter` as a **pre-authentication** filter: it extracts a username from an HTTP request header (historically defaulting to `SM_USER` from SiteMinder examples) and feeds it into Spring Security to load UserDetails/authorities.

**This filter does not authenticate the header itself.** Spring Security documentation warns: if an attacker can set the trusted header and deliver it to the application, the attacker can pick any username arbitrarily. This is especially dangerous when the mapped local account holds high privileges.

Broken flow:

~~~mermaid
flowchart TD
    A[Unauthenticated client] --> B[Direct network path to backend:8080]
    B --> C[Self-asserted X-Authenticated-User header]
    C --> D[RequestHeaderAuthenticationFilter only reads header]
    D --> E[PreAuthenticatedAuthenticationProvider loads user]
    E --> F[Spring sees Authentication created]
    F --> G[Business endpoint trusts forged principal]
~~~

**Risk also exists on internal networks**: another pod, a developer host over VPN, a batch job, an SSRF-capable service, or a secondary ingress can reach the backend. "Private IP only" does not equal "trusted proxy only".

### Two conditions to make pre-auth safer

1. **Every request reaching Spring via pre-auth must traverse the trusted authentication proxy**, with no direct paths or unintended authentication fallbacks.
2. **The proxy itself generates the identity header from a trusted authentication result**, rejects browser/user-supplied headers, and the backend never trusts headers without hop verification.

Spring can verify account status and authorities, yet **cannot know where the header originated on its own** if network/proxy trust is undesigned.

## 4. Do not confuse X-Forwarded-For with proxy identity

Three kinds of "addresses" are easily confused:

| Value | Meaning | Can it verify the proxy source? |
| --- | --- | --- |
| **Transport socket peer** | TCP/TLS endpoint connecting directly to the app server | Can serve as an extra signal if obtained from an unrewritten transport layer with controlled routing |
| **X-Forwarded-For** | Chain of client/proxy IPs forwarded via HTTP headers | **No**, if the edge has not stripped/overwritten it and hop trust is unverified |
| **Forwarded: for/by/host/proto** | HTTP metadata per RFC 7239 | **No**, the header itself can still be forged by the client |
| **X-Real-IP** | IP header a proxy may set | Does not replace proxy authentication |
| **X-Forwarded-Proto** | Original scheme per proxy | Does not prove actual TLS between proxy and backend |
| **X-Forwarded-Host** | Original host per proxy | Not a backend identity allowlist |
| **mTLS peer identity** | Certificate/SAN verified by the TLS stack for the backend hop | Can serve as workload identity proof, given proper trust anchors/policy |

Risky example:

~~~java
// Do NOT do this to determine whether this is a trusted proxy:
boolean trustedProxy = request.getHeader("X-Forwarded-For")
        .startsWith("10.42.");
~~~

The caller can write this header themselves. Moreover, `getRemoteAddr()` in a Servlet may **already have been rewritten by Tomcat RemoteIpValve or ForwardedHeaderFilter**, depending on configuration. If you want to check the **raw transport peer**, read it from the ingress/firewall layer or a connector that preserves the original peer address before rewriting. Never rely on a `getRemoteAddr()` value already replaced by forwarded-header middleware.

**Network origin and user identity are two distinct signals**. A browser IP "inside the corporate network" must never be allowed to write its own identity assertion directly to the backend.

## 5. Proper architecture: the backend must not be public

A recommended model:

~~~mermaid
flowchart LR
    U[Internet / corporate browser] --> E[Public edge + authentication proxy]
    E -->|Authenticated private hop| A[Spring Boot backend]
    A --> D[(Database/private dependencies)]
    X[Untrusted client / sibling workload] -.->|Blocked by firewall or NetworkPolicy| A
~~~

Implementation:
- The app's public DNS points exclusively to the **edge ingress/proxy**, never to a backend IP.
- The backend is deployed with a private IP/service, with no separate Internet load balancer.
- The backend's firewall/cloud security group **allows inbound traffic solely from the proxy tier**; where possible, use identity-based rules/resource tags rather than manual IPs.
- In Kubernetes, use a `ClusterIP` service (with no public Internet ingress) plus a NetworkPolicy selecting the exact ingress controller/auth-proxy pods.
- Restrict node host ports, `hostNetwork`, NodePorts, other LoadBalancers, secondary internal gateways/routes, and IPv6.
- Isolate admin/actuator/metrics endpoints from public traffic, with dedicated authentication and network policies.
- Permit health probes from exact sources without exposing the entire admin API.
- Increase assurance with **proxy→backend mTLS**, having the backend trust only peer certs with the right workload identity.
- Only then allow Spring to accept pre-auth headers.

**No single Spring Boot `server.address=127.0.0.1` property fits every deployment.** In environments where proxy and app run on the same host, binding loopback may fit; in Kubernetes across separate pods/networks, binding loopback prevents the ingress from connecting. Choose private services/bind addresses + policies matched to the real topology.

## 6. Inventory matrix of entry paths to audit

Before production, tabulate every network path that could reach the app:

| Path | Allowed to reach backend? | Mandatory proof |
| --- | --- | --- |
| Public HTTPS via identity proxy | **Yes**, after authentication | Proxy identity + network policy + sanitized headers |
| Internet → backend IP/secondary public LB | **No** | Cloud firewall/SG/LB binding deny |
| Arbitrary pod in same namespace → backend | **No** unless it is a designated trusted proxy/service | Exact NetworkPolicy podSelector |
| Pod in another namespace → backend | **No** unless an explicit path exists | Namespace/pod selector + RBAC |
| Host node → backend/pod | Only approved tasks | Host firewall/cluster controls; CNI behavior |
| NodePort/hostPort → backend | Normally **no** | Unexposed or firewall deny |
| Localhost inside the same pod | Reachable by sidecars/processes | Container isolation/loopback trust; never treat every sidecar as a proxy |
| Health probes | Only designated endpoint and source | Health-only path/port/network policy |
| Actuator/management port | Operations only | Private port, role auth, distinct policy |
| kubectl port-forward | Only Kubernetes API-authorized identities | RBAC/audit; NetworkPolicy does not replace RBAC |
| IPv6 address/public AAAA | Only if explicitly designed | IPv6 policy matching IPv4 |
| DR/staging/alternate ingress | Only paths included in the trust model | Same auth/header hygiene requirements |

**Kubernetes note:** NetworkPolicy depends on a CNI that supports enforcement, and pod/namespace-based selectors can be affected by label-editing permissions. If RBAC lets an untrusted party attach `app: auth-proxy` to their own pod in a trusted namespace, a label-based allowlist can be abused. Therefore **RBAC/admission policies** must protect labels and namespaces.

## 7. Kubernetes NetworkPolicy: allow ingress proxy only

In namespace `apps`, backend pods carry label `app: portal-backend`, while the proxy runs in namespace `edge` with label `app: identity-proxy`. Template:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: portal-only-from-identity-proxy
  namespace: apps
spec:
  podSelector:
    matchLabels:
      app: portal-backend
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: edge
          podSelector:
            matchLabels:
              app: identity-proxy
      ports:
        - protocol: TCP
          port: 8080
~~~

**Meaning:**
- Pods selected by `podSelector` may receive only ingress matching the policy.
- `namespaceSelector` and `podSelector` **within the same `from` item** combine with AND semantics: only proxy pods inside the edge namespace.
- Splitting selectors into two separate items creates OR semantics and can unintentionally widen allowed sources.
- Port 8080 is the **actual port the backend pod listens on**, not necessarily the proxy's public TLS port.
- This policy **does not** establish TLS, user authentication, mTLS identity, or header cleansing. It is an L3/L4 network control.

### Limitations that must be tested

1. NetworkPolicy does nothing if the CNI does not enforce it.
2. `ClusterIP` does not protect against **all** internal workloads; NetworkPolicy adds pod-to-pod restriction.
3. Node/hostNetwork traffic and NAT paths can behave differently per CNI/cloud; test the real path.
4. When selecting all backends, avoid accidentally blocking health probes/sidecars/service mesh traffic without a plan.
5. NetworkPolicy does not stop privileged Kubernetes API users from running `port-forward`; protect via RBAC/audit/admission.
6. IPv6/dual-stack and hostPort require separate testing; never assume an IPv4 policy covers them.
7. Label filtering relies on protecting permissions to modify labels.
8. Egress may also need restrictions against exfiltration if the threat model requires it; the policy above illustrates ingress only.
9. You may need namespace-wide default-deny with exact whitelists for DNS/metrics/health; avoid `ingress: - {}` since that opens everything.

**Step-by-step verification:** spin up a test pod **without** the proxy label and verify it cannot open a TCP connection to the backend; only an identified test proxy pod may connect. Without verified CNI enforcement, treat the YAML policy as **unproven protection**.

## 8. Non-Kubernetes cloud VMs/containers

For VMs/EC2/Compute Engine/Azure VMs, you can:

- Omit public IPs on backend VMs/NICs when unnecessary.
- Place internal load balancers strictly in private subnets with no public listeners.
- Restrict inbound security groups/NSGs to the **proxy security group/managed identity source** when the cloud supports it; if CIDRs must be used, automate updates as proxy IPs change.
- Run a deny-by-default host firewall on the backend.
- Have the proxy forward solely to private addresses and verify backend TLS/mTLS.
- Configure load balancing so no "maintenance LB" bypasses the proxy.
- Include VPNs/bastions/CI runners in the threat model rather than implicitly trusting all private RFC1918 space.
- Govern admin SSH/Kubernetes access with RBAC, never using the app HTTP port for direct debugging.
- If proxy and app share a host, the app can bind loopback/Unix sockets with strict file permissions; however, other processes on the same host remain potential callers, requiring OS isolation.

**Why is a firewall alone insufficient?** A compromised pod/VM on the allowlist or one able to impersonate the proxy can send forged identity headers. Hence mTLS service identity, proxy hygiene, app account checks, and monitoring remain necessary.

## 9. NGINX: stripping client-supplied identity headers

The proxy is where **"untrusted HTTP requests" become "internal identity assertions"**. It must resolve authentication **before** generating headers.

Risky headers:
- `X-Authenticated-User`
- `X-Forwarded-User`
- `Remote-User`
- `X-Remote-User`
- `X-Auth-Request-User`
- `X-User`
- `X-Authenticated-Groups` / `X-Role`
- `X-Forwarded-Client-Cert` when using a service mesh/proxy
- `Authorization` if the proxy terminates authentication and the backend must not receive raw bearer credentials
- Client-supplied `Forwarded`, `X-Forwarded-For/Host/Proto/Port/Prefix` chains.

**Do not blindly strip `Authorization` on every app**: an API may need bearer tokens for the backend to validate itself. In that case design **two separate authentication paths** rather than conflating bearer auth and pre-auth headers, and have the backend verify the bearer token. When the proxy terminates auth, typically pass only the approved assertion, without unnecessary credentials.

### NGINX example with an authentication subrequest

The illustrative setup assumes an internal `auth-service` returning:
- **2xx** on successful authentication, with response header `X-Verified-Principal` derived from a verified identity store;
- **401/403** on failure;
- Other statuses treated as upstream errors, never as success.

~~~nginx
upstream portal_backend {
    server portal-backend.internal:8080;
}

server {
    listen 443 ssl;
    server_name portal.example.org;

    ssl_certificate     /etc/nginx/tls/portal.crt;
    ssl_certificate_key /etc/nginx/tls/portal.key;

    location = /_auth {
        internal;
        proxy_pass http://auth-service.internal:9000/verify;
        proxy_pass_request_body off;
        proxy_set_header Content-Length "";

        # Prevent client from spoofing identity headers to auth service.
        proxy_set_header X-Authenticated-User "";
        proxy_set_header X-Verified-Principal "";

        proxy_set_header X-Original-URI $request_uri;
    }

    location / {
        auth_request /_auth;
        auth_request_set $verified_user
            $upstream_http_x_verified_principal;

        # Forward only when auth service has supplied a principal.
        if ($verified_user = "") { return 403; }

        proxy_set_header X-Authenticated-User $verified_user;

        # Identity aliases must not pass through from browser.
        proxy_set_header X-Forwarded-User "";
        proxy_set_header X-Remote-User "";
        proxy_set_header Remote-User "";
        proxy_set_header X-Auth-Request-User "";
        proxy_set_header X-User "";
        proxy_set_header X-Authenticated-Groups "";

        # Metadata headers written from proxy-managed values.
        proxy_set_header Forwarded "";
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Host portal.example.org;
        proxy_set_header Host portal.example.org;

        proxy_pass http://portal_backend;
    }
}
~~~

**This template is not a complete production configuration**: paths/certificates/auth-service are hypothetical, backend transport is plain HTTP over a private network, and the auth service must **genuinely authenticate** the request and protect its response headers. Use HTTPS/mTLS for the proxy→backend hop whenever possible. NGINX `auth_request` requires the corresponding module and a compliant auth service contract.

### Key things to understand about NGINX

- `proxy_set_header X-Authenticated-User $verified_user` **overwrites** the same header name toward the backend; `proxy_set_header Name ""` suppresses forwarding that header.
- NGINX forwarding behavior must be checked inside the **exact location/server block**, because `proxy_set_header` inheritance follows specific scoping rules.
- `auth_request_set` reads the value returned by the auth subrequest, **not** the client-supplied `$http_x_authenticated_user`.
- `if (...) { return 403; }` here only guards against an auth service returning 2xx with an empty principal; it is not an authentication replacement for `auth_request`.
- If the auth service produces `X-Verified-Principal` from a user-supplied header or an unverified cookie, the proxy remains vulnerable.
- Never write `proxy_set_header X-Authenticated-User $http_x_authenticated_user`, as that simply forwards attacker input.
- Alias header sanitization must cover **every header name the backend/filters actually read**, not just the few examples in the snippet.
- HTTP header case-insensitivity, duplicate headers, and underscore/hyphen variants must be tested across NGINX, LB, and container; you may need to **reject duplicates** at the edge.
- If an external CDN/proxy sits in front, determine where the **first** trust boundary lies and strip headers before the authentication proxy processes them.

### What does the auth service do?

A contract-compliant auth service:
1. Validates the session/OIDC tokens/SPNEGO context or trusted identity data itself;
2. Evaluates token signature, issuer, audience, expiry, and nonce/state/session per protocol;
3. Checks status/revocation/proxy access rules per policy;
4. Returns 2xx with a canonical principal, never accepting a principal from the browser;
5. Returns 401/403 when unauthenticated/unauthorized;
6. Never returns 2xx with a fake or blank `X-Verified-Principal`;
7. Prevents callers outside the trusted proxy from hitting admin/debug endpoints to forge authentication responses;
8. Implements auditing, rate limiting, and fail-closed failure modes.

## 10. Forwarded headers: useful, yet you must know who created them

When a reverse proxy terminates TLS and calls the app over private HTTP, Spring may need the public URL to build redirects and SSO callbacks:

~~~text
Browser: https://portal.example.org/
Proxy -> app: http://portal-backend:8080/
Proxy adds:
  X-Forwarded-Proto: https
  X-Forwarded-Host: portal.example.org
~~~

Spring Boot supports:

~~~yaml
server:
  forward-headers-strategy: native
~~~

Depending on container/version, `native` leverages Tomcat/Jetty/Netty support. If a Spring Framework filter is needed, choose `framework`. For apps that do not trust or use forwarded headers, `none` or `ForwardedHeaderFilter` with `removeOnly=true` may fit.

**Prerequisite:** the proxy at the trust boundary must strip `Forwarded` and **all** `X-Forwarded-*` variants sent by outside callers, then write values it determines itself. Spring cannot tell on its own whether a header came from the proxy or an attacker. This is a direct warning in Spring Framework/Spring Security docs.

### Never use forwarded headers to authenticate a workload

`X-Forwarded-For: 10.42.1.5` does not prove the TCP peer is auth-proxy. `X-Forwarded-Proto: https` likewise does not prove mTLS occurred between proxy and backend. The backend must verify transport/workload identity via **separate network/TLS configuration**, never using metadata headers as proof.

### Chained proxies

~~~text
Browser -> CDN -> LB -> Identity Proxy -> Spring
~~~

Clarify explicitly:
- Which proxy is allowed to set the client IP;
- Which proxy is allowed to set the **authenticated principal**;
- Which proxy strips caller input;
- Which proxy appends `Forwarded/X-Forwarded-*`;
- Processing/rewrite order and `trusted proxies` in Tomcat/NGINX;
- That no hop inadvertently forwards user-supplied identity headers;
- That public HTTP Host/Proto come from an allowlist rather than an untrusted `Host`.

Do not conflate "client-supplied IP chain" with "proxy workload certificate".

## 11. NGINX real_ip module is not a firewall

NGINX `ngx_http_realip_module` allows `set_real_ip_from` to specify which proxy peers have their `X-Forwarded-For` trusted when reconstructing the client IP.

Example **only when NGINX genuinely sits behind a trusted LB**:

~~~nginx
set_real_ip_from 192.0.2.10;
real_ip_header X-Forwarded-For;
real_ip_recursive on;
~~~

These addresses are illustrative only. Setting `set_real_ip_from 0.0.0.0/0` or an overly broad network containing untrusted clients lets attackers control the logged/middleware IP. Restrict strictly to LB/proxy peer addresses and inspect `$realip_remote_addr` to audit the original peer when the module runs.

**Important:** real-ip configuration handles interpreting the **client network address**; it **does not** isolate the backend or authenticate `X-Authenticated-User`. Network firewalls and mTLS identity remain separate controls.

## 12. mTLS: binding the backend to an approved proxy

An IP allowlist is a useful layer, yet not always sufficient:
- Proxy pod IPs change across deployments;
- NAT/load balancers exist;
- Another pod may be compromised or mislabeled;
- Another internal path also reaches the backend;
- A service mesh may rewrite source IPs.

With **mutual TLS (mTLS)**:
1. The proxy presents a client certificate to the backend TLS endpoint.
2. The backend or sidecar TLS stack verifies the chain, issuer trust anchor, **SAN/workload identity**, and validity/revocation per policy.
3. Only proxy service identities on the allowlist may connect.
4. The backend simultaneously presents a server certificate matching the right backend identity for upstream TLS.
5. Identity headers must be generated by the proxy after authentication and protected from tampering on the hop.

**mTLS authenticates the proxy, not the end user.** A TLS-verified proxy that emits a wrong user assertion can still cause identity confusion; hence proxy auth/session policies and Spring business authorization remain mandatory.

### Warning on X-Forwarded-Client-Cert (XFCC)

In some service meshes/proxies, `XFCC` carries certificate metadata over HTTP. **Never trust client-supplied XFCC**; use it only when the mesh/edge **strips/overwrites** it, direct access to the app is impossible, and the upstream workload is authenticated. If direct backend access exists, a self-supplied XFCC header does not prove mTLS took place.

### When proxy and app share a host

A Unix domain socket with tight OS permissions can restrict which processes may call the backend, yet identity headers/actor permissions still require protection. Never assume every process on the host is trusted. If connecting over TCP loopback `127.0.0.1:8080`, audit untrusted local processes and admin debug tools.

## 13. Spring Security pre-auth: proper usage and limits

Spring Security provides these components:

| Component | Role |
| --- | --- |
| `RequestHeaderAuthenticationFilter` | Reads the principal from a proxy-generated header; **does not verify the header** |
| `PreAuthenticatedAuthenticationProvider` | Converts the pre-auth token into an Authentication with loaded UserDetails/authorities |
| `UserDetailsByNameServiceWrapper` | Adapter invoking `UserDetailsService` from a pre-auth token |
| `SecurityFilterChain` | Enforces filters, route authorization, and session policy |
| `Http403ForbiddenEntryPoint` | Entry point returning 403 when no other login mechanism exists |
| `SessionCreationPolicy.STATELESS` | Avoids maintaining stateful security sessions when choosing a per-request model |
| `OncePerRequestFilter` | Can serve as a guard when **trusted transport metadata** exists |
| `ForwardedHeaderFilter` | Processes/strips Forwarded metadata; **not a proxy authenticator** |

### 13.1 Key pre-auth configuration snippet

This is an **illustrative Java class** using Spring Security 6.x+ and Boot 3.x. It **assumes** the application already implements a `UserDetailsService` to load accounts/authorities and that a proxy→backend network/mTLS boundary is enforced independently.

~~~java
package com.example.portal;

import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.core.userdetails.UserDetailsByNameServiceWrapper;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationProvider;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationToken;
import org.springframework.security.web.authentication.preauth.RequestHeaderAuthenticationFilter;

@Configuration
public class ProxyPreauthConfig {

    @Bean
    AuthenticationManager proxyAuthManager(UserDetailsService users) {
        var wrapper =
                new UserDetailsByNameServiceWrapper<
                        PreAuthenticatedAuthenticationToken>();
        wrapper.setUserDetailsService(users);

        var provider = new PreAuthenticatedAuthenticationProvider();
        provider.setPreAuthenticatedUserDetailsService(wrapper);
        return new ProviderManager(provider);
    }

    @Bean
    RequestHeaderAuthenticationFilter proxyIdentityFilter(
            AuthenticationManager proxyAuthManager) {
        var filter = new RequestHeaderAuthenticationFilter();
        filter.setPrincipalRequestHeader("X-Authenticated-User");
        filter.setExceptionIfHeaderMissing(true);
        filter.setContinueFilterChainOnUnsuccessfulAuthentication(false);
        filter.setAuthenticationManager(proxyAuthManager);
        return filter;
    }

    @Bean
    FilterRegistrationBean<RequestHeaderAuthenticationFilter>
            disableProxyFilterOutsideSecurityChain(
                    RequestHeaderAuthenticationFilter proxyIdentityFilter) {
        var registration =
                new FilterRegistrationBean<>(proxyIdentityFilter);
        registration.setEnabled(false);
        return registration;
    }
}
~~~

**This is not yet a complete Spring Boot app**: it has no `main()`, `UserDetailsService`, proxy transport verification, or `SecurityFilterChain` mounting the filter. There is no stdout. The code requires Spring Security, Boot, and Jakarta Servlet dependencies matching your version; it will not run with bare `javac`.

Notable points:
- `X-Authenticated-User` **is considered trustworthy only if the network/mTLS boundary and proxy sanitization are secure**.
- `setExceptionIfHeaderMissing(true)` prevents accepting requests missing a principal under pre-auth; final HTTP behavior still depends on filters/entry points and exception handling.
- `setContinueFilterChainOnUnsuccessfulAuthentication(false)` prevents a provider failure from silently falling through to another auth mechanism; proper error-handling flow is still required.
- `setAuthenticationManager` uses the pre-auth provider to load UserDetails; **does not verify the username header itself**.
- `FilterRegistrationBean#setEnabled(false)` prevents Spring Boot from automatically running the filter as a Servlet Filter **outside** SecurityFilterChain when the filter bean is discovered; the filter must be added **explicitly** to the security chain.
- If Spring persists sessions, the filter may skip running pre-auth on every request once `SecurityContext` exists. Define session/revocation semantics instead of assuming a missing header on a later request revokes prior sessions.

### 13.2 Adding the filter to SecurityFilterChain

Spring Security Servlet configuration snippet:

~~~java
@Bean
SecurityFilterChain webSecurity(
        HttpSecurity http,
        RequestHeaderAuthenticationFilter proxyIdentityFilter)
        throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/health/live").permitAll()
                    .requestMatchers("/admin/**").hasAuthority("PORTAL_ADMIN")
                    .anyRequest().authenticated())
            .sessionManagement(session -> session
                    .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .addFilterBefore(proxyIdentityFilter,
                    UsernamePasswordAuthenticationFilter.class)
            .build();
}
~~~

**This snippet belongs inside a `@Configuration` class**, requiring `@Bean`, `HttpSecurity`, `SecurityFilterChain`, `SessionCreationPolicy`, and `UsernamePasswordAuthenticationFilter` imports. The health endpoint may be `permitAll` in the app while the **network layer still blocks outside sources**; `permitAll` does not mean the public Internet may call the backend directly.

Choosing `STATELESS` here ensures each pre-auth request relies on a fresh header, yet:
- It does not suit every app requiring HttpSession/CSRF/session features; choose the session model per business needs.
- If using sessions, control lifetime, principal-change detection, and session invalidation when headers/identities change.
- Do not mix form login/basic auth fallbacks in ways that break the "every request traversed the proxy" assumption.
- Configure an explicit `AuthenticationEntryPoint` and failure statuses for apps/APIs rather than inferring 403 from a fragment without testing.
- If another security chain exists, ensure it does not accidentally admit requests without checking proxy trust.

**Why not put `.permitAll()` on every endpoint?** Because the username in a pre-auth header is only an authentication input; every route/object still needs authorization.

## 14. Does a Spring network guard replace a firewall?

**No.** A `OncePerRequestFilter` can inspect raw peer/mTLS identity as **defense in depth**, yet:
- An exception handling or filter-order bug can cause the guard not to run on error/async dispatches;
- The Spring container may rewrite `getRemoteAddr()` based on forwarded headers;
- If the guard merely reads an IP from a header, it is easily spoofed;
- Management endpoints on another port may bypass the guard;
- An in-process guard does not protect a compromised JVM from internal network reachability.

Use **out-of-process** network access control as the primary enforcement layer. Inside the app, checking transport identity from integrity-protected connector/mesh metadata adds value.

### Caveats with Servlet getRemoteAddr()

If Tomcat RemoteIpValve or Spring ForwardedHeaderFilter is active, `request.getRemoteAddr()` may be adjusted to the **original client IP**, not the raw socket peer. Do not use that to allowlist proxies. For a real guard, use:
- Network sidecar/service-mesh authorization based on authenticated peer identity;
- L4 firewalls/security groups;
- Raw socket peer metadata supplied by a trusted connector and **unaltered by user-controlled forwarded headers**;
- mTLS certificate chain/SAN verified at the TLS terminator.

A guard accepting `X-Proxy-Verified: true` via an HTTP header **still fails to prove a trusted peer** if the backend has any alternate entry path.

## 15. Standalone Java 17 demo: simulating conditions to accept an identity header

The program below uses only the **Java Standard Library**, requiring no Spring/Kubernetes/NGINX. It demonstrates one principle:

> Treat an identity header as **eligible input for account mapping** only when the request arrived from a configured proxy peer, the peer **was mTLS-verified by the transport layer**, and the identity header is valid.

It **does not verify certificates itself, open a TCP server, issue Authentication objects, or replace a network firewall**. The `peerMtlsVerified` parameter simulates a result that the **real TLS stack** must provide; in production **never take this boolean from a client's JSON/query/header**.

File `TrustedProxyBoundaryDemo.java`:

~~~java
import java.util.Set;

public final class TrustedProxyBoundaryDemo {

    record Request(
            String rawSocketPeer,
            boolean peerMtlsVerified,
            String assertedUser,
            String claimedForwardedFor) {
    }

    private static final Set<String> APPROVED_PEERS =
            Set.of("10.42.7.10", "10.42.7.11");

    static String evaluate(Request request) {
        if (!APPROVED_PEERS.contains(request.rawSocketPeer())) {
            return "DENY_UNTRUSTED_PEER";
        }
        if (!request.peerMtlsVerified()) {
            return "DENY_UNVERIFIED_PROXY";
        }
        String principal = request.assertedUser();
        if (principal == null || principal.isBlank()) {
            return "DENY_MISSING_IDENTITY";
        }
        if (!principal.matches(
                "[a-z0-9._-]{1,64}@example[.]org")) {
            return "DENY_INVALID_IDENTITY";
        }

        // Intentionally do NOT use claimedForwardedFor.
        // Policy approval is not yet application authentication.
        return "ALLOW_FOR_USER_MAPPING";
    }

    public static void main(String[] args) {
        Request normal = new Request(
                "10.42.7.10", true,
                "linh@example.org", "203.0.113.7");

        Request direct = new Request(
                "198.51.100.33", false,
                "admin@example.org", "10.42.7.10");

        Request siblingPod = new Request(
                "10.42.8.15", false,
                "admin@example.org", "10.42.7.10");

        Request fakeProxy = new Request(
                "10.42.7.11", false,
                "admin@example.org", "203.0.113.7");

        Request missingUser = new Request(
                "10.42.7.10", true, "", "203.0.113.7");

        Request malformed = new Request(
                "10.42.7.10", true,
                "admin\r\nX-Role: superuser", "203.0.113.7");

        Request forgedClientIp = new Request(
                "10.42.7.10", true,
                "linh@example.org", "127.0.0.1");

        System.out.println("Normal: " + evaluate(normal));
        System.out.println("Direct: " + evaluate(direct));
        System.out.println("Sibling pod: " + evaluate(siblingPod));
        System.out.println("No mTLS: " + evaluate(fakeProxy));
        System.out.println("No user: " + evaluate(missingUser));
        System.out.println("Malformed: " + evaluate(malformed));
        System.out.println("Forged XFF only: "
                + evaluate(forgedClientIp));
    }
}
~~~

Compile and run:

~~~bash
javac TrustedProxyBoundaryDemo.java
java TrustedProxyBoundaryDemo
~~~

**Exact** stdout:

~~~text
Normal: ALLOW_FOR_USER_MAPPING
Direct: DENY_UNTRUSTED_PEER
Sibling pod: DENY_UNTRUSTED_PEER
No mTLS: DENY_UNVERIFIED_PROXY
No user: DENY_MISSING_IDENTITY
Malformed: DENY_INVALID_IDENTITY
Forged XFF only: ALLOW_FOR_USER_MAPPING
~~~

### Why does "Forged XFF only" still return ALLOW?

Because the program **does not rely on `X-Forwarded-For` to authenticate the proxy**. In that case the raw peer is still an approved proxy and mTLS was verified; forging a client IP in metadata **does not turn into a different identity**. If an application uses XFF to decide user privileges, that is the wrong model. In production, the proxy must still **strip/overwrite XFF** so client IP logs/rate limits remain reliable, yet that is a **separate mechanism** from identity authentication.

### Important limitations

- `APPROVED_PEERS` is a mock IP set, not a dynamic production IP management mechanism; Kubernetes NetworkPolicy/mesh service identity is usually better.
- `rawSocketPeer` must come from a trusted transport layer, not from a `request.getRemoteAddr()` rewritten by forwarded-header middleware.
- `peerMtlsVerified` must be the output of **TLS peer certificate verification**, not a caller-supplied header/boolean.
- The principal regex validates syntax only; the backend must still **load the account and check enabled/tenant/authorities**.
- `ALLOW_FOR_USER_MAPPING` **does not** equal permitting a business action, issuing tokens, or granting admin rights.
- Never retain HTTP identity headers in long-lived sessions when principals/accounts can change.
- This example is a standalone Java 17 exercise only; never copy it as an authorization bypass in a real app.

## 16. Preventing header spoofing and duplicate headers

HTTP header names are case-insensitive. Depending on proxies/containers, names with hyphens/underscores or repeated headers may normalize differently.

Examples of risky variants:

~~~http
X-Authenticated-User: alice
x-authenticated-user: admin
X_Authenticated_User: other
X-Forwarded-User: privileged
Remote-User: owner
~~~

What happens if:
- The edge strips uppercase `X-Authenticated-User` but forgets aliases?
- NGINX passes duplicate headers while Tomcat's `getHeader()` picks a different value?
- A middleware reads `X_Authenticated_User` instead of the canonical header?
- The app has filter A reading `SM_USER` while the auth proxy overwrites only `X-Authenticated-User`?
- Another API route uses an `Authorization: Basic` fallback and bypasses the proxy?
- XFCC is forged by the client and the service mesh fails to strip it?

Countermeasures:
1. Inventory **all** identity headers read by every app/filter.
2. Strip/overwrite at the edge **case-insensitively**.
3. Reject duplicate/ambiguous identity headers where the proxy supports it.
4. Do not read extra alias headers unnecessarily.
5. Choose **one canonical assertion** generated by the proxy and a governed principal grammar.
6. A signed short-lived assertion with issuer/audience/time can be used, though **it helps only if the app verifies signatures and proxy keys remain genuinely secure**.
7. Test end-to-end across the full CDN→ingress→proxy→app chain, because hops may normalize headers differently.
8. Never use arbitrary `Host` or `X-Forwarded-Host` as a trusted identity namespace/tenant.
9. Use issuer/tenant-scoped account IDs rather than granting admin from usernames.
10. If the app receives a trusted original client IP, keep it for logging/rate limits, never as a principal substitute.

### Do not "overwrite last" if a bypass path exists

Even when NGINX strips headers properly, that protects **only requests traversing NGINX**. A request sent straight to the backend **does not** traverse NGINX. Therefore network isolation/mTLS is an indispensable part of the design.

## 17. Pre-authentication with a signed identity assertion

Bare username headers rely on trust in the proxy and transport channel. When multiple components participate or middlebox compromise is a concern, you can design a **signed assertion** for the backend:

~~~json
{
  "iss": "https://identity-proxy.example.org",
  "aud": "portal-backend",
  "sub": "opaque-user-42",
  "iat": 1794000000,
  "exp": 1794000060,
  "scope": "portal.read",
  "tenant": "finance"
}
~~~

This is an **illustrative claim body only**, not a valid JWT (missing JWS header/signature). If choosing JWT:
- The backend must verify the **JWS signature**, algorithm allowlist, keys/rotation, and `iss/aud/exp/nbf/iat`.
- Assertions must be **short-lived**, carry minimal data, and specify the exact issuer and backend-specific audience.
- Enforce replay/session-binding policies as needed rather than checking signatures alone.
- The proxy must mint assertions from verified identities, never re-signing a client-supplied username.
- The backend should still verify the **proxy's mTLS workload identity** even with signed assertions if direct paths must be blocked.
- A signed JWT **does not stop direct backend exposure** if tokens leak or the backend has an unauthenticated fallback.
- Backend authorization still applies per resource rather than relying blindly on unapproved privilege claims.

In Spring, this approach can use **Resource Server JWT** instead of `RequestHeaderAuthenticationFilter`, which is a **different authentication architecture** requiring an explicit token contract rather than just renaming a header.

## 18. Sessions and identity switching through the proxy

A proxy pre-auth app may or may not use sessions:

### Stateless per-request

- Every request carries a proxy-supplied assertion;
- Spring does not rely on an old session to skip checking fresh identity;
- Fits APIs where performance/UX permit;
- Must still check current account status/authorization;
- Requires appropriate endpoint CSP/CSRF/header/cache controls.

### Stateful HttpSession

- Spring saves Authentication after the initial pre-auth;
- Subsequent requests may use the session even if headers disappear or change unless config/filters check principal changes;
- If the user logs out of the identity proxy without revoking the app session, the local session can survive;
- Must govern session TTL, identity switches, `setCheckForPrincipalChanges(true)`, and invalidation as needed;
- Data like groups/roles can go stale after IAM updates;
- When multiple tabs/users share a browser, avoid principal confusion.

**Never treat "the proxy will always send the right header" as a session-revocation mechanism.** Use session invalidation, SSO logout events, live authorization, or fresh per-request assertions per SLA.

### Routes that are easily overlooked

Audit:
- `/api/**` distinct from `/web/**`;
- `/actuator/**`, `/management/**`;
- `/error`, `/forward`, `/async`;
- WebSocket upgrade endpoints;
- gRPC/HTTP/2 gateway routes;
- File upload/status callbacks;
- Static admin consoles;
- Scheduled-job HTTP hooks;
- Legacy servlet mappings;
- Sidecar health endpoints.

If a backend endpoint serves external webhooks, give it a **dedicated authentication channel/port/service** with HMAC/mTLS/token validation instead of opening the entire backend to webhooks and breaking the proxy-only invariant.

## 19. Flows with multiple authentication mechanisms

Suppose a Spring app simultaneously has:
- Header pre-auth for web SSO;
- Basic auth for legacy scripts;
- API keys on `/internal/**`;
- OIDC tokens on `/api/**`.

This requires **explicit security-chain routing** with zero unexpected fallbacks:
- Web pre-auth endpoints accept requests only through the proxy with verified assertions.
- Bearer-token APIs must have dedicated issuer/audience/token validation.
- Internal admin endpoints have dedicated mTLS/workload identity and network scopes.
- Batch scripts need narrow-privilege service accounts; never reuse admin user endpoints.
- Do not let `RequestHeaderAuthenticationFilter` read identity headers on API requests authenticated differently with incompatible account mappings.
- Never leave `formLogin()` or `httpBasic()` exposing a direct login path bypassing SSO when the architecture mandates proxy-only auth.
- With multiple `SecurityFilterChain` beans, verify matcher ordering and include a catch-all chain protecting remaining requests.

Spring Security documentation specifically warns against pairing `RequestHeaderAuthenticationFilter` with alternative login mechanisms that could bypass the external authentication system. That does not forbid multiple mechanisms altogether, but requires **cleanly separating paths/trust models** and testing negative cases.

## 20. Comparing controls against bypass paths

| Architectural flaw | Why dangerous | Strong countermeasure |
| --- | --- | --- |
| Backend has public IP:8080 | Clients bypass the proxy | Private subnet/service + SG/firewall deny |
| Backend uses ClusterIP only | Internal pods can still reach it | NetworkPolicy + mTLS workload identity |
| NetworkPolicy allows all namespaces | Any internal workload can forge headers | Exact namespace+pod selectors and protected labels |
| Proxy strips only X-User, app reads SM_USER | Identity header bypass remains | Catalog all auth headers; strip every alias |
| App trusts X-Forwarded-For as source IP | Caller can supply fake proxy IPs | Transport peer/network ACLs, mTLS |
| Proxy passes `$http_x_authenticated_user` | Header originates from browser | Use verified auth-service output only |
| App has unintended httpBasic fallback | Bypasses proxy identity policy | Separate security chains; deny unwanted mechanisms |
| Actuator management on public port | Bypasses edge/exposes sensitive endpoints | Private port + dedicated auth/authorization |
| Spring session retains old principal | Proxy logout fails to revoke app session | Stateless mode or session revocation/principal change |
| Client-supplied XFCC | Fake mTLS identity | Mesh strip/overwrite, verified peer cert |
| Public IPv6 listener outside IPv4 firewall | Bypasses IPv4 policy | Dual-stack network policy and tests |
| Unaudited kubectl port-forward RBAC | Admin/API paths can reach backend | Kubernetes RBAC/admission/auditing |
| Proxy outage causes app direct fallback | Breaks authentication boundary | Fail closed; availability plans must never expose backend |
| Proxy workload compromised | Attacker can emit headers | mTLS + hardened proxy, signing, least privilege, detection |

**Evaluate controls as a chain:** if the backend is directly reachable, proxy sanitization is insufficient. If the network blocks direct access yet the proxy lets clients write headers, that is insufficient. If the proxy is clean yet the app grants admin from an unmapped username, that is still insufficient.

## 21. Mandatory negative tests

### Test A — Happy path through the proxy

1. Access the public hostname over HTTPS.
2. Proxy prompts for SSO login if no session exists.
3. After authentication, proxy emits a canonical principal, e.g. user@realm, from a trusted identity store.
4. App checks local account enabled/tenant/authorities and returns only permitted resources.
5. App logs record source service alias/trace ID without logging cookies/raw SSO tokens.
6. Where required, verify the TLS stack validated the mTLS peer proxy identity.

**Pass:** user logs in properly without the client supplying any identity header.

### Test B — Browser sets an identity header itself

1. From an authorized test client, send a request to the public hostname carrying a forged `X-Authenticated-User`.
2. Proxy strips/overwrites the header before forwarding to the backend.
3. No client-supplied principal reaches the app.
4. Unauthenticated users receive login/401/403 per contract.
5. Logged-in users resolve strictly to the proxy-verified identity, never the forged header.

### Test C — Direct backend port from an untrusted source

1. From a pod/host outside the proxy allowlist, attempt to connect to the backend private IP/service in a test environment.
2. Network policies/firewalls must drop/block access **before** the HTTP application.
3. Do not merely check that `curl` returns 403: 403 proves the app received the request; network isolation should prevent connection entirely when proxy-only is required.
4. If mTLS reaches the TLS endpoint without a client cert, the handshake must fail or the reverse proxy must reject before Spring.
5. Record source, port, network policy, and observed outcome.

### Test D — Sibling pod in the same namespace

1. Create a test pod without the identity-proxy label in the same namespace.
2. Attempt TCP to backend port 8080.
3. Must be blocked by the NetworkPolicy selecting the backend.
4. Repeat from another namespace.
5. Audit permissions to alter namespace/pod labels via RBAC/admission.

### Test E — X-Forwarded-For spoofing

1. Send a request through the public proxy with `X-Forwarded-For: 127.0.0.1` or a fake proxy IP.
2. Edge strips/overwrites per policy.
3. App never treats the request as coming from the proxy based on XFF.
4. Client IP logging/rate limiting uses the verified trusted-hop chain.
5. No bypass via `Forwarded: for=...` or `X-Real-IP`.

### Test F — Alternate ingress/NodePort

1. Enumerate all Services, Ingresses, LoadBalancers, hostPorts, hostNetwork, and management ports reaching the backend.
2. Test direct access through each endpoint in test.
3. Unapproved paths must deny.
4. Do not overlook IPv6/dual-stack or DR ingresses.
5. Present the approved inventory to the service/security owner rather than testing just one public URL.

### Test G — Authentication proxy outage

1. Force the test auth-service to return 503 or time out.
2. Proxy must **fail closed**, never forwarding anonymous requests with caller-supplied headers.
3. Backend must not open a public fallback "to temporarily let users in".
4. Users receive actionable error responses; monitoring triggers alerts.
5. For service-specific APIs, fallback is permitted only when a pre-defined independent strong auth mechanism exists.

### Test H — Principal header missing/forged/multi-value

1. Proxy auth-service returns 2xx without a principal header → deny.
2. Empty/whitespace header or header containing newlines/control chars → deny.
3. Aliases `SM_USER`, `Remote-User`, duplicate headers → cannot select a different user.
4. Zero paths allow an unauthenticated user to map to admin.
5. Track error categories without logging raw sensitive header values.

### Test I — Session/logout

1. User A logs in through the proxy, creating a session if the app is stateful.
2. Log out of the identity proxy or switch users at the proxy.
3. App must not continue processing as user A when new requests require revocation/principal-change policy.
4. If A's session intentionally persists briefly, verify revocation SLAs and live authorization.
5. Test multiple tabs, multiple nodes, and HTTP/2 keep-alive.

### Test J — User lacks resource permissions

1. Proxy authenticates a valid user and forwards the right assertion.
2. Spring creates Authentication.
3. Routes/resources belonging to another tenant or requiring higher privileges are denied.
4. Backend never treats "traversed the proxy" as authority to invoke every business method.
5. Distinguish authn failures (401/403 per entry point) from authorization 403.

## 22. Kubernetes: are there non-HTTP paths?

A Kubernetes cluster can have:
- API server handling `kubectl port-forward`;
- Ingress controllers on nodes;
- Sidecars accessing localhost inside pods;
- HostNetwork daemonsets;
- Metrics scrapers;
- Service mesh inbound listeners;
- In-cluster CronJobs;
- Shared debugging namespaces and CI runners.

Hence saying "we applied a NetworkPolicy" is not enough. Procedure:
1. Inventory selected pods/labels/namespaces and service ports.
2. Audit RBAC for who can run `pods/portforward`, `exec`, `patch pod labels`, or launch privileged pods.
3. Enforce admission restrictions for sensitive workloads.
4. Verify actual CNI policy enforcement and hostNetwork exceptions.
5. Separate liveness/readiness endpoints from admin endpoints without allow-all rules.
6. Restrict debug ingresses to port 8080 and IPv6.
7. Use packet-level telemetry/mTLS identities to verify only valid proxy connections occur.
8. When another team deploys a new ingress, require a security review since it can introduce a bypass path.

**`kubectl port-forward` is an authorized Kubernetes API operation**, not public HTTP. A developer with port-forward permissions can reach the backend along a path pod-to-pod NetworkPolicies do not necessarily govern. That is why RBAC/admission/auditing are needed alongside—not instead of—NetworkPolicy.

## 23. TLS termination and Host/redirect poisoning

The proxy terminates TLS on `https://portal.example.org`, while the backend receives private HTTP. If Spring builds absolute URLs from unsanitized `Host` or `X-Forwarded-Host`:
- Redirects may point to a caller-supplied domain;
- OAuth2/SAML callback URLs may break or be hijacked;
- Cookie domains/schemes may be wrong;
- Links in reset/SSO emails may be poisoned;
- Logs may record spoofed client IPs.

Mitigations:
- Fixed public host allowlist at the proxy.
- Proxy strips/overwrites forwarded host/proto/port;
- Enable Spring Boot `server.forward-headers-strategy` only after edge hygiene.
- Verify trusted proxy ranges in Tomcat/NGINX real-IP configurations.
- Use a trusted public base URL for sensitive redirects.
- Never treat `X-Forwarded-Proto=https` as equivalent to real internal TLS.
- Set cookies `Secure/HttpOnly/SameSite` matching the actual flow.
- Validate return-to URLs against open redirects.

With multiple proxies, establish a **formal header provenance convention** instead of letting CDN and ingress concatenate values for the app to guess.

## 24. Operations: detecting direct-access paths

Warning signs:
- Backend receives traffic whose socket peer is not in the proxy workload list.
- Identity headers appear on requests whose peer lacks mTLS.
- Spikes in `PreAuthenticatedCredentialsNotFoundException` or backend authn failures.
- Backend pods reached from unexpected namespaces.
- Direct requests hitting management/8080 ports.
- User authenticated outside the proxy yet the app created an Authentication.
- Frequent alias/duplicate identity headers.
- A new ingress points at the same service without an auth filter.
- A backend service deployment gains an unexpected `type: LoadBalancer` or NodePort.

### Safe logging

Sample event:

~~~json
{
  "event": "proxy_boundary_request_denied",
  "traceId": "req-opaque-001",
  "backend": "portal-api",
  "peerWorkload": "unknown",
  "trustDecision": "UNVERIFIED_SOURCE",
  "pathGroup": "business",
  "result": "DENY"
}
~~~

This is **illustrative data**, not a Spring Security response. Never log raw identity tokens, user cookies, OIDC ID Tokens, Kerberos AP-REQs, client certificate private keys, or full forwarded headers.

Suggested metrics:
- `proxy_handoff_received_total{source="verified-proxy"}`
- `proxy_handoff_denied_total{reason="untrusted-peer"}`
- `proxy_handoff_denied_total{reason="missing-identity"}`
- `proxy_auth_service_error_total`
- `backend_network_policy_denied_total` if CNI/flow logs exist
- `unexpected_direct_connection_total` if network telemetry exists
- `preauth_user_mapping_failure_total`
- `proxy_principal_change_total` when stateful

Never use principal emails or raw client IPs containing sensitive data as high-cardinality metric labels. Protect log access, retention, dashboards, and permissions.

## 25. Troubleshooting common incidents

| Symptom | Likely cause | How to investigate |
| --- | --- | --- |
| Spring sees no principal despite proxy login success | Proxy missing header, wrong NGINX `auth_request_set`, stripped at later hop | Inspect auth-service contract and redacted backend traces |
| Proxy auth fails yet app still returns 200 | Pre-auth bypass, permitAll route, session/basic fallback, alternate ingress | Audit SecurityFilterChain matchers and network paths |
| Direct backend 8080 reachable | SG/firewall/NetworkPolicy unenforced, NodePort, hostNetwork | Test TCP reachability from an untrusted source |
| All requests get 403 after applying NetworkPolicy | Wrong proxy pod/namespace labels, port mismatch, health blocked | Inspect CNI flow logs, selectors, listener ports |
| Backend gets identity from browser header | Edge forwards original header without overwriting | Capture redacted proxy request/response in lab |
| Wrong original URL in OIDC redirect | Forwarded headers mismatch trusted proxy path | Check public host/proto and Boot forwarded strategy |
| Audit IPs all show LB | Missing real-IP trusted peers or XFF overwrite | Check proxy chain, realip_module, Tomcat RemoteIpValve |
| Audit IP chosen by caller | Proxy trusts client-supplied XFF | Strip all forwarded headers at first trusted edge |
| User A session persists after proxy logout | Session policy/revocation/principal-change mismatch | Review stateless vs. stateful, expiration/SLO |
| Backend API returns 403 for valid user | App/object authorization, tenant/roles | Inspect ACLs without loosening proxy allowlists |
| Another pod can attach the proxy label | Overly broad RBAC/admission | Review namespace and label permissions |
| mTLS handshake fails between proxy and backend | Wrong cert/SAN/trust anchor or mesh config | Check workload identity; never disable verification |
| API bearer tokens rejected after enabling pre-auth | Authentication chains mixed | Separate endpoints and issuer/audience contracts |
| Duplicate identity headers | Header normalization/alias handling | Reject/strip and update proxy config |
| Spring filter runs twice | Boot Servlet auto-registration + SecurityFilterChain | Disable via FilterRegistrationBean or use single registration |
| Management port is public | Actuator config/SG/secondary ingress | Isolate management endpoints and test separately |

**Never "fix" direct backend exposure using `server.forward-headers-strategy=framework`.** Forwarded-header handling addresses URL/client metadata, not network isolation.

## 26. Practice: before-and-after configuration review

### Before hardening

~~~text
Internet --> Identity Proxy --> Spring backend:8080
                    |
                    +--> sets X-Authenticated-User

Internet -------------------> Spring backend:8080 (public IP still open)
Client self-sets X-Authenticated-User: admin@example.org
Spring RequestHeaderAuthenticationFilter reads header.
~~~

Here the proxy worked properly on the primary public path, yet the backend **has a direct network path**. The pre-auth framework cannot verify header provenance, leading to identity spoofing.

### After hardening

~~~text
Internet --> Trusted Identity Proxy --> [mTLS] --> Spring backend
                 |
                 +-- Authenticating end user
                 +-- Strips caller identity and forwarded headers
                 +-- Creates verified canonical principal

Non-proxy traffic --> Denied at network/firewall policy
Backend:
  - verifies proxy workload boundary
  - reads only sanitized identity assertion
  - loads user/account state
  - enforces authorization per resource
~~~

**Expected outcome:** bypass requests cannot open connections or create an Authentication; unauthenticated requests via the proxy carry no identity; valid proxy requests map to the right user while remaining constrained by business roles and ACLs.

## 27. Self-check questions with answers

**Q1.** Does Spring Security's `RequestHeaderAuthenticationFilter` authenticate `X-Authenticated-User` itself?

**Answer:** No. It only extracts the username as pre-auth input; trust resides in the external system and network/proxy protections.

**Q2.** The proxy strips headers properly, yet the backend still has a public IP. Is it safe?

**Answer:** Not yet. Callers can bypass the proxy and send headers directly. Network isolation and backend peer verification are required.

**Q3.** Does `X-Forwarded-For: 10.42.7.10` prove the request arrived from proxy IP 10.42.7.10?

**Answer:** No. Callers can forge that header. Trust XFF only from verified proxy hops after stripping/overwriting incoming values.

**Q4.** The Spring app needs public HTTPS URLs even though proxy→app uses HTTP. What handles this and under what condition?

**Answer:** Boot's forwarded-header strategy/`ForwardedHeaderFilter` or container equivalent, **after** the edge strips/overwrites `Forwarded` and `X-Forwarded-*`.

**Q5.** Does `ClusterIP` automatically block all internal pods from calling the backend?

**Answer:** No. Kubernetes NetworkPolicy with CNI enforcement is normally needed, plus mTLS where required.

**Q6.** A NetworkPolicy places `namespaceSelector` and `podSelector` in two separate `from` items. Is that the same as placing both in one item?

**Answer:** No. Two separate items mean OR; put both in the same item to combine namespace and pod selection with AND.

**Q7.** Does Kubernetes NetworkPolicy govern who has permission to run `kubectl port-forward`?

**Answer:** Not guaranteed. Port-forward runs via the Kubernetes API and requires separate RBAC/admission/auditing.

**Q8.** The proxy returns 2xx on `auth_request` yet provides no identity header. What should happen?

**Answer:** Deny/fail closed; never fall back to anonymous or a browser-supplied username.

**Q9.** NGINX uses `proxy_set_header X-Authenticated-User $http_x_authenticated_user`. What is wrong?

**Answer:** That reads the incoming browser value rather than a principal from a verified auth context. Use output from a trusted identity/auth service instead.

**Q10.** Does proxy→backend mTLS replace user authentication?

**Answer:** No. It authenticates the workload peer, while the proxy must still authenticate the end user and the backend must authorize.

**Q11.** The backend sees a client cert subject in XFCC; can it trust that subject by default?

**Answer:** No. You need mesh/edge XFCC sanitization and an authenticated hop, or a client certificate verified directly by the TLS stack.

**Q12.** Why must the actuator port be audited independently?

**Answer:** It may be exposed on a separate management port/ingress, bypassing the auth proxy unless network/auth restrictions apply.

**Q13.** After proxy logout, the Spring session remains authenticated. Is that an XFF bug?

**Answer:** Usually a session/revocation model mismatch. Use per-request pre-auth or session invalidation/principal-change policies rather than blaming XFF.

**Q14.** If the app uses both API token auth and pre-auth headers, must one be disabled?

**Answer:** Not necessarily, though separate security chains/trust boundaries, proper issuer/audience checks, and zero SSO-bypass fallbacks are needed.

**Q15.** Why not treat private `10.0.0.0/8` as a trusted proxy network?

**Answer:** Many other internal workloads live there. Allow only exact approved proxy peers/workload identities.

**Q16.** Does public TLS at the edge protect an HTTP backend from attackers inside the same cluster?

**Answer:** No. Private network isolation and, where appropriate, proxy→backend mTLS are required.

**Q17.** The proxy's mTLS cert is valid, yet the auth service takes `user=admin` from a query parameter. Is that safe?

**Answer:** No. The workload peer was verified, yet **end-user assertion provenance** is broken. The proxy must authenticate the user and map a canonical identity before emitting the header.

**Q18.** If the app has `.permitAll("/health/live")`, can NetworkPolicy open the health port to the whole Internet?

**Answer:** No. `permitAll` applies only at the app layer; network access must still restrict to legitimate health-probe sources.

## 28. Deployment and QA checklist

- [ ] Identified which proxy **actually authenticates users** and creates the identity assertion.
- [ ] Backend has no unintended public routes/IPs/LBs/NodePorts/secondary ingresses.
- [ ] Firewalls/security groups or NetworkPolicy enforce **deny by default** toward the backend.
- [ ] Only approved proxy workloads can connect to backend ports.
- [ ] CNI enforcement, IPv4/IPv6, hostNetwork/NodePort/port-forward have been verified.
- [ ] Kubernetes RBAC/admission protects namespace/pod labels used in allowlists.
- [ ] Where mTLS is required, the backend verifies peer certificates/SANs/workload identities.
- [ ] Proxy strips all incoming identity headers/aliases and rejects duplicates properly.
- [ ] Proxy writes the canonical principal **only after** the auth service returns valid authentication proof.
- [ ] App never trusts `X-Forwarded-For` or `Forwarded` to prove a connection came from the proxy.
- [ ] Forwarded metadata is stripped/overwritten at the trust boundary and handled properly by Boot/container.
- [ ] Spring `RequestHeaderAuthenticationFilter` reads the exact header and maps UserDetails/accounts properly.
- [ ] Pre-auth failures never fall through to unaudited form/basic fallbacks.
- [ ] `RequestHeaderAuthenticationFilter` is not registered twice inside/outside `SecurityFilterChain`.
- [ ] Stateless/session policies, principal-change/revocation, and account disabling are tested.
- [ ] Business authorization by route/tenant/object never relies solely on "passed through proxy".
- [ ] Actuator/health/webhook/WebSocket/legacy endpoints are separately classified and secured.
- [ ] Auth proxy outages or missing identities fail closed without opening direct backend access.
- [ ] Negative tests cover forged identity headers, duplicate headers, untrusted peers, and mTLS mismatches.
- [ ] Tested sibling pods, other namespaces, bypass networks, IPv6, and management ports.
- [ ] Auditing/metrics track attempted direct traffic and auth-header anomalies without logging credentials.
- [ ] Rollout/rollback plans preserve the proxy-only invariant throughout deployments.
- [ ] Error responses for 401/403/503 distinguish auth failures, authorization failures, and dependency outages.

## 29. Conclusion

For **proxy authentication**, Spring Security pre-authentication should handle **only identities already verified by a trusted proxy and delivered over a protected channel**. Because `RequestHeaderAuthenticationFilter` does not validate headers itself, **any direct connection path to the backend is a critical authentication bypass**.

A secure design requires **multiple simultaneous layers**:

1. **Block direct backend access on the network**: private endpoints, firewalls/security groups, or enforced Kubernetes NetworkPolicies.
2. **Authenticate the proxy workload**: mTLS/identity-aware peer controls on the proxy→backend path when needed.
3. **Protect header provenance**: strip/overwrite all incoming identity/forwarded headers, emitting assertions solely from an authenticated user context.
4. **Fail-closed Spring pre-auth**: no unintended authentication fallbacks; controlled UserDetails and session policies.
5. **Authorization and monitoring**: account/tenant/object permissions, real bypass testing, session revocation, and anomaly alerting.

**An identity header is not a trustworthy credential merely because it contains the word "Authenticated".** It carries value only when network, proxy, and application boundaries all uphold the trust contract.

### Official documentation

1. Spring Security — Pre-Authentication Scenarios and Request Header Authentication (header spoofing warning): https://docs.spring.io/spring-security/reference/servlet/authentication/preauth.html
2. Spring Security — RequestHeaderAuthenticationFilter Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/preauth/RequestHeaderAuthenticationFilter.html
3. Spring Security — AbstractPreAuthenticatedProcessingFilter (fallback, principal change): https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/preauth/AbstractPreAuthenticatedProcessingFilter.html
4. Spring Framework — Servlet ForwardedHeaderFilter and security considerations: https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html
5. Spring Security — HTTP security and forwarded header trust: https://docs.spring.io/spring-security/reference/features/exploits/http.html
6. Spring Boot — Embedded Web Servers/Forwarded Headers: https://docs.spring.io/spring-boot/reference/how-to/webserver.html
7. Kubernetes — NetworkPolicy, default deny ingress and selector semantics: https://kubernetes.io/docs/concepts/services-networking/network-policies/
8. NGINX — Reverse Proxy, proxy_set_header and suppress header by empty value: https://docs.nginx.com/nginx/admin-guide/web-server/reverse-proxy
9. NGINX — ngx_http_proxy_module: https://nginx.org/en/docs/http/ngx_http_proxy_module.html
10. NGINX — ngx_http_realip_module, set_real_ip_from trusted peers: https://nginx.org/en/docs/http/ngx_http_realip_module.html
11. NGINX — ngx_http_auth_request_module: https://nginx.org/en/docs/http/ngx_http_auth_request_module.html
12. RFC 7239 — Forwarded HTTP Extension: https://www.rfc-editor.org/rfc/rfc7239.html
