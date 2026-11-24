# Reverse Proxies, Rewritten Paths, and Trusted Forwarded Metadata

> **Module:** Spring Security – authorization  
> **Group:** Request context  
> **Focus:** Requests passing through a reverse proxy/load balancer/gateway can have their path, scheme, host, port, and IP address changed. Authorization must apply to **the request Spring Security actually sees**, while `Forwarded` and `X-Forwarded-*` may be used only after the trust boundary is enforced.

## 1. Situation: External URL Differs from the URL Spring Receives

Suppose a client calls the API:

~~~http
GET https://shop.example/portal/api/admin/users
~~~

Infrastructure consists of an HTTPS reverse proxy placed in front of a Spring Boot app running HTTP inside a private network:

~~~text
Client/browser
    |
    | GET https://shop.example/portal/api/admin/users
    v
Trusted edge proxy / ingress
    |  - terminates TLS
    |  - validates host and routes
    |  - strips public prefix "/portal"
    |  - replaces untrusted Forwarded/X-Forwarded-*
    |
    | GET http://app:8080/api/admin/users
    | X-Forwarded-Host: shop.example
    | X-Forwarded-Proto: https
    | X-Forwarded-For: 198.51.100.42
    | X-Forwarded-Prefix: /portal   (if needed for public links)
    v
Spring Boot / Spring Security
    |
    +--> SecurityFilterChain / RequestMatcher
    +--> Authentication / AuthorizationManager
    +--> Controller / Service
~~~

In this **specific** example, the proxy actually changed the path from `/portal/api/admin/users` to `/api/admin/users`. If authorization configuration checks only a matcher based on the **public path** `/portal/api/admin/**` while the matcher receives the upstream path `/api/admin/**`, the admin rule may fail to match. Worse, a broad `authenticated()` rule or a `SecurityFilterChain` lacking a fallback can let the request be processed under a weaker policy than intended.

Conversely, the application needs to know the public URL is `https://shop.example/portal/...` to generate redirects and absolute URLs accurately. That is why `Forwarded`/`X-Forwarded-*` headers exist.

**Two problems must be solved simultaneously yet separately:**

1. **Path/routing correctness:** matchers protect the exact path the servlet/security layer receives after proxy rewrites and any active wrappers/filters.
2. **Metadata trust:** accept host, protocol, port, client address, and public prefix only from a trusted proxy, **never trusting client-crafted headers**.

Adding `X-Forwarded-Proto: https` is not user authentication; setting `X-Forwarded-Prefix: /portal` also does not automatically perform path rewriting in a reverse proxy.

## 2. One HTTP Request Has Multiple "Views" of the URL

Distinguish the data layers:

| Attribute | Example in scenario | Source / meaning |
|---|---|---|
| Public URL | `https://shop.example/portal/api/admin/users` | URL called by the client |
| Public scheme | `https` | Connection client → edge proxy |
| Public host | `shop.example` | Domain accepted by the gateway |
| Public prefix | `/portal` | Prefix that the gateway may strip when forwarding |
| Upstream URL | `http://app:8080/api/admin/users` | Connection edge → application |
| Backend path | `/api/admin/users` | Path received by the container in this example |
| `contextPath` | Usually empty if app deploys at root | Servlet application context; may be modified by wrappers per forwarded-prefix |
| `servletPath` / `pathInfo` | Depends on servlet mapping | Servlet fields used for routing/matchers |
| `requestURI` | Usually contains path per upstream request and context path | Not automatically synonymous with public URI |
| `getScheme()`, `getServerName()` | May be `http`/`app` if forwarded headers are not processed | Current request values; may be handled by wrapper/container |
| Client IP observed at backend | Proxy address | Not necessarily the end client IP |

Servlet getters do not always share one single shape. Spring MVC and Spring Security may use different `RequestMatcher`/`HandlerMapping` mechanisms depending on version, servlet mapping, and configuration. Specifically, `getRequestURI()`, `getContextPath()`, `getServletPath()`, and `getPathInfo()` are not arbitrarily interchangeable.

**Important rule:** Never write authorization by guessing strings from public URLs. Measure/test requests **after the proxy infrastructure and relevant filters/wrappers**, then configure matchers according to the semantics of the API in use. Avoid logging headers containing credentials or tokens while diagnosing.

## 3. What Can a Reverse Proxy Change?

A proxy, API gateway, or ingress can:

- Terminate TLS at the edge and continue internally over HTTP.
- Replace the public `Host` with an upstream/internal hostname (or preserve host per config).
- Add/strip/replace path prefixes.
- Rewrite `/public/api/**` to `/api/**`, or change version `/v2/**` to another upstream path.
- Add request origin metadata via `Forwarded`/`X-Forwarded-*`.
- Route multiple public hosts to one backend, or one host to multiple services.
- Restrict network access, authenticate callers at the gateway, rate-limit, or normalize URLs.
- Add request IDs/hop IDs for tracing (which does not mean those values are trustworthy).

### 3.1. Three Common Rewrite Patterns

~~~text
A. Strip prefix:
  public:  /portal/api/orders/42
  backend: /api/orders/42

B. Keep path intact:
  public:  /portal/api/orders/42
  backend: /portal/api/orders/42

C. Replace prefix:
  public:  /service-a/orders/42
  backend: /internal/v1/orders/42
~~~

The three scenarios have **different upstream paths**, so a `requestMatchers("/portal/api/**")` cannot be declared always right or always wrong without knowing how the gateway actually rewrites.

Every deployment must have a **routing contract**: public host/path/method → upstream service/path/method, header-forwarding behavior, trust boundary, and verification mechanism. This contract must be tested from outside the gateway, not only by testing controllers with MockMvc.

### 3.2. Rewrites Can Cause "Permissions Mismatching Controller" Bugs

Suppose a controller mapping is:

~~~java
@GetMapping("/api/admin/users")
public List<UserDto> users() {
    // ...
}
~~~

And the proxy strips `/portal`. If the HTTP rule says:

~~~java
.requestMatchers("/portal/api/admin/**").hasRole("ADMIN")
.anyRequest().authenticated()
~~~

in a context where the matcher matches the upstream path `/api/admin/users`, the admin rule fails to match and the request falls into `authenticated()`. A logged-in regular user **could bypass HTTP authorization** to call the controller if no other tight safeguard exists. This is an example of **vertical privilege escalation** from wrong path assumptions.

**Fix in the upstream architecture above:** matchers must cover the URL seen by security, such as `/api/admin/**`, with integration tests proving the right chain/rule matches. Do not merely change regexes/patterns without checking whether a forwarded-prefix wrapper or servlet context alters how path matchers evaluate.

## 4. Forwarded Headers: Describing the Client-Facing Request

Two common header families:

1. **`Forwarded`**: header standardized by RFC 7239, containing components like `for=`, `proto=`, `host=`; may contain multiple entries for multiple hops.
2. **`X-Forwarded-*`**: widely used de facto headers set by proxies/gateways.

Example:

~~~http
Forwarded: for=198.51.100.42;proto=https;host=shop.example
~~~

Or separate headers:

~~~http
X-Forwarded-For: 198.51.100.42
X-Forwarded-Proto: https
X-Forwarded-Host: shop.example
X-Forwarded-Port: 443
X-Forwarded-Prefix: /portal
~~~

| Header | Common purpose | Must not be inferred |
|---|---|---|
| `Forwarded` | Describes host/proto/for of request through proxy | That the header is inherently trusted or signed |
| `X-Forwarded-For` | Describes source address and potentially multiple hops | That the first element is definitely the real client IP |
| `X-Forwarded-Proto` | Public scheme, typically `https` | That the client actually used HTTPS if self-sent |
| `X-Forwarded-Host` | Public host | That the host is on the allowed domain list |
| `X-Forwarded-Port` | Public port, e.g., `443` | That port alone proves safe TLS |
| `X-Forwarded-Prefix` | Public URL prefix, useful for URL generation | That proxy rewrote paths right or matchers automatically adapt |
| `X-Real-IP` | Header used by some proxies to pass IP | A universal standard trusted automatically by Spring in all configs |

**They are merely HTTP data until the trust boundary verifies their source.** Requests from the Internet can send any header, including `Forwarded`, `X-Forwarded-Host`, `X-Forwarded-For`, and `X-Forwarded-Proto`.

### 4.1. Relationship Between `X-Forwarded-Prefix` and Rewritten Paths

Spring Framework supports `X-Forwarded-Prefix` for situations where a public prefix is replaced, stripped, or added when passing through a proxy. Example:

~~~text
Public:  https://shop.example/portal/api/orders/42
Backend: http://app:8080/api/orders/42
Proxy:   X-Forwarded-Prefix: /portal
~~~

When the application **actively processes this trusted header**, the framework can use the public prefix to build accurate links/redirects. However, **the header does not replace the reverse proxy's rewrite operation**; if the proxy sends the wrong upstream path, adding the header does not fix controller mappings or security policies.

Furthermore, wrappers applying the prefix can alter how the request is presented in the Servlet API. Therefore **do not conclude every RequestMatcher always sees `/api/**` or always sees `/portal/api/**`** from an external example alone. Verify your exact framework version, container, filter chain, and real endpoints.

## 5. Trust Boundary: Why Can Forwarded Data Be Dangerous?

Suppose a client sends:

~~~http
GET /portal/api/admin/users HTTP/1.1
Host: shop.example
X-Forwarded-Host: evil.example
X-Forwarded-Proto: https
X-Forwarded-For: 127.0.0.1
~~~

If the reverse proxy **forwards those values verbatim** and the application treats them as truth:

- The app may generate links or redirects pointing to `evil.example`.
- "Require HTTPS" checks may be misled by a forged `proto=https`.
- IP allowlist rules may be bypassed by trusting a client-claimed `127.0.0.1`.
- Audit logs/rate limits may misidentify the client.
- Custom headers like `X-Authenticated-User`, if treated by the app as authenticated identity, can create severe vulnerabilities.

**A framework cannot tell on its own whether a header was added by a trusted proxy or sent by a malicious client.** Therefore primary responsibility rests on the **edge proxy at the entry point of the trusted network**.

### 5.1. Minimum Trust Boundary Policy

1. **Disallow direct Internet connections to the backend** except authorized paths. Use firewalls/security groups/private networks and mTLS between proxy and application where appropriate.
2. **At the trusted edge, strip/overwrite all client-sent forwarded headers**, including both standard `Forwarded` and `X-Forwarded-*`. Write only values the proxy directly observed or verified.
3. **Accept only configured public hosts**; never pass arbitrary client hosts through as trusted forwarded hosts.
4. **Trust only controlled hops**: with multiple proxies, explicitly define which proxies may append, forward, or canonicalize earlier hops.
5. **Restrict trusted proxy addresses** in the container/ingress when forwarded handling depends on network addresses.
6. **In the app, enable forwarded-header handling only after a proper trust boundary exists**. A header-processing filter does not make headers safe on its own.
7. **Never turn forwarded metadata into identity**. Authentication must rely on sessions/JWT/mTLS/IdP or a fully protected gateway delegation mechanism.

A concise mental model:

~~~text
Internet (do not trust headers)
    |
    v
TRUST BOUNDARY at the edge
    - drop all inbound Forwarded/X-Forwarded-*
    - validate public host and TLS state
    - extract observed client IP or via trusted hop chain
    - write canonical headers for backend
    |
    v
Private upstream (trusts only the right proxy)
    |
    v
Spring app with appropriate forwarded-header handling
~~~

**Stripping only `Forwarded` while leaving `X-Forwarded-*`, or vice versa, is insufficient**: different libraries can read different header families. Handle both at the trust boundary.

## 6. Forwarding Headers Are Not Authentication, Authorization, or Internal Proof

Three common misconceptions:

**A. `X-Forwarded-For: 127.0.0.1` does not prove a request came from localhost.** Clients on the Internet can send that string if the edge does not sanitize. If an app reads `request.getHeader("X-Forwarded-For")` and grants admin roles to "internal" IPs, that is a design flaw.

**B. `X-Forwarded-Proto: https` does not prove the client transport is protected when headers are untrusted.** It is useful only after the proxy verified real TLS. The app cannot replace TLS enforcement with a string comparison.

**C. `X-Forwarded-Host: admin.example` does not prove the user has rights on that tenant/admin host.** Host-based routing can be part of an architecture, yet requires a trusted host allowlist and principal authentication/authorization. Never map client-supplied hosts into permissions.

In "gateway authenticates on behalf of backend" architectures, headers like `X-Authenticated-User` or `X-User-Roles` sometimes appear. Those are not standard forwarded metadata. If the app accepts them for authentication, it must enforce **connections strictly from the authenticated gateway**, strip client headers, validate format/identity, audit, and enforce anti-bypass controls. Without those conditions, **do not trust them**.

## 7. How Does Spring Boot Handle Forwarded Headers?

In Spring Boot 3.x Servlet, the property:

~~~properties
server.forward-headers-strategy=framework
~~~

selects how the framework handles forwarded headers. Common options:

| Value | General meaning | What to check |
|---|---|---|
| `none` | Do not use Boot's forwarded-header handling | App/server performs no unintended extra processing |
| `native` | Use the web server/container's native mechanism | E.g., Tomcat `RemoteIpValve`; support for headers/prefixes varies by container |
| `framework` | Use Spring Framework's mechanism | For Servlet, `ForwardedHeaderFilter`; for reactive, a different mechanism |
 
**No single option fits every deployment.** Choose based on Boot version, container, proxy configuration, and application goals. Spring Boot can have different defaults depending on environment/cloud platform: **do not rely on unverified defaults** in production.

Example using framework handling where **proxy safety is already ensured**:

~~~properties
# application.properties: enable only after edge sanitizes headers.
server.forward-headers-strategy=framework
~~~

If using container native:

~~~properties
# Suitable when container is configured to trust proxies properly.
server.forward-headers-strategy=native
~~~

If not behind a trusted proxy or wanting to disable forwarded headers:

~~~properties
server.forward-headers-strategy=none
~~~

**Do not enable `native` while also manually registering an extra `ForwardedHeaderFilter` without clear reason and tests.** Double-processing/wrapping can make URLs, redirects, or trust models unpredictable. Pick **one strategy** and verify outcomes on real requests.

### 7.1. When to Use ForwardedHeaderFilter?

Spring Framework's `ForwardedHeaderFilter` processes `Forwarded` or `X-Forwarded-*` values and wraps the request/response so downstream components see a view aligned with the client-facing URL. Depending on version, it handles host, port, scheme, redirects, prefixes, and related fields.

If using the framework-configured filter, its order must ensure components needing normalized data **see the wrapped request**. Spring Framework documentation requires placing the filter ahead of relevant downstream filters; with some manual registrations you must also consider `ASYNC` and `ERROR` dispatcher types.

**Version note:** APIs selecting standard vs. `X-Forwarded-*` headers and `X-Forwarded-Prefix` behavior have changed across newer Spring Framework versions. Never copy a constructor/setting from another version assuming it exists on your dependency. Check the Javadoc and official docs of the version you use.

### 7.2. `removeOnly`: Strip Without Trusting

When you do not want to apply forwarded metadata yet need to strip them before downstream logic, `ForwardedHeaderFilter` offers `removeOnly` mode:

~~~java
ForwardedHeaderFilter filter = new ForwardedHeaderFilter();
filter.setRemoveOnly(true);
~~~

This is an **illustrative Spring Framework 6.x Servlet snippet**, not a standalone JDK program. Construction in newer versions may differ; this only illustrates `removeOnly` semantics. It removes the headers from the request view without treating client-sent headers as the true host/proto.

However, **`removeOnly` does not replace edge header stripping** and does not stop an upstream proxy from mistakenly trusting them. Avoid stacking multiple header-processing filters without understanding ordering.

## 8. Configuring Proxies by Contract Instead of Guesswork

An illustrative proxy contract:

~~~text
Allowed public hostname:
    shop.example
Client protocol:
    HTTPS; external HTTP must redirect at gateway
Public path:
    /portal/api/**
Upstream path:
    /api/**
Proxy rewrite:
    strip /portal
Upstream connection:
    private network only; backend is not public
Forwarding:
    strip Forwarded and all X-Forwarded-* from client
    set X-Forwarded-Host = allowlisted host (shop.example)
    set X-Forwarded-Proto = client scheme actually observed by proxy
    set X-Forwarded-Port = 443
    set X-Forwarded-For = verified source address
    set X-Forwarded-Prefix = /portal if app needs to generate public URLs
Fallback:
    unknown host/path -> proxy does not forward to sensitive app
Logging:
    log request ID and routing outcome, mask credentials/tokens
~~~

This is **pseudoconfiguration for architectural review**, not paste-and-run Nginx/Envoy/Kubernetes syntax. In Nginx, trailing slashes in `proxy_pass`, `location`, `rewrite`, and `real_ip` make real differences; in ingress controllers, annotations and version-specific behaviors apply. Always verify real configs in staging rather than comparing pseudocode alone.

**Special note:** if the edge preserves client `Host` and writes `X-Forwarded-Host` from it, that is still untrustworthy without a **host allowlist** step. Stripping spoofed headers while accepting arbitrary hosts still risks host-header poisoning.

## 9. Configuring Authorization Against Verified Upstream Paths

Suppose integration tests confirm security matchers see `/api/admin/**` on the backend after rewriting. A Servlet configuration might look like:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class BackendAuthorizationConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("order:read")
                .requestMatchers(HttpMethod.GET, "/api/public/**")
                    .permitAll()
                .anyRequest().denyAll()
        );

        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
~~~

**This is a configuration class inside a Spring Boot/Spring Security project**, not a standalone Java program. It assumes the backend runs under the right context, matchers actually receive paths per the tested contract, and the authentication provider properly grants `ROLE_ADMIN`/`order:read`.

Important:

- `/api/admin/**` precedes broader rules; only principals with default `ROLE_ADMIN` pass the HTTP rule.
- `GET /api/orders/**` requires `order:read` authority, yet the service still checks each order's owner/tenant.
- Only `GET /api/public/**` is public in HTTP rules; POST does not automatically inherit it.
- `anyRequest().denyAll()` closes undeclared URLs **in the selected chain**.
- `httpBasic` only illustrates an authentication mechanism; production needs HTTPS, credential providers, and client-appropriate CSRF/session policies.
- **Do not write `/portal/api/admin/**` merely because client URLs have `/portal`** if matchers in your tested deployment receive upstream `/api/admin/**`.
- If using `ForwardedHeaderFilter` with a prefix wrapper, re-test `requestMatchers` semantics with your exact container/framework; never deduce from a fixed example string.

### 9.1. Distinguishing securityMatcher and requestMatchers

When splitting multiple chains:

~~~java
http.securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated());
~~~

`securityMatcher` decides **whether the entire chain is selected**; `requestMatchers` only decides rules **after the chain has been selected**.

For instance, `/internal/debug` does not match `securityMatcher("/api/**")`, so `anyRequest().authenticated()` inside the API chain **does not protect** `/internal/debug`. Without an appropriate fallback chain, that request can fall outside Spring Security's filter chain. Systems with proxy rewrites must check this case especially carefully.

Multi-chain configurations should place an unrestricted fallback chain last:

~~~java
@Bean
@org.springframework.core.annotation.Order(99)
SecurityFilterChain fallback(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
            .anyRequest().denyAll());
    return http.build();
}
~~~

The snippet assumes it sits in a configuration class while specialized chains have higher precedence (`@Order`). If the app has public URLs in the fallback, add an intentional narrow allowlist and test it. Never put a catch-all `permitAll` ahead of an admin chain.

## 10. Side Effects Beyond RequestMatcher

Wrong forwarded info does not merely make routing/security hard to debug. It can also impact:

### 10.1. Redirects and Absolute URLs

Spring may generate absolute URLs for redirects, password resets, verification emails, pagination links, or OAuth/OIDC callbacks. If `X-Forwarded-Host` is spoofed, the app can build links pointing to an attacker's domain; that is **host-header poisoning** and can become a severe vulnerability depending on the flow.

Defense: public host allowlist at the proxy; choose the right forwarded handling; never use untrusted hosts to build security links. Critical callback/redirect URIs should be registered/allowlisted in configuration rather than assembled from arbitrary request hosts.

### 10.2. HTTP/HTTPS, Secure Cookies, and HSTS

If TLS terminates at the gateway, the backend receives HTTP. If it does not know the public request was HTTPS, redirects and URL generation can produce `http://...`, or cookie attributes and security policies can be misconfigured.

Conversely, **a client-entered `X-Forwarded-Proto: https` header is not proof of TLS**. The edge must verify the actual protocol. HSTS must be sent appropriately for client-facing HTTPS responses per architecture. Cookie `Secure`/`SameSite` attributes and CSRF/session strategies must be configured and tested through the real proxy and browser.

### 10.3. Rate Limits, IP Allowlists, and Audits

If the app reads `X-Forwarded-For` directly and takes the first IP:

~~~java
// Do not use for trust decisions:
String clientIp = request.getHeader("X-Forwarded-For");
~~~

an attacker can supply `X-Forwarded-For: 127.0.0.1` if the edge does not strip it. Even with multiple IPs, the first value does not prove the real source. Use a **trusted proxy chain**/container logic configured with exact proxy IP ranges, or take the IP from a gateway guaranteeing integrity. Sensitive controls should not rely solely on IP; prefer strong authentication/authorization and proper edge rate limiting.

### 10.4. Host-Based Routing and Multi-Tenancy

Some apps use subdomains like `tenant-a.shop.example` and `tenant-b.shop.example` to choose tenants. Selecting a tenant solely from client-supplied `Host`/`X-Forwarded-Host` can assign requests to the wrong scope.

Bind **allowlisted hosts, session/principal, and tenant membership**, checking permissions on resources. Host can assist routing, yet never proves a user belongs to a tenant.

## 11. Multi-Proxy Chains: X-Forwarded-For Is Not Simply One IP

An architecture may look like:

~~~text
Client
   |
   v
CDN
   |
   v
External load balancer
   |
   v
Ingress
   |
   v
Spring app
~~~

If each hop appends to `X-Forwarded-For`, multiple comma-separated addresses can appear. The first element can be spoofed client data **if the first edge failed to strip inbound values**.

Deployment rules:

1. Identify which hop is the first **edge trust boundary**.
2. The edge strips/overwrites headers from the Internet, keeping only IP values it trusts from transport or a verified preceding proxy.
3. Each internal hop accepts forwarded metadata only from authorized proxies.
4. Container/ingress must know the **trusted proxies** range; never configure "trust all" in production.
5. When both `Forwarded` and `X-Forwarded-*` exist, pick a consistent policy on the preferred header family and drop unused ones.
6. Test bypassing a proxy, spoofing IPs, or calling the backend directly: trust mechanics must reject or distrust the headers.

If the app has a public direct connection, all proxy sanitization rules can be **bypassed**. Hence network isolation is just as critical as application configuration.

## 12. Standalone Java 17: Simulating Trusted Edge, Rewrite, and Admin Rule

This example uses **plain Java**, simulating one specific scenario: a trusted edge strips prefix `/portal`, **discards fake client forwarded headers**, and sets metadata from verified facts. The app protects `/api/admin/**` with login + admin role.

**This is only a simulation**, not a proxy/Spring Security implementation. The `startsWith` checks are intentionally simple to illustrate paths; real environments must use tested gateway routing and `RequestMatcher`/authorization infrastructure.

Save file `ProxyBoundaryDemo.java`:

~~~java
public class ProxyBoundaryDemo {
    record ClientRequest(
            String publicPath,
            String clientForwardedHost,
            String clientForwardedProto,
            String clientForwardedFor) {}

    record UpstreamRequest(
            String path,
            String forwardedHost,
            String forwardedProto,
            String forwardedFor) {}

    static UpstreamRequest trustedEdge(
            ClientRequest client, String observedRemoteIp) {
        if (!client.publicPath().startsWith("/portal/")) {
            throw new IllegalArgumentException("Unexpected external route");
        }
        String backendPath =
                client.publicPath().substring("/portal".length());
        return new UpstreamRequest(
                backendPath,
                "shop.example",
                "https",
                observedRemoteIp);
    }

    static boolean adminMatcher(String path) {
        return path.startsWith("/api/admin/");
    }

    static String adminAuthorization(
            String path, boolean authenticated, boolean admin) {
        if (!adminMatcher(path)) {
            return "NOT_ADMIN_RULE";
        }
        return authenticated && admin ? "ALLOW" : "DENY";
    }

    public static void main(String[] args) {
        ClientRequest client = new ClientRequest(
                "/portal/api/admin/users",
                "evil.example",
                "http",
                "127.0.0.1");

        UpstreamRequest upstream =
                trustedEdge(client, "198.51.100.42");

        System.out.println("external path: " + client.publicPath());
        System.out.println("backend path: " + upstream.path());
        System.out.println("wrong external matcher: "
                + upstream.path().startsWith("/portal/api/admin/"));
        System.out.println("correct backend matcher: "
                + adminMatcher(upstream.path()));
        System.out.println("client fake host: "
                + client.clientForwardedHost());
        System.out.println("trusted forwarded host: "
                + upstream.forwardedHost());
        System.out.println("trusted forwarded proto: "
                + upstream.forwardedProto());
        System.out.println("trusted forwarded for: "
                + upstream.forwardedFor());
        System.out.println("ordinary user: "
                + adminAuthorization(upstream.path(), true, false));
        System.out.println("admin user: "
                + adminAuthorization(upstream.path(), true, true));
        System.out.println("backend direct access: REJECT");
    }
}
~~~

Compile with Java 17:

~~~bash
javac --release 17 ProxyBoundaryDemo.java
java ProxyBoundaryDemo
~~~

Verified output:

~~~text
external path: /portal/api/admin/users
backend path: /api/admin/users
wrong external matcher: false
correct backend matcher: true
client fake host: evil.example
trusted forwarded host: shop.example
trusted forwarded proto: https
trusted forwarded for: 198.51.100.42
ordinary user: DENY
admin user: ALLOW
backend direct access: REJECT
~~~

Explanation:

- Lines 1–2: same request, yet **public path** and **upstream path** differ.
- Lines 3–4: the public-prefix matcher fails in this upstream scenario; the matcher against the path the backend actually receives matches.
- Lines 5–8: the client sent `evil.example`, `http`, `127.0.0.1`, yet the edge ignored them and set host/protocol/IP from verified sources.
- Lines 9–10: an admin rule still checks authentication and role; matching a path/regex grants no privileges.
- Final line: rejecting direct backend access is an **assumed network policy**, not an automatic feature of Java or Spring Security.

The value `198.51.100.42` is a documentation sample address and does not belong to any real customer.

## 13. Testing: Must Cover Both the Proxy and Spring Security

Testing only `MockMvc` inside the app cannot prove the edge strips headers and rewrites paths properly. Split into **three test layers**:

1. **Unit/component tests:** verify `RequestMatcher`, route/role rules, URL builders, and parsers in the app.
2. **Spring integration tests:** through the Servlet filter chain, method security, authentication providers; verify matchers, handlers, and statuses.
3. **End-to-end through gateway/staging:** send requests from outside the trust boundary with both valid and spoofed headers, observing upstream paths and safe responses.

### 13.1. Mandatory Matrix for Path Rewrites

| Client request | Expected upstream path | Required policy |
|---|---|---|
| `GET /portal/api/admin/users` | `/api/admin/users` | Admin only; regular users denied |
| `GET /portal/api/orders/42` | `/api/orders/42` | `order:read` + owner/tenant |
| `POST /portal/api/orders/42` | `/api/orders/42` | Separate POST policy, does not inherit GET |
| `GET /portal/api/public/faq` | `/api/public/faq` | Intentionally public |
| `GET /portal/internal/debug` | `/internal/debug` or gateway denies | Must not fall into public API |
| `GET /portal/api/admin/users/` | Per real rewrite | No bypass via trailing slash |
| `GET /portal//api/admin/users` | Per firewall/proxy | Reject or handle consistently |
| `GET /portal/api/%61dmin/users` | Per real decoding/routing | No bypass of admin rule |
| Request outside `/portal/**` | Not routed to sensitive backend | Denied by gateway or fallback |

This is an **expected table for a proxy stripping `/portal`**. If your deployment picks another rewrite, adapt the table to the real contract and test it. URLs with encoded slashes, semicolons, or dot segments should not be casually "allowlisted"; tests must confirm consistent canonicalization across proxy and application.

### 13.2. Header-Spoofing Matrix

| Test | Expected behavior |
|---|---|
| Client sends `X-Forwarded-Host: evil.example` | App **does not** use evil host as public URL |
| Client sends `Forwarded: host=evil.example;proto=https` | Edge strips/overwrites; not trusted |
| Client sends `X-Forwarded-Proto: https` when no real TLS exists | Gateway prevents fooling HTTPS policy |
| Client sends `X-Forwarded-For: 127.0.0.1` | Cannot bypass IP allowlist |
| Client sends `X-Forwarded-Prefix: /admin` | Cannot alter routing or permissions |
| Client sends conflicting `Forwarded` and `X-Forwarded-*` | Consistent canonicalization policy, no ambiguous order dependency |
| Client calls backend IP:port directly | Blocked at network layer or headers distrusted |
| Multiple hops, one hop untrusted | Untrusted hop never used to determine identity/IP |
| Proxy sends valid host/scheme/prefix headers | App builds valid public redirects/links |
| Proxy sends missing/bad headers | Fail-safe behavior, monitoring detects, no privilege expansion |

**Do not assert only status `403` on a non-existent endpoint.** A route with no controller may return 404 even if unprotected by a security chain. Tests must have real endpoints and verify authorization/response bodies, or confirm `FilterChainProxy` picks the right chain.

### 13.3. MockMvc for Testing Backend Rules

Assuming the app has a real `GET /api/admin/users` endpoint and matching `SecurityFilterChain`, a Spring MVC test can be written:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BackendSecurityTest {
    @Autowired
    MockMvc mvc;

    @Test
    void normalUserCannotReadAdminEndpoint() throws Exception {
        mvc.perform(get("/api/admin/users")
                .with(user("lan").roles("USER")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanPassHttpRule() throws Exception {
        mvc.perform(get("/api/admin/users")
                .with(user("admin").roles("ADMIN")))
            .andExpect(status().isOk());
    }
}
~~~

This is an **integration test in a project with Spring Security Test**, requiring a real controller returning 200 and proper dependencies. It tests rules on backend path `/api/admin/users`, **not proving the external proxy actually rewrites `/portal` and sanitizes forwarded headers**. Add end-to-end tests through the edge for that.

When building tests for `X-Forwarded-Prefix`, `X-Forwarded-Host`, and `X-Forwarded-Proto`, verify the filter/framework is actually registered in MockMvc/test runtime. Passing a header on a mock request **does not reproduce** gateway validation and header overwriting.

## 14. Debugging in Multi-Layer Proxy Environments

When facing 404, 401/403, wrong-host redirects, or browser cookie warnings, proceed in order:

1. **Identify the public URL:** scheme, host, path, method, port, query from browser/client.
2. **Inspect gateway routing:** which service/backend was selected; was a prefix stripped/rewritten? Are hostnames and route ordering right?
3. **Inspect trust boundary:** did the edge strip inbound `Forwarded` and all `X-Forwarded-*`? Does the backend accept traffic only from trusted proxies?
4. **Verify upstream request:** what actual path/method reaches Servlet? Is there additional path normalization, decoding, or rewriting?
5. **Inspect Servlet fields:** `requestURI`, `contextPath`, `servletPath`, `pathInfo`, and `getScheme()/getServerName()/getServerPort()` after filter processing.
6. **Check forwarding mode:** is `server.forward-headers-strategy` actually `none`, `native`, or `framework`? Are native/duplicate filters active?
7. **Check chain coverage:** which `SecurityFilterChain` does `securityMatcher` select? Is there a final fallback chain?
8. **Check rule order:** did the URL match a broad `permitAll`/`authenticated` rule before an admin/role rule?
9. **Check authentication:** are principal, authorities, and method/object policy checks accurate?
10. **Check response URLs/cookies:** do redirect `Location`, host, scheme, prefix, and `Set-Cookie` `Secure`/`SameSite` match the public request?
11. **Check data records:** users with the right role yet different tenant/owner must be denied.
12. **Run negative tests:** spoof host/proto/IP/prefix, direct-backend access, encoded/trailing-slash paths, and multi-hop requests.

### Safe Logging

In test/staging environments, you can enable narrowly scoped Spring Security logs:

~~~properties
logging.level.org.springframework.security.web.FilterChainProxy=DEBUG
logging.level.org.springframework.security.web.access.intercept=DEBUG
~~~

Actual log levels and messages depend on version. Never log tokens, session cookies, credentials, PII, or full forwarded chains containing sensitive data. Do not leave DEBUG/TRACE running long-term in production without strict controls.

Distinguish **gateway 404** (no route), **MVC 404** (no handler), **Spring Security 401/403**, **CSRF 403**, and **object-policy 403/404**. Each has a different root cause.

## 15. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Writing matchers with public path while proxy strips prefix | Admin rule fails to match or hits weaker rule | Test upstream path and real matchers |
| Believing `X-Forwarded-Prefix` performs path rewriting itself | Wrong controller/security routing | Configure gateway rewrite and framework handling separately |
| Accepting client-supplied forwarded headers | Host/proto/IP spoofing | Strip at edge and set trusted values |
| Stripping only `Forwarded`, leaving `X-Forwarded-*` | Other libraries still trust spoofed values | Handle both header families |
| Allowing direct calls to backend | Bypasses gateway trust boundary | Private network, firewall/mTLS |
| Treating first `X-Forwarded-For` as real IP | Bypasses IP allowlists/rate limits | Trusted proxy chain, avoid ad-hoc parsing |
| Trusting `X-Forwarded-Host` to select tenant | Cross-tenant data exposure | Host allowlist + principal/tenant policy |
| Overlapping `framework` and `native` configs | Double processing/wrong request URLs | One tested strategy |
| Enabling forwarded handling without checking proxies | App trusts spoofed data | Canonicalize at edge first; use `removeOnly` when untrusted |
| Setting overly narrow `securityMatcher` with no fallback | Out-of-chain requests skip Spring Security protection | Catch-all final chain with deny |
| Placing broad `authenticated` matcher ahead of admin | Regular users bypass HTTP rule | Put privileged rules first, add negative tests |
| Treating URL match as sufficient authorization | IDOR/BOLA | Service checks owner/tenant/resource |
| Building redirects from un-allowlisted Host | Host-header poisoning | Canonical origin or host allowlist |
| Testing backend only with MockMvc | Misses proxy rewrite/header spoofing bugs | Test end-to-end through gateway |
| Treating 404 as proof Spring blocked access | URL may simply lack a controller | Test filter chain and real endpoints |

## 16. Pre-Deployment Checklist

- [ ] Documented **public URL → edge route → upstream URL → Spring matcher/controller** for each sensitive API group.
- [ ] Confirmed whether the proxy **strips, preserves, or replaces prefixes**; never guessed from path names.
- [ ] Tested Servlet fields and matchers with the exact container/framework versions in use.
- [ ] Edge **strips/overwrites both `Forwarded` and `X-Forwarded-*`** inbound from the Internet.
- [ ] Public hosts are allowlisted; TLS state and client IP are verified by the edge.
- [ ] Backend is unreachable directly from untrusted networks; trusted proxy hops are explicitly configured.
- [ ] `server.forward-headers-strategy` is set intentionally and avoids double processing.
- [ ] `X-Forwarded-Prefix` is used only as needed; public redirects/links work without exposing other routes.
- [ ] `SecurityFilterChain`s cover all protected requests and include an appropriate fallback.
- [ ] Admin/permission rules are not shadowed ahead by broad `authenticated`/`permitAll`.
- [ ] Object policies exist for tenant/owner rather than relying purely on host/path/client-supplied IDs.
- [ ] Redirects, OAuth callbacks, password reset links, Secure cookies, and HSTS/HTTPS verified through gateway.
- [ ] Tested spoofing host, protocol, client IP, and prefix; tested encoded/trailing-slash paths and direct backend calls.
- [ ] Logs/monitoring include request ID and routing outcome without leaking credentials.
- [ ] Regression tests run whenever changing ingress/controller context path or upgrading Spring Boot/Framework.

**Summary principle:** *Right path at backend, right identity in Spring Security, right metadata source at trust boundary.* All three must hold together to prevent vulnerabilities from reverse proxies and forwarded metadata.

## 17. Knowledge Self-Check

**1. The proxy rewrites `/portal/api/admin/users` to `/api/admin/users`. Can we assume writing matcher `/portal/api/admin/**` at the backend is right?**  
No. Matchers must match the request Spring Security actually sees after rewriting and forwarded handling; verify in runtime.

**2. Does `X-Forwarded-Prefix: /portal` automatically rewrite the upstream HTTP request?**  
No. It is metadata assisting public-prefix handling; the proxy must have its own rewrite rule.

**3. Does `X-Forwarded-For: 127.0.0.1` prove the client came from localhost?**  
No. The header can be sent by the client if the edge fails to sanitize.

**4. Why must both `Forwarded` and `X-Forwarded-*` be stripped?**  
Because different frameworks/containers read different header families; leaving one family still permits spoofing.

**5. Does `server.forward-headers-strategy=framework` automatically make all forwarded headers trustworthy?**  
No. It enables handling in the app; the trust boundary must be enforced at the proxy/network beforehand.

**6. When choose `native` over `framework`?**  
When the container's native mechanism satisfies the deployment's header/redirect/prefix requirements and trusted-proxy configuration; test real results rather than picking out of habit.

**7. Why does `anyRequest().denyAll()` in a chain matching only `/api/**` fail to protect `/debug`?**  
Because `/debug` does not enter that chain. Another chain or an unrestricted-matcher fallback is required.

**8. Does a MockMvc test returning 403 for `GET /api/admin/users` as a regular user prove the gateway strips `Forwarded`?**  
No. It tests the app's HTTP rule; gateway sanitization requires end-to-end testing through the proxy.

**9. Why can a wrong `X-Forwarded-Host` be more dangerous than a broken link?**  
Because a spoofed host can enter redirects, password reset links, callback URLs, or tenant routing, leading to host-header poisoning and data leaks depending on the system.

**10. If a URL ID is valid and the user holds `ROLE_ADMIN`, can they read every tenant's resources?**  
Not automatically. Business/tenant/owner policies and explicit permission scoping are required.

## 18. Official Documentation

- Spring Security – **HTTP request security and forwarded headers**: https://docs.spring.io/spring-security/reference/features/exploits/http.html
- Spring Security – **Authorize HttpServletRequests / Security Matchers**: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security – **Java Configuration / Multiple HttpSecurity / fallback**: https://docs.spring.io/spring-security/reference/servlet/configuration/java.html
- Spring Framework – **Servlet Filters / Forwarded Headers / ForwardedHeaderFilter**: https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html
- Spring Framework – **Path Matching in Spring MVC**: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/handlermapping-path.html
- Spring Boot 3.5 – **Running Behind a Front-end Proxy Server**: https://docs.spring.io/spring-boot/3.5/how-to/webserver.html
- RFC 7239 – **Forwarded HTTP Extension**: https://www.rfc-editor.org/rfc/rfc7239
