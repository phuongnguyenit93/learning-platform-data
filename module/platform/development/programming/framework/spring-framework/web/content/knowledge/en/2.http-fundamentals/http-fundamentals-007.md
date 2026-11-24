# HTTPS, Reverse Proxies, Redirects, and Public Addresses

## 1. Core Problem: What the User Sees vs. What the Backend Sees

In a Spring MVC application, a request arriving directly at embedded Tomcat might look like `http://localhost:8080`. In production, however, users access `https://app.example.test`, TLS is terminated at a reverse proxy, and the proxy forwards the request to the backend over internal HTTP.

```text
Browser
   |
   | GET https://app.example.test/api/orders/42
   | HTTPS (TLS to public port 443)
   v
Reverse proxy / load balancer
   |
   | GET http://127.0.0.1:8080/api/orders/42
   | Internal HTTP; adds original host/scheme info via forwarded headers
   v
Spring MVC / DispatcherServlet / Controller
   |
   | JSON response, Location, Set-Cookie...
   v
Proxy -> HTTPS -> Browser
```

If Spring does not know the public scheme, host, port, or path prefix, the application may:

- Generate links in emails, JSON, HTML pages, or API docs pointing to `http://127.0.0.1:8080/...` or `http://app.example.test/...` instead of `https://app.example.test/...`.
- Redirect `Location` to an internal host/port, wrong HTTP/HTTPS scheme, or omit a `/portal` prefix.
- Trigger redirect loops between a proxy enforcing HTTPS and an application perceiving the request as HTTP.
- Misconfigure properties that depend on HTTPS (such as evaluating whether a request is secure), or mishandle callback URLs.

This lesson focuses on the relationship between **HTTP/TLS, reverse proxies, forwarded headers, redirects, and external/public URLs** in Spring Web MVC. WebFlux uses its own mechanisms, such as `ForwardedHeaderTransformer`.

## 2. Concepts and Boundaries of Responsibility

### HTTPS and TLS termination

HTTPS is HTTP over TLS. TLS protects confidentiality, integrity, and server identity authentication over the connection segment where TLS is established. With **TLS termination at the reverse proxy**, the browser verifies the proxy's certificate; the backend may receive plain internal HTTP.

That does not automatically mean the hop from the proxy to the backend is encrypted. Use plain internal HTTP only inside a controlled trusted network, or use HTTPS/mTLS between layers if your security model requires it. A valid HTTPS certificate on the client side does not indicate the backend itself uses TLS.

### Reverse proxy and load balancer

A reverse proxy sits in front of the application, receives requests at the public address, and forwards them to one or more backends. It may terminate TLS, balance load, inject headers, cache, rewrite paths, or select upstreams. Load balancers can operate at the TCP layer (L4) or HTTP layer (L7); only HTTP-aware hops add or modify HTTP headers.

### Public address (public origin/base URL)

An **origin** is the tuple `scheme + host + port`; for example, `https://app.example.test` has default port 443. A **Base URL** may also include an application prefix like `https://app.example.test/portal`. Distinguish:

| Component | Example | Purpose |
| --- | --- | --- |
| Scheme | `https` | Protocol used by the client. |
| Host | `app.example.test` | Public hostname, distinct from `localhost` or internal machine names. |
| Port | `443` | Client-facing port; usually omitted from HTTPS URLs when default. |
| Path prefix | `/portal` | External path segment the proxy may preserve or strip when forwarding. |
| Request URI | `/portal/api/orders/42` | Request path invoked by external callers. |

The true public address cannot be deduced solely from the internal port `8080` Spring listens on.

## 3. Headers That Tell the Backend About the Original Request

Two header families are commonly encountered:

- `Forwarded` per RFC 7239, e.g., `Forwarded: for=192.0.2.10;proto=https;host=app.example.test`. A chain of proxies may append multiple elements to the header.
- De facto standard headers: `X-Forwarded-Proto: https`, `X-Forwarded-Host: app.example.test`, `X-Forwarded-Port: 443`, `X-Forwarded-For: 192.0.2.10`, and `X-Forwarded-Prefix: /portal`.

| Header | What does it convey? | Common confusion |
| --- | --- | --- |
| `Host` | Host of the request received by the **current hop** | Not necessarily the outermost host if a proxy rewrites Host. |
| `Forwarded` | Client/host/protocol info supplied by proxies per standard | Not self-authenticating; can be spoofed by clients if the proxy does not strip it. |
| `X-Forwarded-Proto` | External request scheme, commonly `https` | Not proof that backend ↔ proxy uses TLS. |
| `X-Forwarded-Host` | Original public host | Unsafe if clients can supply it arbitrarily. |
| `X-Forwarded-Port` | Public port | Not the internal `server.port`. |
| `X-Forwarded-For` | Client IP info across proxy hops | A chain provided by proxies that must be parsed along a trust chain; never blindly trust the first entry. |
| `X-Forwarded-Prefix` | Public path prefix altered by the proxy | Must align properly with path rewrites and servlet context path. |

**Mandatory security warning:** clients can send forged `Forwarded` or `X-Forwarded-*` headers. **The reverse proxy at the trust boundary must strip forwarded headers from external requests and set its own authoritative values**, even when the system only intends to use one of the two header families. In addition, block users from reaching a backend that trusts forwarded headers directly. Otherwise, attackers can trick the app into generating password-reset URLs pointing to their domain, redirecting to wrong hosts, or logging fake IPs. Spring cannot automatically tell whether a header came from a trusted proxy or was spoofed by a client.

## 4. How Does Spring Boot Handle Forwarded Headers?

Spring Boot supports configuring `server.forward-headers-strategy`:

| Value | Behavior | When to choose |
| --- | --- | --- |
| `none` | Does not interpret forwarded headers to alter public request info | Running directly without a proxy or lacking an enforced trust boundary. |
| `native` | Uses container support, such as Tomcat's `RemoteIpValve` configuration | When the container handles all header types the application needs. |
| `framework` | Uses Spring Framework support—for Spring MVC, `ForwardedHeaderFilter` | When the app needs accurate scheme/host/port or redirect handling via forwarded headers, especially when native container support falls short. |

Spring Boot may choose different defaults in some cloud environments; **never guess from the environment**. Specify the choice explicitly in deployment configuration and test real requests. With Tomcat behind a TLS-terminating proxy, Spring Boot documentation recommends considering `server.tomcat.redirect-context-root=false` so the forwarded scheme is accounted for before the container redirects the context root itself.

Spring Boot 3.5 example in `src/main/resources/application.yml`:

```yaml
server:
  port: 8080
  forward-headers-strategy: framework
  tomcat:
    redirect-context-root: false
```

When valid forwarded headers arrive from a trusted proxy, `ForwardedHeaderFilter` wraps the request so handlers and downstream components see the public scheme, host, port, and—depending on configuration/version—public prefix. The filter also adjusts forwarded-header effects on certain redirects. If you register custom filters, order matters: any component needing public URL details must run after forwarded headers have been processed.

**Do not register the filter manually a second time** if Boot already auto-configured it via `server.forward-headers-strategy: framework`. Avoid enabling overlapping forwarding mechanisms without understanding and verifying their ordering.

### Without Spring Boot

A Spring MVC application configuring Servlet filters manually can use `org.springframework.web.filter.ForwardedHeaderFilter`. When registering it yourself, place it early enough and cover `REQUEST`, `ASYNC`, and `ERROR` dispatcher types; downstream filters and servlets must see the wrapped request. The filter also offers a `removeOnly` mode to strip forwarded headers **without** applying them. Specific constructors and options—such as `Forwarded` vs. `X-Forwarded-*` precedence or prefix handling—can vary by Spring Framework release: check the exact version's Javadoc before configuring manually.

## 5. Runnable Spring MVC Example: Generating Links and Redirecting to Public URLs

The example below uses Java 17+, Spring Boot **3.5.16**, Maven, and embedded Tomcat. Endpoint `/api/public-link` returns an absolute URL to `/api/items/42`; endpoint `/go` performs an HTTP redirect to the item endpoint. When valid forwarded headers are processed, the absolute URL reflects the public host/scheme.

**Structure:**

```text
proxy-demo/
├── pom.xml
└── src/main/
    ├── java/demo/
    │   ├── ProxyDemoApplication.java
    │   ├── LinkController.java
    │   └── NavigationController.java
    └── resources/application.yml
```

**`pom.xml`:**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>proxy-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

**`src/main/resources/application.yml`:**

```yaml
server:
  port: 8080
  forward-headers-strategy: framework
  tomcat:
    redirect-context-root: false
```

**`src/main/java/demo/ProxyDemoApplication.java`:**

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ProxyDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ProxyDemoApplication.class, args);
    }
}
```

**`src/main/java/demo/LinkController.java`:**

```java
package demo;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;

@RestController
public class LinkController {
    @GetMapping("/api/public-link")
    public Map<String, String> link() {
        String url = ServletUriComponentsBuilder.fromCurrentContextPath()
                .path("/api/items/{id}")
                .buildAndExpand(42)
                .toUriString();
        return Map.of("url", url);
    }

    @GetMapping("/api/items/{id}")
    public Map<String, Object> item(@PathVariable long id) {
        return Map.of("id", id, "status", "ok");
    }
}
```

**`src/main/java/demo/NavigationController.java`:**

```java
package demo;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class NavigationController {
    @GetMapping("/go")
    public String go() {
        return "redirect:/api/items/42";
    }
}
```

`@Controller` returns the view name `redirect:/...`, causing Spring MVC to issue an HTTP redirect. **If you change this class to `@RestController`, the literal string `redirect:/api/items/42` will be sent as the response body** instead of redirecting; you must return a `ResponseEntity` with a `Location` header to redirect from a REST controller.

**Run:**

```bash
mvn spring-boot:run
```

In another terminal, without forwarded headers:

```bash
curl -s http://localhost:8080/api/public-link
```

Expected JSON body (single field, no key-order sensitivity):

```json
{"url":"http://localhost:8080/api/items/42"}
```

Simulate a proxy **in an isolated development environment**:

```bash
curl -s -H "X-Forwarded-Proto: https" -H "X-Forwarded-Host: app.example.test" -H "X-Forwarded-Port: 443" http://localhost:8080/api/public-link
```

Expected JSON body:

```json
{"url":"https://app.example.test/api/items/42"}
```

Observe the redirect (omit `-L`, since `-L` follows `Location`):

```bash
curl -i -H "X-Forwarded-Proto: https" -H "X-Forwarded-Host: app.example.test" -H "X-Forwarded-Port: 443" http://localhost:8080/go
```

Expect a 3xx status (the default redirect view is typically **302**) and a `Location` pointing to `/api/items/42` on the public origin. Inspect the **actual `Location` value**: depending on redirect configuration and Framework version, browsers may receive an absolute URL or a relative path; the invariant to verify is that the browser navigates to the **right public origin/path**, never the internal backend.

**Testing note:** sending `X-Forwarded-*` directly from `curl` above only demonstrates request transformation on a dev machine. Production must accept these headers only from a trusted proxy that sanitizes them.

## 6. Configuring the Reverse Proxy: TLS, Host, and Forwarded Headers

The following is an **illustrative Nginx `location` block**, placed inside a `server` block already configured with valid HTTPS, certificates, and `server_name app.example.test`. Nginx acts as the reverse proxy at the **final public boundary** receiving Internet traffic, and the application accepts only internal connections from Nginx.

```nginx
location / {
    proxy_pass http://127.0.0.1:8080;

    proxy_set_header Host app.example.test;
    proxy_set_header X-Forwarded-Host app.example.test;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-Port 443;
    proxy_set_header X-Forwarded-For $remote_addr;

    proxy_set_header Forwarded "";
    proxy_set_header X-Forwarded-Prefix "";
    proxy_set_header X-Forwarded-Ssl "";
}
```

Explanation of the choices in the example:

- `proxy_pass` targets the internal backend. Here Nginx and the app run on the same host; in containerized environments, the upstream address usually differs.
- `Host` and `X-Forwarded-Host` are set to a **known public host**, avoiding echoing invalid client-supplied Host values. If multiple valid domains exist, use appropriate host routing/allowlists rather than hardcoding one host for all sites.
- `X-Forwarded-Proto` and `X-Forwarded-Port` reflect the public HTTPS listener. These fixed values are only accurate when this Nginx server block genuinely serves HTTPS on 443. In multi-tier topologies, values are computed at the proper trust boundary.
- `X-Forwarded-For` assigns the peer address observed by the edge proxy; here it does not append client-sent `X-Forwarded-For` data. If another trusted proxy sits in front, design the true address chain with matching trusted-proxy configuration.
- The remaining headers are cleared from the upstream request so clients cannot smuggle forged values; Nginx omits headers set to empty strings via `proxy_set_header`.
- Firewall/network policies must block direct public connections to backend port 8080 whenever the backend trusts forwarded headers.

**Enforcing trust is infrastructure's responsibility.** No `server.forward-headers-strategy` setting independently verifies that `X-Forwarded-Host` came from an authenticated proxy. Across multiple load balancers, CDNs, or ingresses, identify where headers are stripped, regenerated, and accepted at each hop; never treat self-reported client headers as a source of truth.

### When an external `/portal` prefix is present

There are two distinct cases:

**Case 1: proxy preserves the path**: the browser calls `/portal/api/items/42` and the backend receives the exact same path. You can configure the application with context path `/portal` or design controller mappings accordingly; do not add `X-Forwarded-Prefix` unnecessarily. Note that `server.servlet.context-path=/portal` is a Servlet container-level setting, different from merely adding a segment to `@RequestMapping`.

**Case 2: proxy strips the path prefix**: the browser calls `/portal/api/items/42`, and the backend receives `/api/items/42`. A trusted proxy can send `X-Forwarded-Prefix: /portal` so the framework includes the prefix when building public links, if supported by your Spring version and forwarding setup. Test actual links and `Location` values; never assume from the header alone that every redirect, static asset, and context path works seamlessly.

For example, when Nginx already has an HTTPS server block as above, you can replace `location /` with a prefix-routing block:

```nginx
location /portal/ {
    proxy_pass http://127.0.0.1:8080/;

    proxy_set_header Host app.example.test;
    proxy_set_header X-Forwarded-Host app.example.test;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-Port 443;
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header X-Forwarded-Prefix /portal;

    proxy_set_header Forwarded "";
    proxy_set_header X-Forwarded-Ssl "";
}
```

The trailing `/` on `proxy_pass` matters for Nginx location prefix replacement: in this config, `/portal/api/items/42` arrives at the backend as `/api/items/42`. If you want to keep the prefix instead, configure the proxy differently and align the context path. When using `X-Forwarded-Prefix`, verify actual support in your Spring version; do not blindly enable both context path `/portal` and prefix `/portal`, which can yield `/portal/portal/...`.

## 7. HTTP Redirects: Status Codes, Location, and Method Preservation

A redirect is an HTTP 3xx response containing `Location`; browsers/clients may issue a new request to that target. In Spring MVC, `redirect:` creates a redirect view; in REST APIs you can return `ResponseEntity.status(...).location(uri).build()`.

| Status | Primary Meaning | How clients handle method/body |
| --- | --- | --- |
| **301 Moved Permanently** | URL has moved permanently | Clients historically may convert POST to GET; do not rely on method preservation by default. |
| **302 Found** | Temporarily moved | Browsers and many clients may change POST to GET. |
| **303 See Other** | Go to another resource to view the result | Commonly used after POST; the follow-up request is GET (except HEAD). |
| **307 Temporary Redirect** | Temporary redirect, **preserves method and body** | Useful when the original method must remain intact. |
| **308 Permanent Redirect** | Permanent redirect, **preserves method and body** | Use carefully as it can be cached long-term. |

**Post/Redirect/Get (PRG) example**: after a POST creates a record successfully, return **303 See Other** to `GET /orders/42`, preventing browser reloads from resubmitting the POST. With 307/308 redirects, clients resend the same method and body to the target, which can mutate data elsewhere if misconfigured.

```java
// Illustrative snippet placed inside a @RestController.
@PostMapping("/api/orders")
public ResponseEntity<Void> create() {
    URI location = URI.create("/api/orders/42");
    return ResponseEntity.status(HttpStatus.SEE_OTHER)
            .location(location)
            .build();
}
```

This snippet is **not a standalone Java file**; it requires `import java.net.URI;`, Spring's `ResponseEntity` and `HttpStatus`, and `@PostMapping`. This example returns a relative `Location`; the browser resolves it against the current request's origin. In a real application, the ID must come from the newly created record, and REST APIs may prefer **201 Created + Location** rather than a redirect depending on the endpoint contract.

**Never choose redirect behavior purely from Spring defaults.** Decide explicitly whether the URL change is temporary or permanent, whether it follows POST or GET, whether method/body must be preserved, and whether clients may cache the redirect.

## 8. HTTP → HTTPS: Where Should Redirection Happen?

A common pattern is a proxy with an HTTP listener on port 80 returning a redirect to HTTPS on port 443, then serving application requests over HTTPS:

```text
GET http://app.example.test/api/items/42
  -> proxy: 301/308 Location: https://app.example.test/api/items/42
  -> browser: GET https://app.example.test/api/items/42
  -> proxy: forwards to Spring backend
```

If you want to use **308** for site-wide redirects, ensure all clients accept method preservation on non-GET requests. For ordinary interactive browsers, 301/302 are common; for HTTP APIs, carefully evaluate how redirects affect POST/PUT/PATCH.

**Avoid having two layers both enforce HTTPS without consistent trust headers**. For example, if the proxy accepts HTTPS and forwards internal HTTP while forwarded headers are missing, Spring sees `request.isSecure() == false` and redirects to HTTPS; the browser hits the proxy again and loops endlessly. One solution is handling HTTPS at the edge and configuring forwarding properly so Spring sees the public scheme as `https`. You can skip redundant application-level HTTPS redirects if the proxy already enforces it.

### What is HSTS?

**HTTP Strict Transport Security** sends the `Strict-Transport-Security` header in **HTTPS** responses to tell supporting browsers that for a period of time they should connect to that host only over HTTPS. Example:

```http
Strict-Transport-Security: max-age=31536000
```

HSTS **does not replace** deploying HTTPS and redirecting HTTP where needed, and browsers ignore HSTS sent over HTTP. `includeSubDomains` and `preload` have wide-ranging effects that are hard to reverse quickly; enable them only when every relevant subdomain truly serves HTTPS and you have an operational plan. Spring Security supports HSTS when Spring Security is used; some proxies can also emit this header. Designate **one authoritative place** and verify actual output to avoid conflicting configurations.

### Cookies and OAuth callbacks

- Cookies carrying session IDs/auth tokens normally need the `Secure` attribute so browsers send them only over HTTPS; `HttpOnly` limits JavaScript access to cookies, and `SameSite` governs sending cookies in cross-site contexts. Each serves a distinct role.
- Callback URLs (OAuth/OIDC), password reset URLs, email links, Swagger UI redirects, or webhook responses require the right **public host/scheme/path**, often matching a provider's allowlist. Configure a fixed external base URL for workflows requiring strict stability rather than reading Host/Forwarded headers from untrusted requests.
- HSTS, `Secure` cookies, and TLS security cannot be verified simply by running `curl -k` and seeing status 200. Test from a client that observes certificates, proxies, and redirects like a real user.

## 9. Choosing Between Relative and Absolute URLs

**Relative URLs** like `/api/items/42` require no knowledge of host or scheme and are usually the simplest option for navigation links **within the same public origin**. However, if the application is published under a `/portal` prefix, a path starting with `/` references the host root and can drop `/portal`. In that case, build the path from the proper public context or use relative paths tested against the current location.

**Absolute URLs** like `https://app.example.test/portal/api/items/42` are required when the value leaves the current request context (emails, callbacks, QR codes, legitimate cross-origin redirects, documentation for external clients).

Four URL generation sources to distinguish:

1. **Current-request-based URLs**: `ServletUriComponentsBuilder` or Spring MVC utilities read request metadata after forwarding has been applied; useful for links representing the current request, subject to the trust boundary.
2. **Statically configured external base URL**: vetted official hostname/port/prefix, ideal for emails and callbacks; avoids Host header injection and stays independent of internal requests.
3. **Browser-relative routes**: the browser supplies the current origin automatically, good for internal links; watch out for path prefixes.
4. **Client-supplied URI/Location**: never blindly redirect to a query parameter like `?next=https://...` without validation. That causes *open redirect* vulnerabilities.

Do not use `request.getRequestURL()` to build sensitive links before verifying proxy configuration: if forwarded headers are not processed, it may yield the internal backend address; if headers are unsanitized, it may reflect an attacker-chosen host.

## 10. Open Redirects and Building an Allowlist

For example, an endpoint accepting `/login?next=https://evil.example` and returning `Location` verbatim with the `next` string has an **open redirect** flaw. Attackers can distribute a link that looks like it belongs to a legitimate site yet sends users to a phishing domain once clicked.

Safe mitigations depending on your goal:

- For same-site redirects, accept only a predefined set of internal paths (e.g., `/dashboard`, `/account`), checking paths, encoding, fragments, and tricks like `//evil.example` or backslashes. Instead of accepting arbitrary URLs, you can map a navigation key like `next=dashboard` to a fixed route.
- For genuinely necessary external redirects, allow only the `https` scheme and specific **origins** from a managed allowlist. Compare using a proper URI parser and normalized host, never naive `startsWith("https://example.com")` (which can be tricked by `example.com.evil.test`).
- Never construct password-reset or OAuth redirects from `X-Forwarded-Host` if clients could forge that header; use a preconfigured base URL or a host allowlist enforced at the trust boundary.

Even when the backend does not expose its port directly, proxy misconfigurations can still cause `Location` headers and absolute links to be wrong or unsafe.

## 11. Failure Scenarios and Root-Cause Analysis

| Symptom | Signals to Observe | Cause / Fix |
| --- | --- | --- |
| Links in JSON become `http://localhost:8080/...` | Response body, `request.getScheme()`, `getServerName()` | Forwarded headers not processed, or proxy not sending public host/scheme. |
| `Location: http://app.example.test/...` on an HTTPS site | HTTP 3xx `Location` | Missing `X-Forwarded-Proto`/`Forwarded: proto=https` or app generating URLs from internal HTTP. |
| Infinite redirect loop | `Location` chain and 301/302/307/308 codes via `curl -I -L -v` | Proxy and Spring disagree on HTTPS, context path, or trailing slash. |
| Links missing `/portal` | Public URL vs. backend request URI | Proxy rewrote the prefix while the framework did not receive it; or URLs were concatenated manually. |
| Links repeating `/portal/portal` | Public base URL / context path / forwarded prefix | Prefix applied at multiple layers; pick one clear mapping. |
| Links pointing to an unknown host | Client-sent `Host`, `Forwarded`, `X-Forwarded-Host` | Trust boundary failed to strip headers; fix/allowlist hosts and block direct backend access. |
| HTTPS request blocked by browser mixed content | Browser console/network | HTML/JS emits `http://` asset URLs; fix URL generation, CDN config, and forwarding. |
| Cookie missing after redirect/login | `Set-Cookie`, domain/path/`Secure`/`SameSite` | Wrong cookie scope, proxy/TLS causes wrong public scheme evaluation, or cross-site flow blocked. |
| OAuth reports `redirect_uri_mismatch` | Redirect URI sent to provider | Scheme/host/port/prefix does not match registered URI; configure exact external base URL. |
| Logs always show the proxy's IP | Request remote address/forward chain | `X-Forwarded-For` not handled, or client IP extracted from wrong trust chain. |

### Inspecting with HTTP tools

```bash
# View status, Location, response headers. Do not follow redirects automatically.
curl -i https://app.example.test/go

# View the full redirect chain, request method, and URL at each hop.
curl -v -L --max-redirs 5 https://app.example.test/go

# On a machine with internal backend access, compare before/after forwarding.
curl -i http://localhost:8080/api/public-link
curl -i -H "X-Forwarded-Proto: https" -H "X-Forwarded-Host: app.example.test" http://localhost:8080/api/public-link
```

The commands above are illustrative; `app.example.test` is a sample domain—hitting a public site requires real DNS/TLS and a proxy in that environment. When testing with `curl -L`, cap redirects to avoid infinite loops. For sensitive endpoints, never log raw headers containing personal data or tokens.

Key diagnostic questions: "Which URL did the client call?", "Which request URI did the proxy forward?", "Which headers did the trusted proxy set?", "How does Spring process those headers?", "What is the actual response `Location`/absolute link?".

## 12. Deployment Checklist

1. **Define the official public origin and path**: HTTPS scheme, host, port, prefix. Document whether the proxy preserves or strips the prefix.
2. **Valid TLS** on the public listener; decide whether the backend hop uses internal HTTP or HTTPS/mTLS based on network segmentation.
3. **Configure the trust boundary**: strip untrusted `Forwarded`/`X-Forwarded-*`, set authoritative headers, lock down direct backend access, and verify the trusted proxy chain.
4. **Pick the right forwarding strategy**: `none`, `native`, or `framework`; if native does not handle prefixes/redirects adequately, consider `framework` and test end-to-end.
5. **Test links and redirects**: absolute URLs, relative URLs, `Location`, post-POST redirects, prefixes, query strings, and HTTP→HTTPS cases.
6. **Verify security/cookies**: HSTS over HTTPS, appropriate `Secure`/`HttpOnly`/`SameSite`, callback URLs, open redirects, and host injection.
7. **Test through the real proxy** from a client outside the backend network; test with a browser, `curl -i`, and relevant flows—not just `localhost:8080`.

## 13. Self-Assessment Questions

**Q:** The client used HTTPS, yet `request.isSecure()` in Spring is still `false`. Is TLS definitely broken?  
**A:** No. The proxy may terminate TLS and forward internal HTTP. Check TLS between client→proxy and how Spring receives the forwarded scheme; `request.isSecure()` itself reflects the request presented by the container/filters.

**Q:** Is `X-Forwarded-Proto: https` enough to trust that the request came over HTTPS?  
**A:** No. Clients can send that header too; trust it only after the proxy boundary strips/resets it and the backend is shielded from direct bypass traffic.

**Q:** Why does redirect path `/login` work at root yet break when the public URL is `/portal`?  
**A:** Paths starting with `/` are host-root absolute paths; the proxy may have stripped the prefix. Construct URLs with the proper external path and verify forwarded-prefix support.

**Q:** When should you return 303 instead of 307?  
**A:** After a POST when you want the client to load the result page via GET, choose 303; when redirecting while needing to **preserve** the request method and body, choose 307 (temporary) or 308 (permanent) as appropriate.

**Q:** Once `server.forward-headers-strategy=framework` is enabled, can backend port 8080 be exposed publicly?  
**A:** No; if the backend directly accepts forged forwarded headers, attackers can induce wrong-host links or redirects. Enforce firewall/routing rules and a proper trust boundary.

## 14. Reference Documents

- [Spring Boot 3.5 — Embedded Web Servers / Running Behind a Front-end Proxy](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html).
- [Spring Framework — ForwardedHeaderFilter and securing forwarded headers](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html).
- [Spring Framework — Redirect Attributes](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/redirecting-passing-data.html).
- [RFC 9110 — HTTP Semantics, 3xx redirection](https://www.rfc-editor.org/rfc/rfc9110).
- [RFC 7239 — Forwarded HTTP Extension](https://www.rfc-editor.org/rfc/rfc7239).
- [MDN — HTTP Strict Transport Security](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Strict-Transport-Security).

**Key takeaway:** Spring can only generate accurate public URLs when **real-world request routing**, **reverse proxy TLS/redirects**, **forwarded headers from trusted sources**, and **application URL-building rules** are all aligned.