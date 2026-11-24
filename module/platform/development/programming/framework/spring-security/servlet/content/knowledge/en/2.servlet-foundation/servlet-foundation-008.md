# HTTPS, Proxies, and the Trust Boundary of Forwarded Headers in Spring Security Servlet

## 1. Goal and Context

In a Spring Boot application running the **Servlet stack** (Spring MVC and a Servlet container like Tomcat), browser requests often do not reach the application directly. In production environments, they may pass through a CDN, load balancer, API gateway, ingress controller, or reverse proxy. These components can terminate the TLS connection and open a new connection to the backend.

This lesson focuses on three closely linked questions:

1. **Over which connection hop is HTTPS enforced?** When a proxy receives HTTPS but forwards HTTP to the backend, does the application know the client's original request was HTTPS?
2. **What information does Spring Security use to make redirect and protection decisions?** Why can wrong `scheme`, `host`, or `port` values cause redirect loops, broken URLs, or missing HSTS headers?
3. **Who is allowed to assert forwarded headers?** Why must you never immediately trust `Forwarded`, `X-Forwarded-Proto`, `X-Forwarded-Host`, or `X-Forwarded-For` sent by an HTTP client?

After this lesson, you should be able to distinguish an actual TLS connection from *forwarded* protocol metadata; understand how to configure Spring Boot/Spring Security on Servlet behind a trusted reverse proxy; and diagnose common deployment issues without turning self-declared client headers into trusted evidence.

## 2. HTTPS and Reverse Proxies: Two Connections, Two Views

A common architecture:

```text
Browser
   |  HTTPS/TLS; public URL: https://app.example.test
   v
[Reverse proxy / Load balancer]
   |  Internal HTTP, e.g. http://127.0.0.1:8080
   |  + proxy-controlled metadata:
   |    X-Forwarded-Proto: https
   |    X-Forwarded-Host: app.example.test
   |    X-Forwarded-Port: 443
   v
[Servlet container] -> [Spring Security filters]
                              |
                         DispatcherServlet
                              |
                         Controller/Service
```

**TLS termination** means the proxy performs the TLS handshake and decrypts traffic from the client connection at the proxy. The subsequent connection from the proxy to the backend is a **separate connection**, which may use HTTP or HTTPS. Therefore:

- **Client → proxy over HTTPS** does not automatically mean **proxy → backend is also encrypted**. If the backend sits on an untrusted network, TLS is needed on that hop too; in some architectures mutual authentication (mTLS) is also required.
- If the backend directly receives internal HTTP, the Servlet container may see `request.getScheme() == "http"`, `request.isSecure() == false`, and internal port `8080`. It does not yet know that the Internet client used HTTPS.
- The proxy can supply metadata about the external request; the backend should only use that metadata when it arrives through a **verified and controlled proxy chain**.
- A proxy claiming "the original request was HTTPS" does not replace enforcing actual TLS at the edge. Merely adding `X-Forwarded-Proto: https` on a public HTTP connection does not make that connection secure.

In environments without a proxy, the Servlet container observes TLS directly and needs no forwarded headers. Do not enable forwarded-header processing just because the application uses Spring Security.

## 3. What Do Forwarded Headers Contain?

The proxy needs to reconstruct the request as seen by the client. Two header families are common:

| Header | Common meaning | What to watch out for |
| --- | --- | --- |
| `Forwarded` (RFC 7239 standard) | Carries parameters such as `for`, `proto`, `host`, and optionally `by`; can represent multiple hops | A client can send this header too; multiple elements must be parsed along a trusted proxy chain |
| `X-Forwarded-Proto` | Client-side protocol, usually `https` or `http` | A value of `https` does not by itself prove TLS |
| `X-Forwarded-Host` | Public host accessed by the client | A spoofed host can corrupt redirects and absolute URLs |
| `X-Forwarded-Port` | Public port, commonly `443` | Easily wrong when the edge uses another port or metadata conflicts between proxies |
| `X-Forwarded-For` | List of IP addresses across hops | Leading entries may be client-injected; never blindly take the first element |
| `X-Forwarded-Prefix` | Path prefix exposed publicly by a gateway and stripped before proxying | A wrong prefix can break links, redirects, or callback URLs |

Example *solely for understanding format*, not as trusted evidence:

```http
Forwarded: for=192.0.2.60;proto=https;host=app.example.test
X-Forwarded-Proto: https
X-Forwarded-Host: app.example.test
X-Forwarded-Port: 443
X-Forwarded-For: 192.0.2.60
```

`192.0.2.60` belongs to the documentation IP range. In practice, proxies may append or overwrite these headers; multiple proxies in series can produce a multi-address list. Never write rules like "take the leftmost IP in X-Forwarded-For" and use it as identity, admin privilege, or a security condition. The originating IP is network information whose trustworthiness depends on **which proxy observed and recorded it**.

**Distinguish two categories of data:** `X-Forwarded-Proto`/`Host`/`Port` describe the URL and protocol the client *purportedly* used; `X-Forwarded-For` describes the network source chain. They do not authenticate a user, do not replace `Authentication`/`SecurityContext`, and do not grant resource access.

## 4. Where Does the Trust Boundary Lie?

Suppose the backend trusts `X-Forwarded-Proto: https` and `X-Forwarded-Host: app.example.test`. If a client can reach the backend directly or send those headers through a proxy that forwards client values verbatim, anyone can **self-assert** that their request used HTTPS and carries any desired host.

The proper trust model:

```text
UNTRUSTED ZONE                         CONTROLLED ZONE
Client HTTP request
  | (may spoof any X-Forwarded-*)
  v
[Public Ingress/Proxy]
  1. Verify actual HTTP/TLS at the entry point
  2. Strip or discard client-supplied metadata
  3. Generate canonical metadata from proxy observations
  4. Forward only to authorized backends
  |
  v
[Backend Servlet] -> processes normalized forwarded headers
                   -> Spring Security uses accurate request metadata
```

A *trusted proxy* is not just an IP address on a diagram. For the backend to genuinely trust that information, all of these conditions must hold simultaneously:

1. **No bypass path exists:** The backend only accepts traffic from trusted proxies (loopback, network policy, firewall, or controlled private network); port 8080 is not exposed directly to the Internet.
2. **The proxy does not pass through raw client claims:** At the trust edge, the proxy must strip/overwrite `Forwarded` and relevant `X-Forwarded-*` headers, then generate metadata from the connection it actually sees. If a CDN/load balancer sits in front, each hop needs its own explicit contract and verification rule.
3. **Public hosts are constrained:** The gateway serves only valid domains/hosts; never arbitrarily use `Host` or `X-Forwarded-Host` to build callbacks, password-reset links, or redirects.
4. **No conflicting competing headers:** If both standard `Forwarded` and `X-Forwarded-*` appear together, define clearly which is authoritative; ideally the proxy emits only one normalized, consistent set of metadata.
5. **The proxy → backend channel matches the risk level:** Internal HTTP is acceptable only when the network boundary is truly controlled; across untrusted hosts/clusters, encrypt and authenticate the channel.
6. **Logs capture both perspectives:** You should be able to correlate the URL/scheme/host understood by the app with what ingress observed, without logging raw tokens, passwords, or sensitive cookies.

If any condition is missing, enabling "trust forwarded headers" in the framework allows request metadata to be spoofed. **This choice is a trust-architecture decision**, not a quick trick to fix redirects.

## 5. How Do Servlet and Spring Security Use That Information?

On Servlet, APIs that commonly affect how the app handles URLs and security include:

```java
request.getScheme();       // "http" or "https" for the current request
request.isSecure();        // Is it considered a secure connection?
request.getServerName();   // Host name seen by the application
request.getServerPort();   // Port seen by the application
request.getRequestURL();   // Absolute URL provided by the Servlet request
```

Without forwarded-header processing, these values can reflect the **internal connection**. With a forwarded-headers processor and a trusted proxy, the request can be wrapped/normalized so those APIs reflect the **public URL**.

For Spring Security, this directly affects:

- **HTTPS enforcement:** `requiresChannel(...requiresSecure())` checks whether the request is considered secure. If the backend sees only internal HTTP even though the client used HTTPS, the application can enter a redirect loop.
- **Redirects after login, logout, or auth failure:** When the framework builds absolute URLs or host/scheme-based URLs, wrong metadata can send users to port 8080, an internal hostname, or an unintended host.
- **OAuth2/OIDC callbacks in apps using those features:** A `redirect_uri` with the wrong scheme/host/port may fail to match the value registered with the identity provider. This is one consequence of a wrong public URL; this lesson does not go deep into OAuth2/OIDC protocols.
- **HTTP Strict Transport Security (HSTS):** Spring Security's default HSTS header is added only on requests recognized as HTTPS. If the app thinks a request is HTTP after TLS termination, it may omit HSTS as expected; alternatively, the proxy can manage HSTS at the edge.
- **Login session cookies:** The `Secure` attribute on session cookies must align with public HTTPS. Some cookie policies depend on the request/Servlet container, so define production config explicitly and inspect the actual `Set-Cookie` header.
- **Diagnostics and auditing:** Recorded scheme/host/IP can be wrong or spoofed if the trust boundary is weak. Never treat forwarded headers as an authenticated principal.

**Distinguish enabling HTTPS from recognizing HTTPS:** `requiresSecure()` can require a secure channel, but it does not configure certificates, TLS listeners, firewalls, or how proxies handle headers. TLS termination at ingress and forwarded-header interpretation in the app must align.

### Observable failures

| Symptom | Possible cause | What to inspect |
| --- | --- | --- |
| Browser loops 302/301 between URLs | Edge is HTTPS but backend always sees `http`; app enforces HTTPS | `getScheme()`, `isSecure()`, `X-Forwarded-Proto`, filter order, redirect source |
| Redirects to `http://localhost:8080` or internal host | App builds URLs from internal upstream address | Host, proto, port, proxy's public URL config |
| Login callback rejected | `redirect_uri` differs from registered scheme/host/port/prefix | Actual generated callback URL, path rewrites, and trusted forwarded headers |
| Session cookie missing `Secure` | Cookie policy or request secure detection is wrong | `Set-Cookie` on HTTPS responses and session cookie config |
| HSTS does not appear | Spring Security sees HTTP only; another config overwrites headers | Edge HTTPS response, app/proxy HSTS policy |
| Wrong IP in audit/rate limiting | Using proxy's `remoteAddr` or trusting client-supplied IP list | Trusted hops chain and client IP extraction at ingress |
| Links/redirects point to foreign host | Host or forwarded host is unconstrained | Host allowlist and proxy header stripping/overwriting |

## 6. Configuring Spring Boot Servlet Behind a Trusted Reverse Proxy

Spring Boot provides the `server.forward-headers-strategy` property:

| Value | Meaning | When to consider |
| --- | --- | --- |
| `none` | Do not actively process forwarded headers via this strategy | App is not behind a proxy, or there is no trusted forwarded source |
| `native` | Delegate to the Servlet container's native support, such as Tomcat's mechanism | Infrastructure has clear contracts for remote IP and trusted proxies and wants container handling |
| `framework` | Use framework support (on Servlet, typically `ForwardedHeaderFilter`) to recognize forwarded metadata | Spring MVC sits behind a controlled proxy and needs request URLs to reflect the frontend |

In a Spring Boot 3.x/Java 17+ app, sample production configuration:

```yaml
# src/main/resources/application-prod.yml
server:
  forward-headers-strategy: framework
  servlet:
    session:
      cookie:
        secure: true
```

`server.servlet.session.cookie.secure: true` matters for apps using HTTP sessions; it ensures session cookies carry the `Secure` flag in this deployment. `HttpOnly`, `SameSite`, domain/path, and timeout require policies suited to the real application. Never treat `SameSite` as a complete replacement for CSRF protection.

With `framework`, Spring Boot can auto-register `ForwardedHeaderFilter` on Servlet. Do not manually register a duplicate filter doing the same thing if Boot already handles it; do not enable both a container-level rewrite layer and another rewrite layer without understanding their order. With `native`, how trusted proxy addresses are matched and verified depends on the container and operational config; do not assume it behaves identically to `framework` in every detail.

**Important warning:** Setting `framework` or `native` only controls how headers are *interpreted*. It cannot independently verify that headers were written by a trusted proxy. Blocking direct backend access and normalizing headers at ingress remain mandatory.

### Proxy boundary example: a single Nginx ingress

The following is a **fragment** for a `location /` inside a valid HTTPS Nginx virtual host, not a complete TLS config. Assume Nginx is the sole public ingress; only Nginx can reach the backend at `127.0.0.1:8080`, and the fixed public domain is `app.example.test`.

```nginx
location / {
    proxy_set_header Host app.example.test;

    # Drop client-supplied metadata; generate only the controlled X-Forwarded-* set.
    proxy_set_header Forwarded "";
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-Host app.example.test;
    proxy_set_header X-Forwarded-Port 443;
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header X-Forwarded-Prefix "";

    proxy_pass http://127.0.0.1:8080;
}
```

In this configuration, `$remote_addr` is the peer address **directly observed by Nginx**, which cannot by itself identify the end user if another CDN/load balancer sits in front. If your infrastructure has multiple hops, reconfigure trusted upstream and client IP policies at the edge; do not copy a single-hop snippet and claim you have the real user IP.

The HTTPS virtual host must have real certificates and TLS policies; any public HTTP virtual host should redirect users to HTTPS at ingress by design. A fixed host is used in the example to avoid trusting an unvalidated `Host` value. `.test` is an example domain; real testing requires your own environment's hostname, DNS, and certificate.

## 7. A Spring Boot 3.x / Java 17+ Example to Observe and Enforce HTTPS

Below is a small Servlet app to inspect how the backend **interprets** scheme/host/port. The project needs two basic Spring Boot dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
```

In a Spring Boot 3.x project with plugin/dependency management configured, create `src/main/java/example/proxy/ProxyTlsDemoApplication.java`:

```java
package example.proxy;

import jakarta.servlet.http.HttpServletRequest;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class ProxyTlsDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ProxyTlsDemoApplication.class, args);
    }

    @GetMapping("/transport")
    public Map<String, Object> transport(HttpServletRequest request) {
        return Map.of(
            "scheme", request.getScheme(),
            "secure", request.isSecure(),
            "host", request.getServerName(),
            "port", request.getServerPort()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/transport").permitAll()
                .anyRequest().denyAll()
            )
            .requiresChannel(channel -> channel
                .anyRequest().requiresSecure()
            )
            .build();
    }
}
```

Because `/transport` permits only HTTP GET with `permitAll()`, this endpoint lets you inspect metadata without logging in. `requiresSecure()` still requires the request to be recognized as HTTPS **before** entering the controller. `anyRequest().denyAll()` is merely a simple policy so the demo exposes no extra endpoints; real applications must design their own routes and permissions.

If run locally **over HTTP only**, `GET /transport` can return an HTTPS redirect and then fail locally if no TLS listener/proxy exists. That is expected behavior from `requiresSecure()`, not a Java bug. In an environment with a trusted HTTPS ingress, set `server.forward-headers-strategy: framework`, run the app behind the proxy, and call:

```bash
curl -i https://app.example.test/transport
```

When ingress is configured properly, the expected response is HTTP **200** with equivalent key/value pairs (JSON key ordering is not guaranteed):

```json
{
  "scheme": "https",
  "secure": true,
  "host": "app.example.test",
  "port": 443
}
```

This is the **expected behavioral outcome**, not stdout captured from a live server in this lesson. If you see `http`, `false`, `localhost`, or `8080` from a public HTTPS request, inspect the proxy/config chain and filters before changing controller logic. If the endpoint returns a redirect, check `Location` and which component issued it (edge or Spring Security).

### Why can you not just check `isSecure()`?

Once forwarded-header recognition is enabled, `request.isSecure()` can reflect **claims forwarded by a proxy** rather than the TLS state between backend and proxy. A `true` value in a controller has security meaning only if ingress policies and the network boundary have been verified. For the same reason, never implement public TLS enforcement by reading `X-Forwarded-Proto` directly in a controller and treating it as trustworthy.

## 8. `ForwardedHeaderFilter`, the Servlet Filter Chain, and Spring Security

On the Servlet stack, the overall order of interest is:

```text
Proxy sends request + normalized forwarded metadata
             |
Servlet container
             |
Forwarded headers processor (framework or container)
             |
DelegatingFilterProxy -> FilterChainProxy
                          -> SecurityFilterChain
                             (HTTPS redirect, authn, authz, headers, ...)
             |
DispatcherServlet -> Controller
```

This is a **functional diagram**, not the exact filter order for every application/version. When choosing `framework`, the forwarded-header processor must run early enough for filters handling redirects or secure-channel checks to see the normalized info.

Spring Framework's `ForwardedHeaderFilter` uses `Forwarded` and matching `X-Forwarded-*` headers to wrap request/response and adjust URL/redirect computation. It has a strip-only mode (`removeOnly`) when you do not want to honor forwarded info; using that mode must also align with Spring Boot configuration. Merely having the headers present does not make Spring Security enable a processing strategy automatically.

**Two separate security layers:**

- **Ingress/proxy:** verifies real transport protocol, manages certificates, validates hosts, normalizes metadata, and restricts entry to the backend.
- **Spring Security Servlet:** relies on the normalized request to enforce channel policies, authentication, authorization, CSRF protection, and response headers.

CORS does not determine whether a request is HTTPS; CSRF does not prove forwarded headers are trustworthy. `X-Forwarded-User` or gateway-injected headers are also **not** automatically an authenticated user: if identity headers are used, you need a dedicated gateway authentication design and trusted channel.

## 9. Testing a Deployment Before Going to Production

A meaningful test suite runs from the **network edge** into the **application**, not only controller unit tests.

| Case | Outcome to prove | Failure sign |
| --- | --- | --- |
| Call public URL over HTTP | Ingress redirects to HTTPS per policy; no sensitive content served over HTTP | Backend still receives public HTTP and runs sensitive logic |
| Call public URL over HTTPS | Valid TLS certificate; app sees `scheme=https`, `isSecure=true`, correct public host and port | Backend sees internal URL or hits a redirect loop |
| Call backend port directly from outside ingress | Connection blocked by network policy/firewall | Clients can directly send spoofed forwarded headers |
| Send spoofed forwarded headers to ingress | Proxy strips/overwrites them; app still receives canonical metadata for the observed host and TLS | Returned host or proto changes to client-supplied values |
| Access host not in allowlist | Ingress rejects or applies defined host policy | Redirects to self-declared host or generates absolute URLs to foreign domain |
| Log in with cookies/session over HTTPS | `Set-Cookie` carries `Secure` and policy-compliant cookie attributes | Session cookie lacks `Secure` or redirects to HTTP |
| Inspect HTTPS response on a route passing through Spring Security | HSTS appears if policy requires it and is managed by app or ingress | Missing HSTS because app misreads HTTP or header configs conflict |
| Run app behind CDN and multiple proxies | Operational IP derives from proper trusted hops | Trusting client-supplied IP in `X-Forwarded-For`, misapplying rate limits |

Manual checks can be run in a staging environment once DNS/TLS exist:

```bash
# Observe the redirect performed by ingress for an HTTP request.
curl -I http://app.example.test/transport

# Observe public URL, status, HSTS, and data seen by the controller.
curl -i https://app.example.test/transport

# Test whether ingress preserves spoofed metadata from the client.
curl -i -H 'Forwarded: proto=http;host=untrusted.example' \
  -H 'X-Forwarded-Proto: http' \
  -H 'X-Forwarded-Host: untrusted.example' \
  https://app.example.test/transport
```

With a properly configured proxy, the third request **must not alter** the host/scheme trusted by the application; `untrusted.example` is an example domain. For public HTTP, the specific 301/302/307/308 status depends on ingress, so check `Location` and actual policy rather than mandating a single status code.

Automated tests should cover at least: valid HTTPS requests; redirected HTTP requests; requests carrying spoofed host/proto; and backend bypass blocked at the infrastructure layer. `MockMvc` tests can prove how security policies handle `secure=true/false`, but they **cannot replace** testing real ingress, firewalls, certificates, and proxy chains.

## 10. Dangerous Misconceptions

### "Having `X-Forwarded-Proto: https` means the user used HTTPS"

**False.** Any HTTP client can fabricate that header. Only when a trusted ingress observes TLS, strips untrusted source headers, and regenerates metadata does the backend have grounds to use it.

### "Enabling `server.forward-headers-strategy: framework` is enough"

**Insufficient.** The framework does not block the backend port, install certificates, or prove hosts are allowed. Controlling network paths and header-overwriting mechanics is the core of the trust boundary.

### "Spring Security `requiresSecure()` encrypts the whole path"

**False.** It can require/redirect to HTTPS based on the request view. The proxy must handle real TLS on the public side; the proxy-to-backend leg must be secured by infrastructure-appropriate means.

### "The first IP in `X-Forwarded-For` is always the client IP"

**False.** The IP list depends on how proxies append/overwrite headers, and clients can inject a fake prefix. If IP is needed for rate limiting or auditing, determine the client IP at a component aware of trusted hops; never use IP as an identity substitute for authentication.

### "HSTS, HTTPS, and the Secure cookie flag are the same thing"

**False.** HTTPS encrypts the connection; HSTS instructs the browser to keep using HTTPS within policy scope; the `Secure` cookie attribute restricts when the browser sends the cookie. They complement one another yet must be configured and verified separately. HSTS only takes effect when the browser receives it over valid HTTPS; deploy `includeSubDomains`/`preload` carefully once all related domains are ready.

### "Using `Host` or `X-Forwarded-Host` to build absolute links is always safe"

**False.** Without host restrictions, attackers can trick the app into building links or redirects to their own domains. Sensitive URLs like password-reset links should rely on a trusted public origin configuration or an explicit host validation policy.

## 11. Reasoning Exercises

1. A client calls `https://shop.example.test/cart` over TLS at the load balancer, yet the backend receives HTTP on port 8080. Spring Security has `requiresSecure()` and the page keeps redirecting in a loop. Which Servlet values, Boot settings, and LB headers would you inspect? Why should you not immediately turn off `requiresSecure()`?
2. Ingress passes through the client-sent `X-Forwarded-Host` verbatim. The app constructs post-login redirects from that hostname. Describe the spoofable input, the affected output, and where the fix belongs.
3. The backend is exposed publicly on port 8080 with forwarded-header processing enabled, and an HTTP client sends `X-Forwarded-Proto: https`. What might `request.isSecure()` report, and why does that result not prove the request was encrypted?
4. There are two reverse proxies in series. Why is using the leftmost IP element of `X-Forwarded-For` to decide "internal network address exempt from authentication" dangerous? What design is better?
5. An app logs in via cookies behind an HTTPS ingress, yet the session cookie lacks `Secure`. Propose how to isolate whether the bug is in the cookie policy or scheme detection, then state the required test after fixing it.

**Key takeaway:** HTTPS must be enforced on the actual entry path; forwarded headers are merely metadata relayed by proxies. Spring Security Servlet can only make accurate channel/redirect/cookie/header decisions when the backend sees the public URL **and** that information is produced by a genuinely trusted proxy boundary.
