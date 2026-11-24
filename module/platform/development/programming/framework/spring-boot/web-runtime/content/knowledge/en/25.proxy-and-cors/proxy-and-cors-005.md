# Generating redirects, absolute links, and cookies with the right public address

When deploying a Spring Boot application behind a **reverse proxy, load balancer, ingress, or CDN**, the address the application sees is usually **different from the address the browser actually visits**. For example:

- The user opens: `https://shop.example.test/account`.
- NGINX receives HTTPS on port 443, terminates TLS, and forwards HTTP to `http://127.0.0.1:8080/account`.
- Spring Boot sees only the connection from the proxy unless configured to process forwarded headers.
- The controller generates `Location: http://127.0.0.1:8080/login`, emails contain internal links, or session cookies lack `Secure`: all of these can break in production.

This lesson shows how to make **redirects, absolute links, and cookies** match the **public address** seen by the browser while avoiding trusting forged user headers. The focus is **Spring Boot 3.x + Spring MVC/Servlet + Java 17+**, with extensions for WebFlux, Spring Security/OAuth2, and multi-hop proxies.

**Core principle:** define a **trusted public origin/base URL**, establish a **trust boundary** at the proxy, pass sufficient scheme/host/port/prefix metadata, let the framework generate URLs from the normalized request, and configure cookies explicitly according to the browser's HTTPS/domain/path policy. **You cannot solve the whole problem with CORS alone or by toggling a single Boot property.**

## 1. Learning objectives

After this lesson, you will be able to:

- Distinguish the internal URL between proxy and application from the public URL the client needs to see.
- Explain `Host`, `Forwarded`, `X-Forwarded-Proto`, `X-Forwarded-Host`, `X-Forwarded-Port`, and `X-Forwarded-Prefix`.
- Choose `server.forward-headers-strategy=none/native/framework` in Spring Boot 3.x and explain the trust prerequisites.
- Write `redirect:/...` redirects and build absolute URLs with `ServletUriComponentsBuilder` or a configured public base URL, knowing when to use each.
- Configure session cookies and custom cookies with `Secure`, `HttpOnly`, `SameSite`, `Domain`, and `Path`; distinguish Servlet container session cookies from Spring Session cookies.
- Diagnose HTTPS→HTTP redirects, `:8080` leaking into URLs, missing/doubled prefixes, broken OAuth2 `redirect_uri` values, and unsent cookies.
- Test a runnable Spring Boot Java 17+ example with an illustrative NGINX configuration and `curl` commands.
- Design safely against Host header injection, forged forwarded headers, open redirects, and cross-origin cookie misuse.

## 2. Why does the server address differ from the public address?

Consider the request flow:

```text
                  Public browser
        GET https://shop.example.test/account
                           |
                           | TLS / HTTPS :443
                           v
             NGINX edge / ingress / LB
                           |
                           | HTTP :8080 (internal network)
                           | Host: shop.example.test
                           | X-Forwarded-Proto: https
                           | X-Forwarded-Host: shop.example.test
                           | X-Forwarded-Port: 443
                           v
             Spring Boot / embedded Tomcat
                           |
                           v
                 @Controller handler
```

On the proxy→Boot hop, the actual socket may use scheme `http`, local port `8080`, and a remote address equal to the proxy's address. If the application builds absolute URLs from the internal connection details without adjustment, it can generate wrong URLs:

```text
Wrong: http://shop.example.test:8080/done
Wrong: http://127.0.0.1:8080/done
Right: https://shop.example.test/done
```

The right address depends on your **actual public deployment**. Another application may be exposed at `https://portal.example.test/app` or use a non-standard port; do not force `https://shop.example.test` onto every system.

### 2.1. Three kinds of addresses to distinguish

| Kind | Example | What is it used for? |
| --- | --- | --- |
| Application socket address | `http://127.0.0.1:8080` | Proxy calling the origin, internal health checks |
| Public origin address | `https://shop.example.test` | Scheme + hostname + public port if any |
| Public base URL including prefix | `https://shop.example.test/portal` | Links clients should see when the app is served under a prefix |

An **origin** is scheme + host + port; a **base URL** may also include a path prefix. Cookie `Domain` and `Path` are separate rules browsers use to decide whether to send cookies; they are never derived from filesystem paths or upstream IPs.

### 2.2. Signs of misconfigured proxy URLs

- Browser is redirected from HTTPS to HTTP; this can trigger mixed-content warnings, HTTPS enforcement loops, or login failures.
- HTTP `Location` contains `localhost`, a private IP, `:8080`, or is missing `/portal`.
- "Verify your email" messages point to an internal hostname that external users cannot open.
- OAuth2/OIDC `redirect_uri` is `http://...` and fails to match the URI registered with the identity provider.
- Session cookie is issued yet not sent back by the browser on later requests due to `Secure`, `Domain`, `Path`, or `SameSite`.
- Multiple proxy/CDN layers append or drop `X-Forwarded-Prefix`, producing doubled paths or 404s.
- Links in JSON/HATEOAS, OpenAPI docs, HTML canonical URLs, or `201 Created` `Location` headers contain non-public hostnames.

## 3. Headers describing the original request

### 3.1. `Host` and actual scheme

`Host` is the request header HTTP/1.1 uses to identify the authority/virtual host. HTTP/2 and HTTP/3 have the `:authority` pseudo-header. A proxy may pass the public `Host` upstream or replace it with an internal host. However, `Host` on a request from the Internet **is not inherently trustworthy** for sensitive links; it can be controlled or spoofed if the edge does not validate hostnames.

If an application builds URLs by concatenating `request.getServerName()` and `request.getScheme()` without proxy handling, the values may reflect the internal hop. Do not fix this by concatenating strings from arbitrary headers manually.

### 3.2. RFC 7239: `Forwarded`

A proxy can emit a single standard header:

```http
Forwarded: for=203.0.113.25;proto=https;host=shop.example.test
```

It communicates the client/hop address, protocol, and host observed by the proxy. Across multiple proxies, the value can be a list of hops. Do not naively take the "first element" and trust it without a trusted-proxy policy: values can be appended onto client-supplied headers.

### 3.3. The `X-Forwarded-*` family

Many environments use the de facto headers:

```http
X-Forwarded-For: 203.0.113.25
X-Forwarded-Proto: https
X-Forwarded-Host: shop.example.test
X-Forwarded-Port: 443
X-Forwarded-Prefix: /portal
```

| Header | Common meaning | Common mistake |
| --- | --- | --- |
| `X-Forwarded-For` | Chain of client/proxy IPs | Trusting fake IPs to bypass rate limits/access controls |
| `X-Forwarded-Proto` | Public scheme `http`/`https` | Losing TLS termination state, generating `http` redirects |
| `X-Forwarded-Host` | Public host from the client's perspective | Host header injection when no allowlist exists |
| `X-Forwarded-Port` | Public port | URLs leak `:8080` or omit a custom port |
| `X-Forwarded-Prefix` | Public prefix when the proxy rewrites paths | Redirects/links/cookies miss or corrupt `/portal` |
| `X-Forwarded-Ssl` | Vendor/legacy HTTPS indicator | Mistaking for a universal standard, inconsistent handling |

Header names do not mean every infrastructure emits all of them. `X-Forwarded-Prefix` is not part of standard RFC 7239 syntax. Apps exposed at the root path usually do not need a prefix; with path rewriting, test against your actual Spring Framework and connector versions.

## 4. Spring Boot's standard mechanism: `forward-headers-strategy`

In Spring Boot 3.3, the key property is:

```properties
server.forward-headers-strategy=framework
```

There are three options:

| Value | How it works | When suitable |
| --- | --- | --- |
| `none` | Skips Boot's forwarded-header processing | App is not behind a trusted proxy; do not want spoofed client headers to have effect |
| `native` | Uses embedded web server support (e.g., Tomcat `RemoteIpValve`) | Proxy sends standard headers the container handles, usually sufficient for scheme/client IP |
| `framework` | Uses Spring Framework mechanisms: `ForwardedHeaderFilter` for Servlet, `ForwardedHeaderTransformer` for reactive | Need Spring to adjust requests/redirects for scheme, host, port, and sometimes prefix |

Boot 3.3 notes that if a proxy sends `X-Forwarded-For` and `X-Forwarded-Proto`, `native` may be sufficient. If more is needed, use `framework`. The default depends on the environment: Boot may automatically choose `native` on certain detected cloud platforms, while other environments default to `none`. **Do not assume which mode the runtime uses**; set it explicitly in deployment config if public URLs depend on it.

For Servlet apps, `ForwardedHeaderFilter` makes the request/response reflect metadata from trusted proxy headers. When handlers call `request.getScheme()`, `getServerName()`, `getServerPort()`, `isSecure()`, or use `ServletUriComponentsBuilder`, the results can be based on the public address rather than the internal socket.

**Important:** from Spring Framework 5.1 onward, `ServletUriComponentsBuilder` **does not read `Forwarded`/`X-Forwarded-*` directly on its own**. It builds URLs from the request already processed by the framework or container. Never both parse forwarded headers manually in a controller and enable `ForwardedHeaderFilter` to "fix it twice."

### 4.1. `ForwardedHeaderFilter` in Servlet applications

With `server.forward-headers-strategy=framework`, Boot registers the appropriate `ForwardedHeaderFilter`. Do not add a second bean out of habit, as two duplicate filters can conflict or complicate debugging.

Spring Framework provides a `removeOnly` mode: it recognizes the headers and **strips them without applying them**. This is a sound choice at a boundary where the app must not trust forwarded data; it does not solve public URL generation if those headers were the only source of the original origin.

Newer Spring Framework versions may provide granular settings for choosing `Forwarded` vs. `X-Forwarded-*` and handling `X-Forwarded-Prefix`; APIs and defaults change across releases. In this lesson's Java 17+ example, only scheme/host/port are relied upon dynamically to avoid depending on version-specific prefix details.

### 4.2. Tomcat and context-root redirects

Spring Boot 3.3 documentation notes: if **Tomcat** runs behind a TLS-terminating proxy, consider:

```properties
server.tomcat.redirect-context-root=false
```

This property allows the forwarded protocol to be applied before context-root redirects in relevant scenarios. It does not "enable HTTPS" for the entire app, nor does it replace proxy header/host configuration. For Jetty, Undertow, or WebFlux/Reactor Netty, check the semantics of that server.

### 4.3. When should you not enable trusting forwarded headers?

If port 8080 on the origin is exposed directly to the Internet, a client can send:

```http
Host: internal-app.example
X-Forwarded-Proto: https
X-Forwarded-Host: attacker.example
```

An application with `framework` enabled and no trust boundary risks generating links to a forged domain. Therefore, **before enabling `framework` or `native` in production**, lock down the network so the origin accepts traffic only from authorized proxies, and configure the proxy to **strip/overwrite client-sent headers**.

## 5. Trust boundary: where it must be placed

### 5.1. Spring has no way to tell real headers from fake ones

`ForwardedHeaderFilter` simply reads HTTP header values. Headers carry no built-in signature or authenticity; a client can send the same header names if the proxy lets them pass. The right defense is:

1. The edge proxy accepts only valid public hostnames and TLS/ports.
2. The edge **strips `Forwarded` and all untrusted `X-Forwarded-*` headers** from client requests.
3. The edge emits only the values it genuinely knows: public scheme/host/port and client IP per policy.
4. If a CDN/LB sits in front of the edge, trust metadata from that hop only after verifying the connection path/allowlist and rewrite rules.
5. The origin binds only to internal networks, preventing direct user access to the app port.
6. The application consumes processed request data and does not parse raw headers manually.

It is especially dangerous to use `X-Forwarded-Host` to construct password-reset links or email URLs: a malicious value can cause **Host header poisoning / password-reset link injection**. Security-sensitive URLs, third-party callbacks, and email links should be built from a **configured/allowlisted `public-base-url`** instead of relying entirely on request headers.

### 5.2. NGINX at the TLS edge

Example where NGINX **receives TLS directly from browsers** on an operator-trusted host. This is a `server` block snippet inside an `http` context; certificate paths are illustrative and must be replaced in real infrastructure:

```nginx
server {
    listen 443 ssl;
    server_name shop.example.test;

    ssl_certificate     /etc/nginx/tls/fullchain.pem;
    ssl_certificate_key /etc/nginx/tls/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;

        # Forward only the hostname accepted by the virtual host/allowlist.
        proxy_set_header Host $host;

        # Strip client-supplied RFC 7239 header.
        proxy_set_header Forwarded "";

        # Overwrite required X-Forwarded-* headers, do not pass raw data through.
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host  $host;
        proxy_set_header X-Forwarded-Port  $server_port;
        proxy_set_header X-Forwarded-For   $remote_addr;

        # No public prefix in this topology.
        proxy_set_header X-Forwarded-Prefix "";
    }
}
```

**Additional configuration needed in practice**: a default vhost handling unknown hostnames, an HTTP→HTTPS redirect on listener 80 if required, certificate renewals, TLS hardening, network ACLs, logging, timeouts, upload/body limits, and deployment orchestration. A `server_name` in one server block **does not replace** a host allowlist for all requests: ensure unmatched hostnames are rejected instead of falling through to a default vhost that still proxies to the app.

Why use `proxy_set_header X-Forwarded-For $remote_addr;` instead of always using `$proxy_add_x_forwarded_for`? In this example of a **first edge seeing the client directly**, setting `$remote_addr` avoids appending onto a forged `X-Forwarded-For` sent by the client. With multiple legitimate proxies/CDNs, you need an explicit trusted-hops/real-IP policy chain rather than blindly preserving data sent from the Internet.

**Do not copy verbatim if NGINX sits behind a CDN**: in that case `$scheme` at NGINX may be internal HTTP and `$remote_addr` is the CDN's IP, not the browser's. You must establish the trusted hop, preserve the public protocol from the right edge, and accept only metadata delivered by an authenticated CDN/LB.

### 5.3. Internal paths and public paths can differ

If NGINX runs in a separate container, `127.0.0.1:8080` points to the **NGINX container**, not Spring Boot. In Docker Compose or Kubernetes, use the appropriate service DNS (for example `http://spring-app:8080`) and verify network isolation.

When deploying public HTTPS with an HTTP origin, internal-hop security depends on the network. If the internal hop traverses an untrusted network, add TLS/mTLS or suitable protection—never assume "HTTPS at the browser" means every hop is encrypted.

## 6. Spring Boot 3.x Java 17+ example: redirects, absolute links, and cookies

The application below provides these endpoints:

- `GET /inspect`: displays scheme, host, port, secure, and two absolute links.
- `GET /go`: redirects to `/done` using `redirect:`.
- `GET /done`: redirect target returning the text `done`.
- `POST /session`: creates an `HttpSession` to observe the session cookie.
- `POST /demo-cookie`: creates an illustrative browser cookie with `Secure`, `HttpOnly`, `SameSite`, and `Path`.

This is a **Spring Boot MVC example without Spring Security and without real login**. Do not use `/session` and `/demo-cookie` as a production authentication policy.

### 6.1. Create the project

Create a project from [Spring Initializr](https://start.spring.io/), choosing Java 17+, Spring Boot **3.x** (e.g., 3.3.x), Gradle/Groovy, and the **Spring Web** dependency. Main dependencies section of `build.gradle` generated by Initializr:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

This is a **Gradle fragment**, not the full `build.gradle`. Initializr generates the Boot plugin, repositories, Java toolchain, and Gradle Wrapper. With Boot 4.x, starter names differ, so use a major version matching the sample code.

Create the structure:

```text
src/main/
  java/demo/
    PublicUrlApplication.java
  resources/
    application.properties
```

### 6.2. Complete Java code

File `src/main/java/demo/PublicUrlApplication.java`:

```java
package demo;

import java.time.Duration;
import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseCookie;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.ResponseBody;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;
import org.springframework.web.util.UriComponentsBuilder;

@SpringBootApplication
public class PublicUrlApplication {

    public static void main(String[] args) {
        SpringApplication.run(PublicUrlApplication.class, args);
    }
}

@Controller
class PublicUrlController {

    private final String publicBaseUrl;

    PublicUrlController(
            @Value("${app.public-base-url}") String publicBaseUrl) {
        this.publicBaseUrl = publicBaseUrl;
    }

    @GetMapping("/inspect")
    @ResponseBody
    public Map<String, String> inspect(HttpServletRequest request) {
        String derived = ServletUriComponentsBuilder
                .fromContextPath(request)
                .path("/done")
                .build()
                .toUriString();

        String canonical = UriComponentsBuilder
                .fromUriString(publicBaseUrl)
                .path("/done")
                .build()
                .toUriString();

        return Map.of(
                "scheme", request.getScheme(),
                "host", request.getServerName(),
                "port", Integer.toString(request.getServerPort()),
                "secure", Boolean.toString(request.isSecure()),
                "derivedUrl", derived,
                "configuredUrl", canonical);
    }

    @GetMapping("/go")
    public String go() {
        return "redirect:/done";
    }

    @GetMapping("/done")
    @ResponseBody
    public String done() {
        return "done\n";
    }

    @PostMapping("/session")
    @ResponseBody
    public String startSession(HttpServletRequest request) {
        request.getSession(true).setAttribute("demo", "created");
        return "session-created\n";
    }

    @PostMapping("/demo-cookie")
    public ResponseEntity<String> demoCookie() {
        ResponseCookie cookie = ResponseCookie
                .from("visitor_choice", "yes")
                .path("/")
                .secure(true)
                .httpOnly(true)
                .sameSite("Lax")
                .maxAge(Duration.ofHours(1))
                .build();

        return ResponseEntity.ok()
                .header(HttpHeaders.SET_COOKIE, cookie.toString())
                .body("cookie-set\n");
    }
}
```

**Why does this example compile?**

- Only `PublicUrlApplication` is `public` and the filename matches the class; `PublicUrlController` in the same `demo` package is scanned by Spring.
- `@Controller` uses `return "redirect:/done"` for redirects rather than writing a text body.
- `@ResponseBody` is placed only on handlers that write JSON/text directly.
- `ServletUriComponentsBuilder.fromContextPath(request)` builds the URL from the scheme, host, port, and context path of the **normalized request**.
- `UriComponentsBuilder.fromUriString(publicBaseUrl)` builds links from a **trusted configured base URL** without relying on client headers; this fits email links, fixed OAuth callbacks, or contexts without an HTTP request.
- `ResponseCookie` writes `Set-Cookie` with explicit security attributes, yet **does not turn the cookie into a session on its own**. The container session is managed separately by `request.getSession(true)`.

The code evaluates `/inspect` per request without storing state in mutable fields. `publicBaseUrl` is a fixed setting; if production needs multiple tenants/hosts, map authenticated tenants to an **allowlist of public origins** instead of using any incoming `Host`.

### 6.3. `application.properties`

File `src/main/resources/application.properties`:

```properties
server.port=8080

# Use only behind a trusted proxy with the origin inaccessible directly from the Internet.
server.forward-headers-strategy=framework
server.tomcat.redirect-context-root=false

# Fixed public URL used for security/email links outside of requests.
app.public-base-url=https://shop.example.test

# Default Servlet container session cookie, intended for HTTPS environments.
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.same-site=lax
server.servlet.session.cookie.path=/
```

This is a **production target configuration behind a TLS proxy**. When running local HTTP at `http://localhost:8080`, the `Secure` cookie flag marks the cookie as requiring HTTPS; normal browsers may not send it over plain HTTP (browsers have an exception for localhost—never rely on that in production). You can use a separate local profile to test non-`Secure` cookies, but never make that the production default.

`app.public-base-url` is a custom application property, **not a built-in Spring Boot property**. Replace it with your published/allowlisted hostname and optional path prefix. With `https://shop.example.test/portal`, `.path("/done")` produces `https://shop.example.test/portal/done` as long as the base has no stray trailing slash.

### 6.4. Running

From the directory containing the Gradle Wrapper:

```bash
./gradlew bootRun
```

On Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

This application requires Spring dependencies, so `javac PublicUrlApplication.java` alone lacks the classpath; create a Gradle/Maven project and run it. If port 8080 is in use, stop the old process or configure another port and update test commands accordingly.

### 6.5. Local test without forwarded headers

```bash
curl -sS http://localhost:8080/inspect
```

When hitting HTTP on 8080 directly without forwarded headers, the JSON output has values equivalent to:

```json
{
  "scheme": "http",
  "host": "localhost",
  "port": "8080",
  "secure": "false",
  "derivedUrl": "http://localhost:8080/done",
  "configuredUrl": "https://shop.example.test/done"
}
```

JSON property ordering is not guaranteed; this is **illustrative output** corresponding to a default local request. The key point to notice is the difference between **derivedUrl** (from the request) and **configuredUrl** (from the fixed public URL).

### 6.6. Testing simulated forwarded headers locally

**Only for testing the feature in an isolated development environment**, you can send headers as if from a trusted proxy:

```bash
curl -sS \
  -H 'X-Forwarded-Proto: https' \
  -H 'X-Forwarded-Host: shop.example.test' \
  -H 'X-Forwarded-Port: 443' \
  http://localhost:8080/inspect
```

With `server.forward-headers-strategy=framework`, expected output:

```json
{
  "scheme": "https",
  "host": "shop.example.test",
  "port": "443",
  "secure": "true",
  "derivedUrl": "https://shop.example.test/done",
  "configuredUrl": "https://shop.example.test/done"
}
```

In HTTP URL formatting, the default port 443 is usually omitted from `https://...`, even though `getServerPort()` may return 443. This JSON is an **illustrative example of a run with forwarded-header processing**; if the configuration has not taken effect, `derivedUrl` remains internal HTTP.

This command deliberately demonstrates that a **direct request** can spoof forwarded headers when the app is configured to trust them. **Never allow Internet users to reach the origin directly with this header-trusting configuration.** Security resides at the proxy/network boundary, not in the header names.

### 6.7. Testing the redirect

```bash
curl -i \
  -H 'X-Forwarded-Proto: https' \
  -H 'X-Forwarded-Host: shop.example.test' \
  -H 'X-Forwarded-Port: 443' \
  http://localhost:8080/go
```

Expect a redirect status, typically `302 Found`, with `Location` pointing validly to `https://shop.example.test/done` or a **relative `Location`** that the browser resolves accurately per redirect settings. Absolute vs. relative `Location` behavior can depend on filters, containers, and redirect strategies; therefore verify the **destination URL the browser will actually visit** rather than asserting a single `Location` string across all versions.

**Do not run `curl -L` to follow redirects to the sample domain** unless you have a real matching domain running. `example.test` in the examples is a reserved documentation domain, not a live hostname to call over the Internet.

### 6.8. Testing cookies and sessions

Test creating the sample cookie:

```bash
curl -i -X POST http://localhost:8080/demo-cookie
```

Inspect a header equivalent to:

```http
Set-Cookie: visitor_choice=yes; Path=/; Max-Age=3600; Secure; HttpOnly; SameSite=Lax
```

Attributes may appear in a different order. A cookie is **host-only** when `Domain` is omitted. If the browser visits the public URL `https://shop.example.test`, the cookie is scoped to that public host; the internal backend `127.0.0.1` is never a cookie `Domain` visible to the browser. Calling `curl` directly on localhost only shows header structure; it does not prove the browser will send the cookie on a real HTTPS site.

Test the Servlet-container-managed session:

```bash
curl -i -X POST http://localhost:8080/session
```

In MVC/Tomcat without Spring Session, when a session is created, the response normally includes `Set-Cookie: JSESSIONID=...` with the configured attributes. Do not confuse these two cookies: `visitor_choice` is the demo cookie created via `ResponseCookie`; `JSESSIONID` is the cookie referencing the servlet container's `HttpSession`.

Never paste real session IDs into logs, chats, or commits. When testing publicly over an HTTPS proxy, check browser DevTools or `curl -i` to verify `Secure`, `HttpOnly`, `SameSite`, `Domain`, `Path`, and that the browser sends the cookie back on the right requests.

## 7. Building absolute URLs: request-derived or configured canonical?

### 7.1. When to derive URLs from the normalized request

Use this when building self/reference links for the **valid public host of the current request**, such as a multi-host app with safe host routing or generating resource links in an HTTP response:

```java
String url = ServletUriComponentsBuilder
        .fromContextPath(request)
        .path("/orders/42")
        .build()
        .toUriString();
```

This is a **snippet** inside a handler with `HttpServletRequest request`. It pulls scheme/host/port/context path from a request already processed by `ForwardedHeaderFilter` or native support. **Do not manually parse `X-Forwarded-Host`** inside a controller to assemble URLs: it is error-prone for ports/prefixes and opens the door to host spoofing.

You can use `ServletUriComponentsBuilder.fromCurrentContextPath()` inside an MVC request thread where `RequestContextHolder` holds the request. Do not use it in a background scheduler, Kafka listener, async email worker, or startup task when no current request exists.

### 7.2. When you must use a preconfigured public base URL

URLs used in password-reset emails, OAuth2 callbacks, webhooks, shared export links, or jobs without a request should rely on a **canonical public base URL** defined in configuration or a verified tenant registry:

```properties
app.public-base-url=https://shop.example.test
```

```java
String link = UriComponentsBuilder
        .fromUriString(publicBaseUrl)
        .path("/orders/42")
        .build()
        .toUriString();
```

This snippet assumes `publicBaseUrl` has been injected and validated; it is not a standalone program. Advantage: independent of client-supplied `Host`/`Forwarded` headers and usable without an HTTP request. Trade-off: requires managing hostnames per environment and possibly mapping tenant→public URL in multi-tenant systems.

**Never use a user-supplied variable directly as the hostname**, such as `?baseUrl=https://evil.example`. If multiple domains are permitted, maintain an official allowlist, verify tenant/permissions, scheme, host, port, and prefix, and never issue links to arbitrary domains.

### 7.3. Relative HTML links are often better than absolute links

Within same-site HTML, relative or root-relative links depend much less on scheme and host:

```html
<a href="/account">Account</a>
```

If the app is published under `/portal`, hardcoding `/account` will **omit the prefix**. With Thymeleaf/Spring MVC, use context-aware URL expressions:

```html
<a th:href="@{/account}">Account</a>
```

In an app where forwarded prefixes are handled properly, framework expressions/context can preserve the public path. Test when the reverse proxy rewrites prefixes; do not assume every version handles it automatically. For emails, external systems, or callbacks requiring full URLs, use absolute URLs from an authorized source.

## 8. Creating proper redirects behind a reverse proxy

### 8.1. Relative redirects in Spring MVC

A `@Controller` can return:

```java
@GetMapping("/signin-success")
public String signinSuccess() {
    return "redirect:/account";
}
```

This is a snippet, not a real login mechanism. `redirect:` is a **special view prefix**; the framework generates a redirect response. The leading `/` indicates an application-relative path per redirect view semantics, yet the final URL is still affected by context path, prefix, and the framework's redirect strategy.

When redirecting after a **POST**, Spring MVC commonly returns 302 in default setups; depending on architecture, HTTP 303 See Other can be used to emphasize switching to GET under PRG. Never use permanent 301/308 statuses for login flows or temporary routes: caches and browsers can retain them longer than intended.

### 8.2. Absolute redirects to external URLs

When redirecting to another page on an allowed domain, use an allowlist and a validated URI. Never do:

```java
@GetMapping("/next")
public String next(@RequestParam String url) {
    return "redirect:" + url; // OPEN REDIRECT
}
```

This is an **anti-pattern**: an attacker can craft a link that looks like your site yet redirects to a phishing site. Map route IDs to a fixed destination list, or use a strict URL parser and host allowlist if external redirects are required by business logic. Never check only `startsWith("https://shop.example.test")`, because `shop.example.test.evil.test` also starts with that string.

### 8.3. Login redirect loops and HTTPS termination

Common loop:

```text
Browser GET https://shop.example.test/login
 -> TLS proxy sends HTTP upstream
 -> Backend thinks request is http
 -> Security requires https and redirects
 -> Browser again GETs https://shop.example.test/login
 -> Loop
```

Fix the root cause: have the proxy emit the public protocol reliably, have Boot process forwarded headers, match HTTPS/security rules to actual conditions, and check that multiple layers are not forcing conflicting redirects. Never "fix" it by disabling HTTPS protection or accepting logins over plain HTTP.

### 8.4. `201 Created` `Location` and API URLs

When creating a resource in a REST API, a `201 Created` response may need a `Location` header with the public URL:

```java
URI location = UriComponentsBuilder
        .fromUriString(publicBaseUrl)
        .path("/api/orders/{id}")
        .buildAndExpand(orderId)
        .toUri();

return ResponseEntity.created(location).build();
```

This is a **snippet** assuming a validated `publicBaseUrl` and `orderId`, not standalone runnable code. If the public hostname must be derived per tenant from the request, read it only from a request that has undergone forwarded-header processing **and host verification**. Never put an unchecked raw `Host` into `Location`.

## 9. Public path prefixes and the doubled-prefix problem

Suppose the browser opens:

```text
https://portal.example.test/portal/orders/42
```

Yet NGINX forwards to Boot:

```text
http://127.0.0.1:8080/orders/42
```

The proxy has **stripped the `/portal` prefix** upstream. If Spring generates absolute links from internal paths without knowing the prefix, links will omit `/portal`. One infrastructure pattern uses `X-Forwarded-Prefix: /portal` to describe the public prefix.

### 9.1. Illustrative NGINX prefix rewrite

**Snippet replacing `location /` inside an NGINX vhost that already has TLS and safe forwarded headers:**

```nginx
location /portal/ {
    proxy_pass http://127.0.0.1:8080/;

    proxy_set_header Host $host;
    proxy_set_header Forwarded "";
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Host $host;
    proxy_set_header X-Forwarded-Port $server_port;
    proxy_set_header X-Forwarded-For $remote_addr;

    # Public prefix determined by the proxy itself, never trusting client input.
    proxy_set_header X-Forwarded-Prefix /portal;
}
```

The trailing `/` in `proxy_pass http://127.0.0.1:8080/;` matters because NGINX replaces the URI part matching the location; in this configuration, public `/portal/go` becomes upstream `/go`. Changing slashes without testing can send the wrong path upstream.

**Important:** whether `X-Forwarded-Prefix` is applied varies across Spring Framework versions and filter settings. Newer versions offer explicit opt-in for forwarded prefixes. Therefore, do not treat the snippet above as a guarantee that every Boot version automatically renders `/portal` without configuration. Test `/inspect` and `/go` through the deployed vhost itself.

### 9.2. Do not both keep a prefix and add a prefix

Two common approaches:

- The proxy keeps `/portal` intact and the app is configured with a matching context path/routes.
- The proxy strips `/portal`, the app runs at root, and it receives a trusted forwarded prefix to build public links.

Avoid combining `server.servlet.context-path=/portal` **with** uncoordinated proxy stripping/`X-Forwarded-Prefix=/portal`; that can produce `/portal/portal/...` or route mismatches. Decide on a single topology contract and test links, redirects, static assets, OAuth callbacks, and cookie `Path`.

### 9.3. How does a prefix affect cookie `Path`?

If the website is public under `/portal` yet the cookie has `Path=/internal`, the browser will **not send** the cookie on requests to `/portal/account`. Conversely, `Path=/` covers the entire site, which may be broader than necessary. For session cookies, specify the public scope:

```properties
server.servlet.session.cookie.path=/portal
```

This is for a prefixed deployment; do **not** use it simultaneously with `path=/` from the earlier root example. Spring Session may use its own `CookieSerializer` defaulting cookie path from the internal context path; configure the public path explicitly on whichever Spring Session mechanism you use.

Cookie `Path` is a browser sending filter, **not** an authorization mechanism or strict security isolation between apps on the same host.

## 10. Cookies matching the public address: what does the browser see?

### 10.1. Cookies do not store scheme/port the way URLs do

Cookies do not "point to an address" via a full URL. Browsers decide whether to store/send a cookie primarily from the **response host**, `Domain`, `Path`, `Secure`, `SameSite`, expiration, and browser policies. Port is not a cookie scoping attribute like a URL authority; cookies are not isolated solely by different ports on the same host under normal rules.

For example, the browser visits `https://shop.example.test/`, the proxy forwards to `http://127.0.0.1:8080`, and the app returns:

```http
Set-Cookie: JSESSIONID=opaque-value; Path=/; Secure; HttpOnly; SameSite=Lax
```

The browser sees the response coming from **shop.example.test**, not the upstream hostname in `Set-Cookie`. When **`Domain` is omitted**, cookies are normally host-only, scoped solely to the public host of the response. This is the preferred default when only one hostname needs the session.

### 10.2. Attributes you must understand

| Attribute | Meaning | Common error |
| --- | --- | --- |
| `Secure` | Browser sends cookie only over secure connections per cookie rules | TLS terminates at proxy, backend sees HTTP and omits `Secure` |
| `HttpOnly` | JavaScript cannot read cookie via `document.cookie` | Session ID exposed to scripts or unnecessary tools |
| `SameSite=Lax` | Restricts certain cross-site requests, usually fits same-site web apps | Cross-site logins/callbacks or iframes fail to behave as expected |
| `SameSite=Strict` | Stronger cross-site restriction | Users following links from external sites do not carry cookies into session flows |
| `SameSite=None` | Allows cross-site contexts per browser policy | Missing `Secure` causes the browser to reject or withhold the cookie |
| `Domain` | Expands cookie scope to permitted domain | Setting `Domain` to an internal host or overly broad domain |
| `Path` | Restricts URL paths where the browser sends the cookie | App is public at `/portal` yet cookie has `Path=/internal` |
| `Max-Age` / `Expires` | Cookie lifetime in the browser | Confusing it with server-side session expiration |
| `SameSite` and CORS | Two independent policy layers | Assuming enabling CORS makes browsers send session cookies automatically |

**`Secure` does not depend on whether the backend receives HTTP.** The browser uses HTTPS externally; for production session cookies, configure `server.servlet.session.cookie.secure=true` to guarantee `Secure` even when the origin receives internal HTTP.

### 10.3. Host-only or broader `Domain`?

For an app hosted only at `shop.example.test`, normally **omit `Domain`** so the cookie stays host-only. If sharing between `shop.example.test` and `account.example.test` is genuinely required, a broader domain may be needed, though it increases risk; evaluate subdomain trust and cookie name collisions.

Never set `Domain=127.0.0.1` or `Domain=internal-service.local` on a public response at `shop.example.test`; the browser will reject it as an invalid domain for that response.

### 10.4. Cookie prefixes

Browsers enforce extra constraints on cookie names starting with `__Secure-` or `__Host-`:

- `__Secure-...` must be set with `Secure` from an appropriate HTTPS context.
- `__Host-...` requires `Secure`, `Path=/`, and **no `Domain` attribute**.

Example for an application-specific cookie:

```http
Set-Cookie: __Host-visitor_choice=yes; Path=/; Secure; HttpOnly; SameSite=Lax
```

This is an illustrative cookie. Do not rename the container session cookie to `__Host-...` without configuring browsers, Spring Security, Spring Session, and related integrations consistently. If the app is public under `/portal` and needs `Path=/portal`, `__Host-` does not fit because it mandates `Path=/`.

## 11. Servlet session cookies and Spring Session cookies

### 11.1. Sessions managed by the embedded servlet container

In standard Spring Boot MVC/Servlet apps, the `JSESSIONID` cookie (unless renamed) can be configured with:

```properties
server.servlet.session.cookie.name=JSESSIONID
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax
server.servlet.session.cookie.path=/
```

`server.servlet.session.cookie.domain` can be set when shared-domain cookies are truly needed; most single-host apps should **leave it unset**. `server.servlet.session.timeout` controls server-side inactivity, separate from `cookie.max-age`. If the browser still holds an ID after the server session expires, the cookie will not revive the old session.

Spring Boot 3.3 supports `server.servlet.session.cookie.same-site` for auto-configured embedded servlet containers per the official docs. Always verify `Set-Cookie` in the actual runtime, especially when a security framework or proxy cookie rewriting is involved.

### 11.2. Sessions managed by Spring Session Redis/JDBC

When using Spring Session, the app can use `DefaultCookieSerializer` to emit a session cookie typically named `SESSION`. A `CookieSerializer` bean can configure:

```java
@Bean
CookieSerializer cookieSerializer() {
    DefaultCookieSerializer serializer = new DefaultCookieSerializer();
    serializer.setCookieName("SESSION");
    serializer.setCookiePath("/");
    serializer.setUseSecureCookie(true);
    serializer.setUseHttpOnlyCookie(true);
    serializer.setSameSite("Lax");
    return serializer;
}
```

This is a **snippet** only for a project already using Spring Session, requiring `@Bean`, `CookieSerializer`, and `DefaultCookieSerializer` imports. It does **not** belong in the minimal Java app from section 6. Never add it to "fix cookies" when the app uses only embedded Tomcat sessions: it adds confusion and dependencies.

Spring Session may read `request.isSecure()` to decide the default `Secure` flag if not set explicitly; requests must be interpreted properly behind a TLS proxy. Setting `setUseSecureCookie(true)` explicitly can be appropriate for HTTPS-only production. Check which serializer bean is the final source of `Set-Cookie` for domain and path—never assume Servlet container properties automatically modify every custom cookie.

### 11.3. Custom cookies created with `ResponseCookie`

`ResponseCookie` is used for application cookies (preferences, theme selection, etc.) and explicitly supports `Secure`/`HttpOnly`/`SameSite`/`Path`/`Domain`/`Max-Age`. It **does not** maintain a server session automatically and does not replace authentication tools. If a cookie holds a sensitive identifier, design integrity/confidentiality, expiry, rotation, and CSRF protections per security requirements—not just `HttpOnly`.

## 12. `SameSite`, CORS, and cross-site flows

The topic group name includes **CORS**, yet CORS does not directly solve public-URL issues. Distinguish:

- **Forwarded headers**: tell the server the public scheme/host/port/prefix so it generates accurate redirects and links.
- **Cookie `SameSite`**: tells the browser whether to send cookies based on top-level site and request context.
- **CORS**: tells the browser whether JavaScript at origin A may read responses from origin B.
- **CSRF protection**: reduces the risk of browsers sending unintended state-changing authenticated requests.
- **Spring Security `redirect_uri`**: callback parameters must match provider settings and the public URL; never derive arbitrarily from an untrusted `Host`.

### 12.1. CORS with credentials

If an SPA at `https://ui.example.test` calls an API at `https://api.example.test`, the two hostnames are **cross-origin** even if they belong to the same site. Browser `fetch` typically needs `credentials: "include"` to send cross-origin cookies, and the API must allow the explicit origin and set `Access-Control-Allow-Credentials: true` per policy.

Never combine `Access-Control-Allow-Origin: *` with credentials. CORS must list/check allowed origins; if a framework blindly echoes any client-sent `Origin`, that is unsafe. Beyond CORS, cookies still obey `Domain`/`Path`/`Secure`/`SameSite`. If truly cross-site (different registrable sites), `SameSite=None; Secure` may be required, subject to browser third-party cookie restrictions.

### 12.2. OAuth2/OIDC `redirect_uri` and HTTPS

Suppose an app logs in via an OAuth2 provider. When initiating login, Spring Security generates a public `redirect_uri`, for example:

```text
https://shop.example.test/login/oauth2/code/provider
```

If the app thinks the scheme is `http`, the generated URI can become `http://shop.example.test/login/oauth2/code/provider` or expose `:8080`. The provider rejects it because `redirect_uri` does not match the registered URI, or the browser gets redirected onto the wrong protocol.

Solution: configure proxy trust, public hostname, and prefix accurately, and register the **exact** callback URI in Spring Security and provider settings; in many cases you can configure an explicit redirect URI template. Never fix it by registering broad wildcard redirect URIs or accepting arbitrary `Host` headers for "flexibility."

### 12.3. CSRF and `SameSite`

`SameSite` helps constrain cookies in some cross-site contexts, yet it does not replace CSRF tokens across all flows. When using authentication cookies/sessions, POST/PUT/DELETE endpoints must have an appropriate CSRF strategy. In Spring Security, check the token repository, form/SPA integration, and only genuinely necessary callback exemptions. Never disable CSRF application-wide just because a reverse proxy broke cookies.

## 13. When there is a CDN, ingress, or multiple proxy hops

### 13.1. Who is the source of truth for the public origin?

The chain might be:

```text
Browser HTTPS :443
 -> CDN / WAF
 -> Load Balancer
 -> Kubernetes Ingress
 -> Spring Boot HTTP :8080
```

An internal hop may see HTTP even though the browser used HTTPS. If ingress writes `X-Forwarded-Proto: http` from its own internal `$scheme`, the backend gets the wrong info. Designate which hop is authoritative for the **viewer scheme**, and have downstream hops preserve that value only when received from an **authenticated, trusted hop**. Never trust headers pre-populated by the browser.

### 13.2. Table of information to verify at each hop

| Hop | Observed scheme | Observed host | Expected forwarded metadata |
| --- | --- | --- | --- |
| Browser → CDN | HTTPS | shop.example.test | CDN knows viewer scheme and public host |
| CDN → LB | May be HTTP or HTTPS | May be origin/LB host | CDN passes metadata per trusted config |
| LB → ingress | May be HTTP | Service/ingress hostname | Does not drop verified viewer scheme/host |
| Ingress → Boot | Usually internal HTTP | May be service host | `Forwarded`/`X-Forwarded-*` normalized consistently |
| Boot controller | Processed request | Public origin | `getScheme()`/builders reflect public address |

This is a **reasoning table**, not a guarantee of default behavior for any specific CDN/LB. AWS ALB, NGINX Ingress, Traefik, Envoy, Cloudflare, Spring Cloud Gateway, and CDNs differ in how they set/append headers, trust client IPs, and handle prefixes.

### 13.3. Avoid trusting two conflicting formats

If a request reaching Boot contains both:

```http
Forwarded: proto=http;host=wrong.example
X-Forwarded-Proto: https
X-Forwarded-Host: shop.example.test
```

You must know precisely which source your framework version prioritizes; never allow two conflicting header streams past the Internet edge. An easy-to-audit policy is having **the edge strip both client-sent header families and emit only the allowed format**, with downstream hops coordinating consistently. Adding manual beans/filters does not replace the edge's responsibility.

## 14. Step-by-step debugging of URLs, redirects, and cookies

### 14.1. Observe responses from the browser-facing endpoint

```bash
curl -i https://shop.example.test/go
```

Check `Location`:

- Does it use the HTTPS scheme?
- Does the host match the public hostname?
- Does it leak `localhost`, `10.x`, or `:8080`?
- Does it preserve the `/portal` prefix if required?
- Is there a redirect loop? Use `curl -v` and limit redirects rather than running `-L` unchecked.

### 14.2. Inspect cookies over HTTPS

```bash
curl -i -X POST https://shop.example.test/session
```

Inspect `Set-Cookie` and browser DevTools:

- Is `Secure` present on the session cookie?
- Is `HttpOnly` set properly?
- Is `SameSite` compatible with login/iframe/SPA flows?
- Is `Domain` accidentally set to an internal hostname or too broad?
- Is `Path` properly `/` or `/portal`?
- Does the browser show **blocked cookie** warnings, and on which request?
- Is the cookie sent back on requests to APIs/routes requiring the session?

Never paste real session IDs into public issues or chats. If sharing logs, redact cookie values and tokens.

### 14.3. Compare origin vs. public URL

In an **isolated local environment**, compare:

```bash
curl -sS http://localhost:8080/inspect
```

with the simulated forwarded-headers run in section 6.6 and a run through public NGINX. If the app still sees `scheme=http` behind the proxy, forwarded-header processing is not taking effect; if the app sees `scheme=https` yet the cookie lacks `Secure`, inspect cookie/container settings or the Spring Session serializer.

### 14.4. Diagnose redirect loops

If `https://.../login` keeps redirecting back to itself, capture an ordered sequence of statuses and `Location` headers without following infinitely:

```bash
curl -v --max-redirs 5 -L https://shop.example.test/login
```

Identify what emits each `Location` (proxy, Spring Security, controller), differences in scheme/host/path, and cookies. Never disable HTTPS redirects or remove auth just to stop a loop; locate the hop misunderstanding the public protocol or losing the session/CSRF state.

### 14.5. Test host header poisoning in an authorized test environment

From an authorized test environment, send a hostname outside the allowlist through the edge; expect it to be rejected before reaching Boot. If the app produces an absolute link containing the unknown hostname, your trust boundary or host validation is insufficient. Never test host injection against systems without authorization.

## 15. Common deployment mistakes

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `Location: http://...` despite browser HTTPS | Proxy TLS termination yet Boot does not process forwarded protocol | Set `X-Forwarded-Proto` and forward-headers strategy properly |
| `Location: https://host:8080/...` | Internal port leaked into URL | Forward public port or use configured canonical URL |
| Redirect jumps to `localhost` | Socket/upstream host used to build URL | Forward right public host, inspect request-derived builders |
| Redirect contains `/portal/portal` | Context path and forwarded prefix overlap | Pick one rewrite contract and test |
| Redirect missing `/portal` | Proxy strips prefix yet app unaware of public prefix | Configure prefix handling matching framework version |
| Session cookie missing `Secure` | Servlet sees internal HTTP, default cookie config unadjusted | Enforce `server.servlet.session.cookie.secure=true` for production HTTPS |
| Browser does not send cookie | Wrong `Domain`/`Path`/`SameSite`/`Secure`/expiry | Inspect browser DevTools and request `Cookie` header |
| Cookie sent to more subdomains than needed | `Domain` too broad | Prefer host-only cookies |
| Spring Session issues `SESSION` instead of `JSESSIONID` | Spring Session `CookieSerializer` | Inspect session store and serializer |
| OAuth2 provider reports `redirect_uri` mismatch | Callback URL has `http`, internal host, or wrong prefix | Fix public headers/canonical config and provider URI |
| Password-reset link contains rogue domain | Client-manipulated `Host`/forwarded header | Strip/overwrite at edge, canonical allowlist |
| Login keeps redirecting to login | Lost/blocked cookie or missing session | Inspect cookies + session store + security flow |
| `X-Forwarded-Proto=https` yet `getScheme()=http` | Strategy not enabled or filter bypassed | Verify Boot profile and hop headers |
| CORS enabled yet cookie still not sent | CORS does not override `SameSite`/cookie scope | Configure credentials, cookies, and CSRF together |
| CDN sees HTTPS yet ingress sees HTTP | Trust chain drops viewer protocol | Fix each hop from a trusted source |
| Proxy rewrites `proxy_redirect` yet app still emits bad links | Only some `Location` headers rewritten, not JSON/emails/cookies | Fix public URL at the root and test all channels |

## 16. Security and production operations

### 16.1. Block direct origin access

If external Internet clients can reach the origin directly, forwarded headers cannot be trusted. Network policies, security groups, private binds/interfaces, or firewalls must restrict connections to authorized proxies. Add a `Host` allowlist and default-vhost rejection at the edge. Never assume "nobody knows port 8080's URL": direct access still happens via scanners or poorly isolated internal networks.

### 16.2. Do not trust client addresses for authorization

`X-Forwarded-For` can be useful for audits/logs/rate limits **when** the trusted-proxy chain is properly defined. Never make account authorization decisions based solely on an IP from a raw header. If IP allowlisting is needed, use a reliable client-IP mechanism at the gateway/WAF and test for spoofing.

### 16.3. Sensitive absolute URLs must use an allowlist

Password-reset emails, email verification links, OAuth callbacks, and shared file links should use a configured canonical/public base URL or trusted tenant URL map. Validation should verify URI scheme, hostname, port, and path prefix, preventing user input from creating unintended redirect targets.

### 16.4. Local environments differ from production

Do not turn on `server.forward-headers-strategy=framework` on a local port and assume any `X-Forwarded-Host` from Internet clients is valid. In dev, test header spoofing to understand the risk. In production, protect the origin with a proxy trust boundary, test real HTTPS and browser cookie handling; having `Secure` prevent cookies from working over plain HTTP on a public hostname is the intended security behavior.

### 16.5. Proxy header forwarding is security-relevant input

Forwarded protocol/host determines redirect targets, callback URLs, security checks, cookie behavior, and sometimes CSRF origin comparisons. Proxy config changes must ship with regression tests. Never push an ingress change without checking Spring Security, HTML links, REST `Location` headers, session cookies, and CDN cache rules together.

### 16.6. Cookie names and sharing across apps

If multiple apps on the same host share `Path=/` and the same `JSESSIONID` name, they can overwrite or collide with each other's cookies in the browser. Choose appropriate names/paths/scopes; if sharing login across apps is intended, design the session store, domain, authentication, and CSRF properly rather than merely reusing a cookie name. Cookie domain/path alone do not provide strict security isolation; clear security architecture is required.

## 17. Pre-deployment test suite

| Case | Input | Pass criteria |
| --- | --- | --- |
| Local without proxy | GET `/inspect` on localhost | `scheme=http`, local internal links |
| Behind HTTPS proxy | GET `/inspect` via public host | `scheme=https`, public host/port |
| Normal redirect | GET `/go` through proxy | `Location` resolves in browser to public `/done` |
| Absolute links | GET `/inspect` | Both request-derived and canonical match public host |
| HTTPS termination | POST `/session` | `Secure` cookie present if policy requires |
| Custom cookie | POST `/demo-cookie` | `Path=/`, `Secure`, `HttpOnly`, `SameSite=Lax` |
| No cookie `Domain` | Browser request on same host | Host-only, no internal host leaked |
| Prefix rewrite | GET `/portal/inspect` through proxy | Links/redirects keep `/portal` exactly once |
| OAuth callback | Login via test provider | `redirect_uri` matches registered URI |
| Spoofed `Host` header | Send non-allowlisted hostname at edge | Request rejected, no malicious links generated |
| Client-forged `Forwarded` | Client sends crafted `X-Forwarded-*` to edge | Edge drops/overwrites, backend ignores rogue values |
| CORS + cookies | Browser on allowed separate origin | Credentials/Origin/`SameSite`/CSRF per policy |
| Public HTTP | Visit `http://...` | Redirects to HTTPS per strategy, no loop |
| Per environment | Distinct dev/staging/prod public base URLs | No staging links emitted in prod emails |

A single passing `curl -H X-Forwarded-Proto: https` test is **not enough** to validate production: it proves the framework can read the header, not that the proxy trust boundary is secure.

## 18. Review questions

**1.** Why can Spring Boot generate `http://...:8080` in `Location` even though the browser is on HTTPS?  
**Answer:** The backend may see only the internal HTTP hop to port 8080; forwarded protocol/host/port were not processed or were overwritten incorrectly.

**2.** Does `server.forward-headers-strategy=framework` make every `X-Forwarded-Host` header trustworthy?  
**Answer:** No. A trusted edge proxy must strip client-supplied headers and block direct access to the origin. The framework cannot tell who created the header.

**3.** Can you build email links using `ServletUriComponentsBuilder.fromCurrentRequest()` inside a scheduled job?  
**Answer:** No: a scheduled job has no bound HTTP request. Use a configured `public-base-url` or trusted tenant map.

**4.** The browser receives a cookie from `https://shop.example.test`, while the backend runs on `http://127.0.0.1:8080`. Should you set `Domain=127.0.0.1`?  
**Answer:** No; the browser sees the public host. Prefer omitting `Domain` (host-only) if only one hostname needs the cookie.

**5.** If the app is public under `/portal`, will a cookie with `Path=/internal` be sent to `/portal/orders`?  
**Answer:** No. `Path` must match the public request path per browser rules; typically set `Path=/portal` or `/` depending on desired scope.

**6.** Why might `SameSite=None` still fail to send cookies cross-origin?  
**Answer:** It still requires `Secure`, matching `Domain`/`Path`, a CORS credentials policy for fetch/XHR, CSRF handling, and browser third-party cookie rules.

**7.** Does CORS change `request.getScheme()` from `http` to `https`?  
**Answer:** No. That is the job of trusted forwarded headers/proxy config, separate from cross-origin response read permissions.

**8.** Why should you avoid `return "redirect:" + nextUrl` when `nextUrl` comes from the client?  
**Answer:** It creates an open redirect; use an allowlist or validated route mapping instead.

**9.** When Spring Session Redis emits `SESSION` via a custom `CookieSerializer`, which setting should you inspect to adjust the cookie?  
**Answer:** Inspect the Spring Session `CookieSerializer` itself and Boot integration; do not assume every `server.servlet.session.cookie.*` property modifies custom cookies directly.

**10.** If the app uses `server.servlet.context-path=/portal` while the proxy also sends `X-Forwarded-Prefix=/portal`, what error can happen?  
**Answer:** Depending on topology, it can double the prefix or cause routes not to match; pick one rewrite model and test URLs, redirects, and cookies.

## 19. Implementation checklist

- [ ] Documented public origin/base URLs and internal upstream routes for every environment.
- [ ] Edge proxy accepts only valid hostnames, rejects unknown hosts, and enforces public HTTPS.
- [ ] Proxy strips/overwrites **both** `Forwarded` and `X-Forwarded-*` from untrusted clients.
- [ ] Spring Boot `server.forward-headers-strategy` set per environment; origin is never exposed directly.
- [ ] `request.getScheme()`, `getServerName()`, `getServerPort()` behind the proxy reflect the public request.
- [ ] Redirect `Location` never contains `http`, internal host/port, or duplicated prefixes.
- [ ] Absolute links in HTML, JSON, emails, password resets, and callbacks use the right public base URL.
- [ ] Sensitive URLs are built from canonical config/allowlists, not raw request headers.
- [ ] If using a public path prefix, proxy rewrites/context path and forwarded prefixes are tested on the real version.
- [ ] Session cookies have `Secure`/`HttpOnly`/`SameSite`/`Domain`/`Path` matching the browser-facing hostname and path.
- [ ] Servlet container `JSESSIONID` is clearly distinguished from Spring Session `SESSION` and custom `CookieSerializer`.
- [ ] CORS credentials, `SameSite`, and CSRF are tested together across the full flow rather than in isolation.
- [ ] HTTPS redirects, OAuth2 login, logout, and callbacks are tested in a real browser with no redirect loops.
- [ ] Direct-origin access and spoofed `Host`/forwarded headers tested in an authorized environment.
- [ ] Multi-hop CDN→LB→ingress chains checked so no hop overwrites the original public protocol incorrectly.
- [ ] Monitor redirect loops, login failures, cookie rejections, callback mismatches, and broken links after rollout.

## References

1. [Spring Boot 3.3 — Running Behind a Front-end Proxy Server](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html)
2. [Spring Boot 3.3 — Servlet Web Applications and SameSite Cookies](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html)
3. [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/)
4. [Spring Framework — Forwarded Headers and ForwardedHeaderFilter](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html)
5. [Spring Framework 6.1 — ServletUriComponentsBuilder Javadoc](https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/web/servlet/support/ServletUriComponentsBuilder.html)
6. [Spring Session 3.3 — Custom Cookie](https://docs.spring.io/spring-session/reference/3.3/guides/java-custom-cookie.html)
7. [Spring Session — DefaultCookieSerializer API](https://docs.spring.io/spring-session/docs/3.3.x/api/org/springframework/session/web/http/DefaultCookieSerializer.html)
8. [RFC 7239 — Forwarded HTTP Extension](https://www.rfc-editor.org/rfc/rfc7239)
9. [RFC 6265 — HTTP State Management Mechanism](https://www.rfc-editor.org/rfc/rfc6265)
10. [MDN — Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Set-Cookie)

**Conclusion:** to generate accurate redirects, absolute links, and cookies in Spring Boot behind a reverse proxy, you must address three layers **together**: (1) a trusted proxy that preserves and normalizes **public scheme/host/port/prefix**, (2) Spring Boot/framework consuming that metadata properly or using a **canonical base URL** for sensitive links, and (3) cookies issued for the **HTTPS/domain/path seen by the browser**, not the JVM's internal address. Real testing through the edge is what proves the configuration works and is secure.