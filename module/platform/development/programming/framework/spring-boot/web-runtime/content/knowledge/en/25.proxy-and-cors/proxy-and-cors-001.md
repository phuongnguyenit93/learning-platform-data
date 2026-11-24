# Public paths, hosts, and protocols when a Spring Boot application is behind a reverse proxy

## 1. The problem: which URL does the user see, and which URL does the backend see?

A Spring Boot application deployed behind a **reverse proxy**, **load balancer**, **API gateway**, or **ingress controller** typically has two different addresses:

- **Public URL:** the address that end users or external systems actually see, for example `https://app.example.com/portal/demo/inspect`.
- **Backend URL:** the address that the reverse proxy uses to call the application, for example `http://127.0.0.1:8080/demo/inspect` or `http://app-service:8080/demo/inspect`.

The proxy may terminate HTTPS (TLS termination), change the host/port, and add or strip a path prefix. A backend looking only at the connection made directly to itself will see HTTP, an internal host, and the rewritten path. If the application uses that information to generate absolute links, redirects, OAuth callback URLs, or cookies, users may encounter:

- Redirects to `http://app-service:8080/...` instead of `https://app.example.com/...`.
- The browser reporting **mixed content** when an HTTPS page contains HTTP links, scripts, or API endpoints.
- Redirects missing the `/portal` prefix, leading to 404.
- Incorrect `Secure` or `Path` cookie attributes, login loops, or the session not being sent.
- An OAuth/OIDC redirect URI that does not match the registered value.
- URLs built from an untrusted host header, leading to **host-header poisoning**, open redirects, or password-reset links pointing to an attacker's domain.

This lesson belongs to the **Proxy and CORS** topic and focuses on keeping the **scheme, host, port, and path prefix** aligned with the public entry point. The examples use **Spring Boot 3.5.x, Spring MVC/Servlet, Java 17+**, and an illustrative Nginx proxy; the later sections cover WebFlux, cookies, Spring Security, and CORS.

**Most important goal:** establish a **trust boundary** where the proxy strips client-supplied `Forwarded`/`X-Forwarded-*` values and sets verified values; Spring is only allowed to interpret information that has crossed that boundary. Do not trust forwarded headers directly from the Internet.

## 2. Request diagram and how the URL changes across a proxy

Consider the setup:

```text
Browser / external partner
GET https://app.example.com/portal/demo/inspect
                 |
                 | HTTPS :443
                 v
Nginx / Ingress / Load Balancer
- Verifies Host = app.example.com
- Terminates TLS
- Strips the /portal prefix when forwarding upstream
- Strips untrusted forwarded headers and sets proxy headers
                 |
                 | HTTP :8080 (internal network)
                 v
Spring Boot MVC
GET http://127.0.0.1:8080/demo/inspect
                 |
                 v
Spring needs to know the original URL is:
scheme = https
host = app.example.com
port = 443
external path prefix = /portal
```

Distinguish between **two different transformations**:

1. **Rewriting the request path at the proxy:** from `/portal/demo/inspect` to `/demo/inspect`. This is the step that allows the `@GetMapping("/demo/inspect")` controller to handle the request.
2. **Reconstructing the public URL in the backend:** the application still needs to know that the external URL has the `/portal` prefix and the public scheme/host in order to generate accurate links and redirects.

Doing only (1) while skipping (2) causes the app to handle the request successfully but return broken links. Doing only (2) while the proxy does not rewrite properly prevents Spring from matching the controller mapping.

Another model is **keeping the prefix intact** at the proxy and configuring `server.servlet.context-path=/portal` on the backend. Both models can be valid. However, **you should not both strip the prefix at the proxy and require that context path on the backend**, nor should you keep the prefix internally while also manually prepending it to every link, as this easily leads to 404s or a doubled `/portal/portal`.

## 3. Components of a public URL

For the URL:

```text
https://app.example.com:443/portal/products/42?q=a%26b#details
  |        |         |     |        |            |
scheme    host       port  prefix   path         query/fragment
```

- **Scheme:** `https` or `http`; HTTPS at the edge does not mean the backend uses HTTPS.
- **Host:** `app.example.com`, not the internal pod/container/VM hostname.
- **Port:** `443` for standard HTTPS; may be omitted in standard URL representations. If the proxy exposes a non-default port such as `8443`, it must be reflected accurately.
- **Public prefix:** `/portal`, typically coming from gateway routing/rewriting; **not a classpath directory name**.
- **Path:** `/products/42` is the path segment within the application.
- **Query:** parameters must be encoded per component; do not concatenate raw user input into links.
- **Fragment:** `#details` is normally handled only client-side by the browser and is not sent to the server in an HTTP request.

An **origin** in a CORS policy consists of **scheme + host + port**, not the path prefix. For example, `https://app.example.com/portal` and `https://app.example.com/another` share the **same origin** if they have the same scheme, host, and port, even if their routing differs.

## 4. Two common proxy header families

### 4.1. Standard `Forwarded` header (RFC 7239)

A proxy can use:

```http
Forwarded: for=203.0.113.20;proto=https;host=app.example.com
```

Information typically includes:

- `for`: client identity/address along the hop chain, depending on proxy policy.
- `proto`: scheme on the client/edge side (for example `https`).
- `host`: public host, which may include a port.

The header may contain multiple elements across proxy hops. Do not naively split the string by commas or semicolons for security logic: the RFC format supports quoted values, IPv6, obfuscated identifiers, multiple hops, and proxy trust rules.

### 4.2. The `X-Forwarded-*` header family

Many proxies use the long-standing convention:

```http
X-Forwarded-Proto: https
X-Forwarded-Host: app.example.com
X-Forwarded-Port: 443
X-Forwarded-Prefix: /portal
X-Forwarded-For: 203.0.113.20
```

Meaning:

| Header | Reflects | Pitfalls |
| --- | --- | --- |
| `X-Forwarded-Proto` | Public scheme, e.g., `https` | If missing, the app may generate `http://...` |
| `X-Forwarded-Host` | Host the user accesses | If the client can supply it, URLs may point to an attacker |
| `X-Forwarded-Port` | Public port | Wrong port can make callbacks/redirects unreachable |
| `X-Forwarded-Prefix` | External prefix handled by the proxy | Missing prefix -> 404, duplicated prefix -> broken URL; support depends on Spring version/config |
| `X-Forwarded-For` | Chain of client/proxy hop addresses | Do not blindly trust the first value as a trusted IP |
| `X-Forwarded-Ssl` | Another convention for HTTPS termination | Does not replace a standardized proxy contract |

These are **spoofable metadata** if the backend receives them directly from a client. Do not use these headers for **authorization**, privilege escalation, brute-force protection, or IP allowlisting before verifying the header source and trusted hop chain.

**Do not intentionally enable both the standard and legacy formats "just in case."** Agree on a single contract with the proxy, strip unused headers from the Internet, and test how the framework prioritizes them if both still appear.

## 5. Securing the trust boundary: before enabling forwarded headers

Spring configuration can reconstruct public URLs **only when the proxy guarantees the headers are trustworthy**. Spring cannot tell on its own whether a `Forwarded` value was set by a legitimate proxy or forged by an outsider.

Three minimum requirements:

1. **The edge proxy strips/overwrites** `Forwarded` and all `X-Forwarded-*` headers coming from the Internet, then sets appropriate values from a trusted source (TLS termination, routing rules, verified host). If there are multiple proxies, rules for preserving/replacing hops must be clearly defined at each trust boundary.
2. **The backend must not be directly reachable publicly.** Bind to localhost if on the same machine, or use security groups, network policies, firewalls, private service endpoints, or sidecar isolation. In production, never leave `http://pod-ip:8080` accessible from the Internet alongside the reverse proxy.
3. **Allow only valid public hosts.** Configure an ingress/server name allowlist; avoid using a client-supplied raw `Host` or `X-Forwarded-Host` to determine the domain of links, password-reset URLs, or redirects.

Bad example:

```http
GET /demo/next HTTP/1.1
Host: 127.0.0.1:8080
X-Forwarded-Proto: https
X-Forwarded-Host: attacker.invalid
```

If the backend trusts this header from a direct connection, a response URL can be turned into `https://attacker.invalid/...`. An attacker does not need to know the internal link setup—only that the application uses the header to build URLs.

For **especially security-sensitive links** (password recovery, invitation links, email verification, webhook callbacks, OAuth redirect URIs), prefer an **operator-configured canonical public base URL** and/or an approved host allowlist instead of relying entirely on request metadata. For example, `app.public-base-url=https://app.example.com/portal`, which is introduced in the hands-on example.

**Testing one valid request is not enough to prove the proxy is safe.** You must verify that a request carrying a malicious external `Forwarded` or `X-Forwarded-Host` is stripped/overwritten before reaching Spring, and ensure the raw backend port is not exposed to the Internet.

## 6. Configuring Spring Boot `server.forward-headers-strategy`

Spring Boot has the property:

```properties
server.forward-headers-strategy=framework
```

Modes:

| Value | Meaning | Considerations |
| --- | --- | --- |
| `none` | Does not rely on forwarded headers to reconstruct requests through this mechanism | Suitable when there is no trusted proxy or when using fixed canonical URLs |
| `native` | Uses the embedded web server/container's native capability (e.g., Tomcat `RemoteIpValve`) | Useful for scheme/remote IP; prefix/host support varies by container/version |
| `framework` | Uses Spring Framework-level processing: `ForwardedHeaderFilter` for Servlet MVC or `ForwardedHeaderTransformer` for WebFlux | Suitable when more complex handling is needed, while still requiring trust-boundary protection |

**Do not enable `framework` while also arbitrarily registering another `ForwardedHeaderFilter`**, as headers may be processed twice or filter ordering may become unexpected. Spring Boot already provides integration via this property.

Spring Boot 3.5 documentation notes that some cloud environments have different defaults; **set the mode explicitly according to your deployment design** instead of relying on defaults across local, Docker, and cloud. In the hands-on example, we use `framework` in an environment simulating a trusted proxy—**that does not mean it is safe to expose the app port to the Internet**.

### 6.1. When is `native` a reasonable choice?

If the proxy provides standard `X-Forwarded-For` and `X-Forwarded-Proto`, the container's native support may be sufficient for scheme/client metadata. With Tomcat, `RemoteIpValve` has additional settings for header names and trusted internal proxy ranges. Example configuration keys (must match the actual architecture):

```properties
server.forward-headers-strategy=native
server.tomcat.remoteip.protocol-header=x-forwarded-proto
server.tomcat.remoteip.remote-ip-header=x-forwarded-for
```

This is **an alternative** to `framework`, not a set of properties to enable at the same time. Do not set `server.tomcat.remoteip.internal-proxies` to empty in production just so every IP is trusted. Verify trusted proxy IPs/CIDRs and how Tomcat parses the chain; do not use `X-Forwarded-For` as a security identity when clients can inject data.

If `X-Forwarded-Prefix` is needed, do not assume native mode will handle it the same way as the Spring filter. **Actually test the context path and `Location` header**, or use an architectural scheme that does not strip prefixes.

### 6.2. `framework` and `X-Forwarded-Prefix`

When the proxy strips `/portal` before sending upstream, Spring needs a mechanism to understand the **public prefix**.

Spring Framework has support for `X-Forwarded-Prefix` in its forwarded-header infrastructure. **Prefix enable/disable behavior can vary across Spring Framework versions**, including separate options for using prefixes in newer releases. Therefore, do not conclude solely from `server.forward-headers-strategy=framework` that every framework version will automatically set `request.getContextPath()` to `/portal`. Check your specific framework version, filter/transformer configuration, and the output of `request.getContextPath()` or Spring-generated links.

For framework versions that allow setting `ForwardedHeaderFilter.setUseForwardedPrefix(true)`, this option should only be applied when the gateway genuinely sends a **trusted** prefix. Do not manually add a second filter when Boot already registers one; if deep customization is needed, deliberately design the registration so there is only **one** processing mechanism.

**Simple and reliable fallback:** for critical links, use a fixed `app.public-base-url` plus the internal path in the right place. The example below still keeps the forwarded-headers configuration to demonstrate scheme/host handling, while redirects are built from a canonical base so `/portal` is preserved even if a framework version does not automatically handle the prefix.

### 6.3. Tomcat TLS termination and context-root redirects

According to Spring Boot documentation, with Tomcat behind a TLS-terminating proxy, you may need:

```properties
server.tomcat.redirect-context-root=false
```

The goal is to prevent Tomcat from performing a context-root redirect **before `X-Forwarded-Proto` is applied** in certain configurations. This is not an option that turns HTTP into HTTPS, nor does it replace proxy headers. Verify against your Tomcat/Boot version and deployment before applying it.

## 7. Nginx reverse proxy configuration example

Suppose the client accesses `https://app.example.com/portal/demo/inspect` and the backend listens on `http://127.0.0.1:8080/demo/inspect`.

This example **illustrates how to rewrite and set a canonical set of headers**; TLS certificate files must actually exist, and a complete configuration also needs timeouts, logging, a host allowlist, HTTP→HTTPS redirects, a trust chain, and infrastructure hardening:

```nginx
server {
    listen 443 ssl;
    server_name app.example.com;

    ssl_certificate     /etc/nginx/tls/app.example.com.crt;
    ssl_certificate_key /etc/nginx/tls/app.example.com.key;

    # When the URL lacks a trailing /, redirect to the canonical prefix.
    location = /portal {
        return 308 /portal/;
    }

    location /portal/ {
        # A trailing / on proxy_pass strips /portal/ before forwarding upstream.
        proxy_pass http://127.0.0.1:8080/;

        # Pin the public host instead of taking an arbitrary request value.
        proxy_set_header Host app.example.com;

        # Use only X-Forwarded-* for this example contract.
        proxy_set_header Forwarded "";

        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Host app.example.com;
        proxy_set_header X-Forwarded-Port 443;
        proxy_set_header X-Forwarded-Prefix /portal;

        # Assumes Nginx is the edge directly receiving clients.
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Real-IP $remote_addr;

        # Do not keep legacy indicators outside the contract.
        proxy_set_header X-Forwarded-Ssl "";
    }
}
```

**Explanation:**

- `location /portal/` + `proxy_pass http://127.0.0.1:8080/;`: the URI is rewritten by the proxy from `/portal/demo/inspect` to `/demo/inspect` according to Nginx's rules for prefix locations.
- Both `Host` and `X-Forwarded-Host` are set to `app.example.com` from the approved server configuration, not from the client's raw `Host`.
- `X-Forwarded-Proto=https` and `X-Forwarded-Port=443` convey the public scheme/port after Nginx handles TLS.
- `X-Forwarded-Prefix=/portal` advertises the external prefix; **it does not automatically rewrite URLs in Spring if the version/filter does not support it**.
- `X-Forwarded-For $remote_addr` only makes sense when Nginx is actually the **trusted edge receiving clients directly**. If a CDN or load balancer sits in front of it, you must configure a specific real-client-IP trust chain; do not arbitrarily pick the first or last element of a chain.
- `proxy_set_header Forwarded "";` ensures no client-sent RFC header is forwarded in this illustrative setup. In a real system, you must **thoroughly strip/override all variants of forwarded metadata** at the edge, including proprietary headers used by gateways/infrastructure.
- `/portal` is redirected to `/portal/`. HTTP 308 preserves the HTTP method/body by specification; the application should account for this if the route permits side-effecting methods. This example uses it only as a prefix entry point.
- If Nginx runs in a separate container, `127.0.0.1` points to the **Nginx container itself**, not the Spring container; replace it with an authorized service DNS name such as `app-service:8080` on a private network.

**Limitations of the example:** Nginx does not provide dummy certificates in this snippet; the TLS paths illustrate where files live in a real deployment. You must also protect the backend with a firewall/network policy rather than relying solely on `proxy_set_header`. If multiple ingresses reach the application, every ingress must enforce the same trust policy.

### 7.1. One change in `location` can break the entire path

Compare these cases:

```nginx
# Pattern A: the /portal/ URI prefix is replaced by / when proxy_pass has a trailing /.
location /portal/ {
    proxy_pass http://127.0.0.1:8080/;
}

# Pattern B: the original URI is typically preserved when proxy_pass has no URI after the host.
location /portal/ {
    proxy_pass http://127.0.0.1:8080;
}
```

The two snippets above are **for comparison**, not configurations to run simultaneously. With Pattern A, the backend maps `/demo/inspect`. With Pattern B, the backend may receive `/portal/demo/inspect`, so if the controller only maps `/demo/inspect` it will return 404 unless a corresponding context/mapping exists.

**Do not fix a missing-prefix bug by prepending `/portal` across all controllers.** Decide the contract up front: whether the prefix is kept on the backend or stripped by the proxy, then configure URL builders and headers consistently.

## 8. Runnable Spring Boot Java 17+ example: dynamic URLs and canonical URLs

The example uses Spring MVC. It provides:

- `GET /demo/inspect`: shows request metadata **after forwarded-header processing** and the URL Spring attempts to reconstruct. It returns only basic demo information and does not expose session tokens or sensitive IPs.
- `GET /demo/next`: returns HTTP **302 Location** to the fixed public URL `https://app.example.com/portal/demo/inspect`; this avoids reset/callback links depending on raw request hosts.
- `GET /demo/link`: returns the canonical link URL based on the server property, suitable for JSON or email templates.

**The demo has no authentication and is not designed for public sensitive endpoints.** Its purpose is to understand public URLs when running behind a proxy.

### 8.1. Create the project

Create a Spring Boot **3.5.x** project with **Java 17+**, dependencies **Spring Web** (`spring-boot-starter-web`) and **Spring Boot Starter Test** (`spring-boot-starter-test`, test scope). Use the Maven Wrapper generated by Spring Initializr.

```text
src/
├─ main/
│  ├─ java/com/example/demo/
│  │  ├─ ProxyUrlsApplication.java
│  │  └─ PublicUrlController.java
│  └─ resources/
│     └─ application.properties
└─ test/java/com/example/demo/
   └─ PublicUrlIntegrationTest.java
```

### 8.2. Configuration file

**`src/main/resources/application.properties`**

```properties
server.port=8080

# With a trusted proxy, let the Spring framework reconstruct public request metadata.
server.forward-headers-strategy=framework

# Canonical URL configured by the operator, not taken from arbitrary headers.
app.public-base-url=https://app.example.com/portal

# Helps when Tomcat performs a context-root redirect after TLS termination.
server.tomcat.redirect-context-root=false
```

In the local demo, call `http://localhost:8080` directly with headers simulating a proxy to observe behavior. In production, **this port must not be left public** when `server.forward-headers-strategy=framework` is enabled; a trusted proxy boundary must sit in front of it.

### 8.3. Main class

**`src/main/java/com/example/demo/ProxyUrlsApplication.java`**

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ProxyUrlsApplication {
    public static void main(String[] args) {
        SpringApplication.run(ProxyUrlsApplication.class, args);
    }
}
```

### 8.4. Controller

**`src/main/java/com/example/demo/PublicUrlController.java`**

```java
package com.example.demo;

import java.net.URI;
import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;
import org.springframework.web.util.UriComponentsBuilder;

@RestController
@RequestMapping("/demo")
public class PublicUrlController {

    private final URI canonicalPublicBase;

    public PublicUrlController(
            @Value("${app.public-base-url}") String configuredBase) {
        URI base = URI.create(configuredBase).normalize();

        // Simple policy for the lab: one fixed origin + prefix.
        if (!"https".equalsIgnoreCase(base.getScheme())
                || !"app.example.com".equalsIgnoreCase(base.getHost())
                || !"/portal".equals(base.getPath())
                || base.getRawQuery() != null
                || base.getRawFragment() != null) {
            throw new IllegalArgumentException(
                "Invalid configured public base URL"
            );
        }
        this.canonicalPublicBase = base;
    }

    @GetMapping("/inspect")
    public RequestInfo inspect(HttpServletRequest request) {
        // Spring builds the base from the request already processed by the framework.
        String derivedBase =
            ServletUriComponentsBuilder.fromCurrentContextPath()
                .build()
                .toUriString();

        return new RequestInfo(
            request.getScheme(),
            request.getServerName(),
            request.getServerPort(),
            request.getContextPath(),
            derivedBase,
            canonicalPublicBase.toString()
        );
    }

    @GetMapping("/link")
    public Map<String, String> link() {
        return Map.of("url", canonicalInspectUrl().toString());
    }

    @GetMapping("/next")
    public ResponseEntity<Void> next() {
        return ResponseEntity.status(HttpStatus.FOUND)
            .location(canonicalInspectUrl())
            .build();
    }

    private URI canonicalInspectUrl() {
        return UriComponentsBuilder.fromUri(canonicalPublicBase)
            .path("/demo/inspect")
            .build()
            .toUri();
    }

    public record RequestInfo(
        String scheme,
        String host,
        int port,
        String contextPath,
        String derivedBase,
        String configuredPublicBase
    ) {}
}
```

**Why does the example separate two URL forms?**

1. `derivedBase` uses `ServletUriComponentsBuilder.fromCurrentContextPath()` and **the framework-processed request**. If trusted headers indicate `https` and `app.example.com`, the dynamic value reflects that information. If the version/framework handles `X-Forwarded-Prefix` as expected, the public `/portal` path also appears.
2. `canonicalPublicBase` is an operator-configured URI. Even if a request arrives over an internal path or through a reverse proxy that does not forward the prefix, `canonicalInspectUrl()` still produces **`https://app.example.com/portal/demo/inspect`**.
3. `URI.create(...).normalize()` is **not** a general-purpose anti-URL-poisoning function; the constructor only accepts the exact scheme/host/prefix set for the demo. With multiple public domains, you must design an explicit allowlist or tenant mapping rather than removing checks to accept any `Host`.
4. `ResponseEntity.status(FOUND).location(uri)` sets the `Location` header for a 302 redirect. `@RestController` does not automatically concatenate paths or return view names like `@Controller`.
5. The URI has `https` even though the connection to Tomcat is `http`, because that is the public URL the operator wants the client to see.
6. To build URLs containing IDs/queries from input, use `UriComponentsBuilder` and encode **the appropriate components**, rather than concatenating user strings directly into URLs. See the example in section 10.

### 8.5. Running locally

```bash
java -version
./mvnw spring-boot:run
```

On Windows, use `mvnw.cmd spring-boot:run` and `curl.exe` if PowerShell aliases `curl`.

**Without sending forwarded headers** (direct request to the local server):

```bash
curl -i http://localhost:8080/demo/inspect
```

JSON output similar to:

```json
{
  "scheme": "http",
  "host": "localhost",
  "port": 8080,
  "contextPath": "",
  "derivedBase": "http://localhost:8080",
  "configuredPublicBase": "https://app.example.com/portal"
}
```

This is the **expected output for HTTP localhost without a proxy and without forwarded headers**, not an actual run log. JSON field order/formatting depends on Jackson; do not test JSON strings with fixed whitespace.

**Simulating a trusted proxy locally** (only suitable for test/dev on a non-public port):

```bash
curl -i http://localhost:8080/demo/inspect \
  -H "X-Forwarded-Proto: https" \
  -H "X-Forwarded-Host: app.example.com" \
  -H "X-Forwarded-Port: 443" \
  -H "X-Forwarded-Prefix: /portal"
```

Expected after the filter:

- `"scheme":"https"` and `"host":"app.example.com"`.
- `"port"` reflects standard HTTPS (typically 443).
- `contextPath` / `derivedBase`: may reflect `/portal` **if the Spring version/config enables forwarded-prefix processing**; verify specifically against the framework version you are running.
- `"configuredPublicBase":"https://app.example.com/portal"` is always fixed per the property.

**Checking the redirect:**

```bash
curl -i http://localhost:8080/demo/next
```

Expected HTTP `302 Found` and:

```http
Location: https://app.example.com/portal/demo/inspect
```

This redirect **does not depend on forwarded headers** because it is built from the canonical base. Do not use `curl -L` when you only want to inspect the header: it may try to reach the domain in `Location` (for example, a public domain without DNS configured in the demo environment).

**Checking the JSON link:**

```bash
curl -i http://localhost:8080/demo/link
```

Expected:

```json
{"url":"https://app.example.com/portal/demo/inspect"}
```

This is the URL that can be published if real infrastructure routes that hostname/prefix; the local demo does not create DNS records or TLS certificates for `app.example.com`.

## 9. Integration testing: real HTTP connector and simulated headers

Testing controllers only with `MockMvc` may not fully observe embedded server and filter-chain behavior as when requests arrive over HTTP. This example uses `@SpringBootTest(webEnvironment=RANDOM_PORT)` to start local Tomcat and **JDK HttpClient** to send headers simulating a trusted proxy.

**`src/test/java/com/example/demo/PublicUrlIntegrationTest.java`**

```java
package com.example.demo;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class PublicUrlIntegrationTest {

    @LocalServerPort
    int port;

    private final HttpClient client = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.NEVER)
        .build();

    private final ObjectMapper json = new ObjectMapper();

    private URI local(String path) {
        return URI.create("http://localhost:" + port + path);
    }

    @Test
    void directRequestSeesLocalScheme() throws Exception {
        HttpRequest req = HttpRequest.newBuilder(local("/demo/inspect"))
            .GET()
            .build();

        HttpResponse<String> res = client.send(
            req, HttpResponse.BodyHandlers.ofString()
        );

        assertEquals(200, res.statusCode());
        JsonNode body = json.readTree(res.body());
        assertEquals("http", body.get("scheme").asText());
        assertEquals("localhost", body.get("host").asText());
        assertEquals(
            "https://app.example.com/portal",
            body.get("configuredPublicBase").asText()
        );
    }

    @Test
    void trustedProxySimulationRestoresSchemeAndHost() throws Exception {
        HttpRequest req = HttpRequest.newBuilder(local("/demo/inspect"))
            .header("X-Forwarded-Proto", "https")
            .header("X-Forwarded-Host", "app.example.com")
            .header("X-Forwarded-Port", "443")
            .header("X-Forwarded-Prefix", "/portal")
            .GET()
            .build();

        HttpResponse<String> res = client.send(
            req, HttpResponse.BodyHandlers.ofString()
        );

        assertEquals(200, res.statusCode());
        JsonNode body = json.readTree(res.body());
        assertEquals("https", body.get("scheme").asText());
        assertEquals("app.example.com", body.get("host").asText());
        assertTrue(
            body.get("derivedBase").asText()
                .startsWith("https://app.example.com")
        );
    }

    @Test
    void redirectUsesCanonicalPublicUrl() throws Exception {
        HttpRequest req = HttpRequest.newBuilder(local("/demo/next"))
            .GET()
            .build();

        HttpResponse<Void> res = client.send(
            req, HttpResponse.BodyHandlers.discarding()
        );

        assertEquals(302, res.statusCode());
        assertEquals(
            "https://app.example.com/portal/demo/inspect",
            res.headers().firstValue("Location").orElseThrow()
        );
    }

    @Test
    void linkContainsPublicPrefixExactlyOnce() throws Exception {
        HttpRequest req = HttpRequest.newBuilder(local("/demo/link"))
            .GET()
            .build();

        HttpResponse<String> res = client.send(
            req, HttpResponse.BodyHandlers.ofString()
        );

        assertEquals(200, res.statusCode());
        JsonNode body = json.readTree(res.body());
        assertEquals(
            "https://app.example.com/portal/demo/inspect",
            body.get("url").asText()
        );
    }
}
```

Run:

```bash
./mvnw test
```

**Design outcome:** with a compatible Spring Boot 3.5.x project, embedded Tomcat, and `server.forward-headers-strategy=framework` in effect, **all four tests are expected to pass**. They illustrate the framework reconstructing scheme/host and canonical redirects. **This is not a report of tests executed in a real repository.**

What these tests **do not prove**:

- Whether real Nginx strips all forwarded headers from the Internet.
- Whether the backend port is directly reachable from an external network.
- Whether the Spring/framework version handles `X-Forwarded-Prefix` as expected: the tests only check scheme/host; the canonical link test checks that the prefix is not duplicated, **which does not mean `derivedBase` dynamically includes the prefix**.
- Whether the OAuth login flow, cookie path, `SecurityFilterChain`, or CORS policy work properly on the production host.

For thorough QA, also test requests through the edge HTTPS URL and verify `Location`, `Set-Cookie`, page links, and authorization per the application contract.

## 10. Generating correct URLs for links, redirects, queries, and callbacks

### 10.1. Absolute URLs from a trusted request

In Spring MVC, once trusted proxy headers and the proper filter are ensured, APIs such as `ServletUriComponentsBuilder.fromCurrentContextPath()` can reconstruct the scheme, host, and context path. Example snippet inside a controller:

```java
String base = ServletUriComponentsBuilder
    .fromCurrentContextPath()
    .build()
    .toUriString();
```

**Do not use this result for security-sensitive operations merely because it looks like HTTPS.** If the edge does not sanitize input, an attacker can control the host. For links sent via email, a fixed canonical base is usually simpler.

### 10.2. Relative URLs and prefixes

A relative link like `/demo/inspect` is a path **from the domain root**, not from `/portal`. Therefore:

- If the app is public at `/portal`, an `href` of `/demo/inspect` can lead to `https://app.example.com/demo/inspect` (**missing the prefix**).
- An `href` of `demo/inspect` is a relative path against the current page URL; it can break if the page depth changes.
- With Thymeleaf/JSP templates, use context-aware URL helpers (`@{/...}` in Thymeleaf when context is configured properly), and test behind the proxy.
- With SPAs, configure the router base, asset public path, fetch base URL, and HTML `<base>` carefully. Misconfiguring any one of these layers can still cause 404s for assets even when backend APIs return normally.
- When an app is public under a subpath while the backend context root is empty, if the framework does not know the proxy prefix, default context-aware links may still omit the prefix. You need a proper proxy/framework contract or a configured public base on the frontend.

### 10.3. Query/path parameters must be encoded separately

Illustrative snippet inside a service/controller, not a standalone class:

```java
URI uri = UriComponentsBuilder
    .fromUri(URI.create("https://app.example.com/portal"))
    .path("/search")
    .queryParam("q", "{q}")
    .encode()
    .buildAndExpand("a&b accented")
    .toUri();
```

The resulting URI contains the percent-encoded `q` query parameter, without splitting `a&b` into two parameters. Characters like `&` in data must be protected. Do not concatenate:

```java
// ANTI-PATTERN: data can break URL structure.
String link = "https://app.example.com/portal/search?q=" + userQuery;
```

When a target URL is user-supplied, add **destination validation**: allow only internal-relative URLs or an allowlist of scheme/host/port to prevent open redirects. `URI.normalize()` only normalizes a URI according to its rules; it does not block malicious URLs on its own.

### 10.4. OAuth/OIDC redirects and SSO

If Spring Security OAuth2 login uses a callback endpoint such as:

```text
https://app.example.com/portal/login/oauth2/code/my-client
```

then the identity provider must register the **exact public URL**, not `http://app-service:8080/login/oauth2/code/my-client`. Check:

- `https`, host, external port, and `/portal` prefix.
- The actual URL generated by Spring Security after forwarded processing.
- The authorization request redirect URI and the value registered at the IdP.
- Session cookies, `SameSite`/`Secure`, and OAuth state across redirect steps.
- Proxy path rewriting on the callback route so the backend receives `/login/oauth2/code/my-client`.

If the callback is wrong, do not fix it by allowing broad wildcard redirect URIs or disabling CSRF/state. Identify which layer is missing the protocol/host/prefix and fix the trust/proxy configuration.

## 11. Cookies and sessions behind a TLS-terminating proxy

The backend may receive HTTP while the browser is speaking HTTPS with the proxy. Cookies and security handling based on the **public context** must accurately reflect HTTPS.

Common Spring Boot Servlet options:

```properties
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax
```

For production HTTPS:

```properties
server.servlet.session.cookie.secure=true
```

`Secure` requires the browser to send the cookie over HTTPS; the internal app can still communicate over HTTP with the reverse proxy. `HttpOnly` restricts JavaScript from reading the cookie. `SameSite` helps restrict certain cross-site cookie flows, though it **does not replace CSRF protection**.

Distinguish **cookie `Path`**:

- If the backend context path is `/` while the public prefix is `/portal`, the session cookie may have `Path=/`; the browser still sends it to `/portal/...`, though the cookie is sent more broadly than necessary.
- If the cookie has `Path=/portal`, the browser sends it to `/portal/...`, but will not send it to public paths under `/other`.
- If the proxy rewrites paths, do not assume the cookie path always matches automatically; inspect the `Set-Cookie` header and the cookie sent back by the browser.
- If using Nginx `proxy_cookie_path`, rewrite only when truly needed and avoid duplicating prefixes. Cookie path rewrite rules only affect cookies, not link/controller mappings.

For OAuth, login, and cookie-based forms, inspect the **`Secure`/`HttpOnly`/`SameSite` policy**, origin, CSRF token, and redirect URLs together. Redirecting to `http` or a different host can prevent the cookie from being sent, creating a login loop even though the session still exists on the server.

**Do not output session cookies, CSRF tokens, `Authorization` headers, or access tokens in debug endpoints or public logs.**

## 12. CORS is related but not synonymous with forwarded URLs

CORS is a **browser** mechanism applied when JavaScript from origin A wants to read a response from origin B. An origin consists of scheme, host, and port, **not the path prefix**:

```text
https://app.example.com/portal
https://app.example.com/another
  -> same origin

https://app.example.com
https://api.example.com
  -> different host, different origin

http://app.example.com
https://app.example.com
  -> different scheme, different origin
```

If a public website at `https://app.example.com` calls an API at `https://api.example.com`, the CORS policy must match the **public browser origin**, not `http://app-service:8080` on the internal network.

CORS allowlist example for Spring MVC (configuration snippet, **no need to put in the demo project if all requests are same-origin**):

```java
@Configuration
class CorsConfig implements WebMvcConfigurer {
    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
            .allowedOrigins("https://app.example.com")
            .allowedMethods("GET", "POST")
            .allowedHeaders("Content-Type", "Authorization");
    }
}
```

Import `org.springframework.context.annotation.Configuration`, `org.springframework.web.servlet.config.annotation.WebMvcConfigurer`, and `CorsRegistry`. When Spring Security is present, integrate CORS into the filter chain so **preflight OPTIONS** is handled before authentication blocks the request; do not disable authentication just to "fix CORS."

**Do not** use `Access-Control-Allow-Origin: *` combined with credentialed cross-origin requests; do not reflect an arbitrary `Origin` without an allowlist. CORS **does not** protect an API from curl/server-to-server traffic and does not replace CSRF/authentication/authorization.

A request with the wrong scheme/host inside the backend behind a proxy can break link building and origin comparisons, but **you should not fix it by opening CORS to all domains**. Fix the forwarded headers and public URLs first, then configure the origin allowlist as needed.

## 13. Common issues and how to investigate

| Symptom | Possible cause | Check and fix |
| --- | --- | --- |
| Redirect `Location: http://localhost:8080/...` | Missing `X-Forwarded-Proto/Host` or app not processing them | Check edge headers, `server.forward-headers-strategy`, HTTP response from public URL |
| Browser reports mixed content | Absolute URLs generated with internal HTTP scheme | Fix forwarded proto or use an HTTPS canonical base |
| Links missing `/portal` | Proxy strips path but app does not know the prefix | Check `X-Forwarded-Prefix`, filter/version, template/router public base |
| Links become `/portal/portal` | Context path configured while also adding prefix manually | Standardize rewrite or preserve model, avoid double-prefix |
| A route 404s only through proxy | Wrong `location`/`proxy_pass` or prefix/trailing slash | Compare URI entering Nginx vs URI actually received upstream |
| OAuth `redirect_uri_mismatch` | Callback built using internal scheme/host/path | Compare public redirect and IdP registered URI |
| Login loop / cookie not sent | Cookie `Secure`/`Path`/`SameSite` mismatch, wrong redirect host | Inspect `Set-Cookie` and subsequent browser `Cookie` request header |
| Redirects to strange domain from request header | Proxy forwards untrusted host/forwarded values | Strip/override at edge, host allowlist, canonical URL for critical links |
| IP recorded in logs is proxy IP | Trusted `X-Forwarded-For` not handled | Design trust chain, access log configuration, do not blindly pick client IP |
| Local tests pass but prod fails | CDN/ingress has different routing/headers than local Nginx | Test direct-to-backend and through real URL, trace each hop |
| CORS fails even with right URL links | Public origin/credentials/preflight config mismatch | Review `Origin`, `Access-Control-Allow-Origin`, OPTIONS, Spring Security CORS |
| Proxy uses HTTPS but `request.isSecure()` is false | Trusted forwarded proto not applied at backend | Check `framework`/`native`, proxy headers, and cookie policy |

### Useful checks

**Inspect response headers externally:**

```bash
curl -k -I https://app.example.com/portal/demo/inspect
```

`-I` sends **HEAD**; use only if the endpoint supports HEAD. `-k` skips TLS verification and **is only for debugging certificates in an authorized environment**, not for final security testing; during real testing, omit `-k` to verify the certificate chain properly.

**Inspect a redirect without following it:**

```bash
curl -i https://app.example.com/portal/demo/next
```

Check `Location`; it must have the right public scheme, host, and path. If you use `curl -L`, the client follows the redirect and can hide where the bad redirect originated.

**Test spoofed host headers at the edge (only in infrastructure you are authorized to test):**

```bash
curl -i https://app.example.com/portal/demo/next \
  -H "X-Forwarded-Host: attacker.invalid"
```

If the edge is configured properly, the header from the Internet must be stripped/overwritten, and `Location` must still point to the allowed domain. **The fact that the demo's `/demo/next` is always canonical does not prove the edge is secure**; also verify at the request-metadata endpoint, controlled access logs, and gateway config.

**Verify whether the path is rewritten:**

- External request: `/portal/demo/inspect`.
- Expected upstream: `/demo/inspect`.
- Controller mapping: `@GetMapping("/demo/inspect")` combined with class-level `@RequestMapping("/demo")`.
- If upstream still sees `/portal/demo/inspect`, check the `/` in `proxy_pass` and `location`.
- Do not set `server.servlet.context-path=/portal` in the application when the proxy is stripping `/portal`.

## 14. How to test in production-like environments without arbitrary fake headers

A QA test suite should have two separate tracks:

1. **Direct-to-app in an isolated environment:** verify that Spring handles `Forwarded`/`X-Forwarded-*` according to the contract the proxy is expected to send. The Java tests in section 9 illustrate this group. Do not treat this as proof that the trust boundary is secure.
2. **Through the real proxy/ingress/CDN:** send requests to the public HTTPS domain; verify scheme, host, port, path, links, and redirects are correct. Also intentionally send spoofed headers at the **edge** to confirm they are dropped and do not affect the backend.

Behavior checklist:

- [ ] `https://app.example.com/portal/demo/inspect` actually routes to the right controller.
- [ ] `request.getScheme()` is `https` after applying trusted forwarded metadata.
- [ ] `request.getServerName()` is the approved public host, not internal DNS.
- [ ] Port reflects the external port, not 8080 when clients use HTTPS 443.
- [ ] Dynamic/templated URLs contain the `/portal` prefix **exactly once** when required by the contract.
- [ ] Redirect `Location` never contains `http://app-service:8080` or an attacker domain.
- [ ] Email links, webhooks, and OAuth callbacks are built from a canonical/allowlisted public URL.
- [ ] Cookie `Secure`, `HttpOnly`, `SameSite`, and `Path` match public HTTPS.
- [ ] CORS allowed origins contain the exact scheme/host/port, not copied from the backend URL.
- [ ] Proxy strips/overrides both `Forwarded` and `X-Forwarded-*` from untrusted input.
- [ ] Backend is reachable only from the trusted proxy/sidecar or private network.
- [ ] No privilege escalation or treating `X-Forwarded-For` as an auth source before a valid trust chain.
- [ ] No redirect loops at `/portal` → `/portal/` or HTTP→HTTPS.
- [ ] Proxy, framework, container, and Spring Security are all patched and up to date.

## 15. Notes for Spring WebFlux

The main example uses **Spring MVC** (`jakarta.servlet.http.HttpServletRequest` and `ForwardedHeaderFilter`). With **Spring WebFlux**, requests are not wrapped by a Servlet filter; Spring Framework uses **`ForwardedHeaderTransformer`** before dispatch to update scheme/host/prefix information according to allowed headers.

Illustrative snippet (not a standalone WebFlux application):

```java
// Inside a WebFlux handler; exchange is a valid ServerWebExchange.
URI requestUri = exchange.getRequest().getURI();
String path = exchange.getRequest().getPath().value();
```

Import `java.net.URI` and the appropriate WebFlux APIs; do not use `HttpServletRequest` or `ServletUriComponentsBuilder` on a Netty stack. Spring Boot's `server.forward-headers-strategy=framework` integrates the appropriate handler for the stack, but **the trust boundary at the proxy is still mandatory**.

If WebFlux uses `X-Forwarded-Prefix`, test the specific `ForwardedHeaderTransformer` behavior for your version and gateway contract. For strict response links, a canonical base configuration remains useful.

## 16. Self-check

**Q1.** The browser calls `https://app.example.com/portal/orders`, but the backend receives `http://10.0.0.5:8080/orders`. Is this necessarily a bug?  
**A:** No; this can be proper TLS termination and path-prefix rewriting. A bug occurs when the app uses the internal scheme/host/path to generate public URLs or the proxy fails to route accordingly.

**Q2.** Is setting only `X-Forwarded-Proto: https` enough to restore all public URLs?  
**A:** No. You also need the public host/port and possibly the prefix. More importantly, only trust headers set by a legitimate proxy.

**Q3.** Is `server.forward-headers-strategy=framework` safe if outsiders can call port 8080 directly?  
**A:** No. Clients could then send their own forwarded headers. The backend must sit behind a trust boundary and the edge must sanitize headers.

**Q4.** Why shouldn't `X-Forwarded-Host` be used directly to generate password-reset links?  
**A:** Because the host can be spoofed if the edge mishandles it. Use a canonical public base/allowlist instead.

**Q5.** The proxy strips `/portal`, yet the backend sets `server.servlet.context-path=/portal`—what usually happens?  
**A:** Requests arriving at the backend lack the required context path and easily return 404. Standardize on either rewriting or preserving.

**Q6.** Is `X-Forwarded-Prefix` always understood automatically in `native` mode?  
**A:** No. Native support varies by container/version; you must verify `request.getContextPath()` and generated links, or use another model.

**Q7.** Are the two paths `/portal` and `/other` on the same `https://app.example.com` two separate CORS origins?  
**A:** No. An origin consists of scheme/host/port, not the path.

**Q8.** If the proxy converts HTTPS→HTTP, does a `Secure` session cookie stop working in the browser?  
**A:** No, as long as the browser accesses the public HTTPS URL and the cookie is issued appropriately. However, request metadata/headers and cookie config must be correct.

**Q9.** What can cause a redirect `Location: https://app.example.com/demo` instead of `/portal/demo`?  
**A:** The framework not receiving/applying the public prefix, templates hardcoding root paths, or inconsistent proxy path rewriting.

**Q10.** If a Java test calling the backend directly with `X-Forwarded-Host: app.example.com` passes, does that prove Nginx rejects forged headers from the Internet?  
**A:** No. You must test **through the edge** and verify the proxy configuration and trust chain.

## 17. Official documentation

- Spring Boot 3.5 — *Embedded Web Servers / Running Behind a Front-end Proxy Server*: https://docs.spring.io/spring-boot/3.5/how-to/webserver.html
- Spring Framework 6.2 — *Servlet Filters / Forwarded Headers / X-Forwarded-Prefix*: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/filters.html
- Spring Framework — *ServletUriComponentsBuilder API*: https://docs.spring.io/spring-framework/docs/6.2.11/javadoc-api/org/springframework/web/servlet/support/ServletUriComponentsBuilder.html
- Spring Framework — *WebFlux Forwarded Headers*: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
- Spring Security — *CORS Integration*: https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html
- Spring Security — *OAuth2 Login*: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html
- Nginx — *ngx_http_proxy_module / proxy_pass and proxy_set_header*: https://nginx.org/en/docs/http/ngx_http_proxy_module.html
- RFC 7239 — *Forwarded HTTP Extension*: https://www.rfc-editor.org/rfc/rfc7239
- MDN — *Same-origin policy*: https://developer.mozilla.org/en-US/docs/Web/Security/Same-origin_policy
- OWASP — *Unvalidated Redirects and Forwards*: https://cheatsheetseries.owasp.org/cheatsheets/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.html

**Conclusion:** when running Spring Boot behind a reverse proxy, never treat internal request details as the public address. First decide the contract for TLS termination, host, port, and prefix rewriting; next configure trusted `Forwarded`/`X-Forwarded-*` headers at the edge and choose the appropriate handling mode in Spring; finally verify **redirects, links, cookies, OAuth callbacks, and CORS origins** over the real HTTPS URL. For security-sensitive links, use a controlled canonical public base to avoid relying on untrusted header data.