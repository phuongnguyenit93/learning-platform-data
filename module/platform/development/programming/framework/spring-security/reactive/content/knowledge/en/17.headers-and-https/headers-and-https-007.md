# Strict-Transport-Security and HTTPS Deployment Requirements in Spring Security Reactive

## 1. Lesson Objectives

When a Spring WebFlux application serves login pages, session cookies, REST APIs, or sensitive content, **TLS/HTTPS is a fundamental requirement to protect data in transit**. Yet simply setting up a redirect from `http://` to `https://` does not address the case where the initial HTTP connection is intercepted by an on-path attacker. **HTTP Strict Transport Security (HSTS)** instructs browsers that already know a website's policy to **proactively upgrade subsequent visits to HTTPS**, while preventing users from casually bypassing certificate errors for an HSTS-bound host.

This lesson covers:

1. Understanding the `Strict-Transport-Security` header, the `max-age`, `includeSubDomains`, and `preload` directives, and browser behavior.
2. Distinguishing **HSTS**, **TLS**, **HTTP → HTTPS redirects**, and the **preload list**.
3. Knowing Spring Security **reactive's** exact HSTS defaults, the `ServerHttpSecurity.headers(...).hsts(...)` API, and the "write only on HTTPS requests" rule.
4. Configuring HTTPS locally in Spring Boot WebFlux Java 17+ with a self-signed keystore, verifying the header with `curl`, and understanding requirements for public CA certificates in production.
5. Handling reverse proxies, TLS termination, `Forwarded`/`X-Forwarded-Proto`, proxy trust boundaries, and cases where the app fails to recognize the HTTPS scheme.
6. Planning gradual `max-age` increases, subdomain audits, preload considerations, and rollbacks without locking users out of the site.
7. Writing a test matrix and safe deployment checklist across multi-node/CDN/ingress infrastructures.

**Core principle:** HSTS is a **browser-remembered policy about a hostname**. HSTS **does not issue certificates, does not enable TLS on the server, does not replace the first-visit redirect, and does not protect every kind of HTTP client**.

## 2. Why Is an HTTPS Redirect Alone Not Enough?

Suppose a user types `example.com` or clicks an `http://example.com/login` link.

~~~text
First visit, before the browser knows HSTS for the host:

Browser --HTTP--> http://example.com/
         |                |
         |         301/308 redirect
         |                v
         +------------> HTTPS
                           |
                    Response includes:
                    Strict-Transport-Security
                           |
                           v
                   Browser remembers host

Subsequent visits, while HSTS is active:

User types http://example.com/login
                           |
                           v
           Browser auto-upgrades before sending request
                           |
                           v
                 Direct HTTPS to host
~~~

On the **first visit** to a domain whose HSTS policy is not yet known to the browser, the initial HTTP request can be altered by a network attacker before the HTTPS redirect occurs. Once the browser receives a **valid HTTPS response** carrying HSTS, it remembers the rule and proactively turns `http://` into `https://` on future visits. HSTS reduces **SSL stripping / protocol downgrade** risk and causes browsers to refuse HTTPS connections with invalid certificates for protected hosts.

Limitations:

- If the user has never seen HSTS and the domain is not on the preload list, the **first-visit problem** still exists.
- Browsers honor HSTS only from **HTTPS responses with trusted TLS certificates**; headers sent over HTTP have no security effect.
- HSTS does not fix an expired certificate, create a TLS listener, replace authentication/authorization, or cure XSS vulnerabilities.
- Browsers are what enforce HSTS. `curl` or custom HTTP clients may not store or obey the policy by default.
- Mixed-content links and resources (HTTP images/scripts, `ws://` WebSockets) still must be fixed and tested; HSTS cannot replace a comprehensive secure resource-loading policy.

## 3. Syntax and Meaning of Strict-Transport-Security

Three common forms:

~~~http
Strict-Transport-Security: max-age=300
Strict-Transport-Security: max-age=31536000; includeSubDomains
Strict-Transport-Security: max-age=63072000; includeSubDomains; preload
~~~

### 3.1. max-age

`max-age` is the **number of seconds** the user agent remembers the HSTS policy starting from the most recent valid header received.

| Value | Duration | When to consider |
| --- | --- | --- |
| `max-age=300` | 5 minutes | Initial canary/rollout step |
| `max-age=604800` | 7 days | Stability verification phase |
| `max-age=2592000` | 30 days | Observation prior to long-term commitment |
| `max-age=31536000` | 365 days | Long-term policy once HTTPS is ready |
| `max-age=63072000` | 730 days | A long-term setting commonly used when considering preload |
| `max-age=0` | Clears the HSTS policy **stored by this exact host** if received over valid HTTPS | Limited rollback; **does not** remove preload or parent host policy |

Every valid HTTPS response re-emitting HSTS **refreshes the expiration clock** from that response time, not just the first installation. If you stop sending the header today, browsers that already learned the policy keep it until `max-age` expires (or they receive a valid `max-age=0`).

### 3.2. includeSubDomains

~~~http
Strict-Transport-Security: max-age=31536000; includeSubDomains
~~~

This directive extends the policy from the current hostname down to **all subdomains beneath it**, including nested levels.

For instance, a response from `example.com` with `includeSubDomains` affects `www.example.com`, `api.example.com`, `legacy.example.com`, and `dev.internal.example.com` once the browser learns the parent host's policy. It **does not** propagate upward from `login.example.com` to `example.com`, nor does it affect sibling domains outside that host's scope.

**Major risk:** if any subdomain runs HTTP-only, or uses a self-signed/expired certificate, HSTS on the parent domain can lock browsers out of that subdomain. Inventory **all internal subdomains**, legacy systems, static assets, callbacks, SSO, APIs, staging, and infrequently used hostnames before enabling it on a parent domain.

### 3.3. preload

~~~http
Strict-Transport-Security: max-age=63072000; includeSubDomains; preload
~~~

`preload` is a **request signal to join the HSTS preload list**; it does **not** mean "enabling the header immediately preloads the domain into all browsers." The domain must also meet the criteria at [hstspreload.org](https://hstspreload.org/) and be accepted and shipped through browser releases.

Preload partially solves the **first-visit problem**, yet carries very long-lasting commitments: every subdomain, even internal ones, may be forced to HTTPS by browsers; removal from the preload list can take months and is not synchronized across all browsers. **Do not enable `preload(true)` by default just because examples show it.** The HSTS preload service itself notes careful consideration is needed because preload's incremental benefit over HSTS can be modest in browsers that already upgrade HTTP proactively.

### 3.4. Remembered per Hostname, Not Just per Port

HSTS policy binds to a **hostname/domain name**, not a single URL/path. Browsers do not learn separate HSTS policies for `/login` vs. `/api`. Once active, HSTS affects HTTP visits across that host, not solely the endpoint that initially emitted the header.

Never use IP literals, arbitrary dev names, or a shared multi-environment host as a "production preload" test. Locally, `localhost` and self-signed certificates behave differently from public domains; `curl -k` only proves the server sent the header, **not that a browser trusts the certificate and stored the policy**.

## 4. Conditions for HSTS to Take Effect

Distinguish **the header appearing in a response** from **the browser actually accepting HSTS**.

| Condition | What happens if missing? |
| --- | --- |
| Server or edge **serves real HTTPS** | HSTS cannot substitute for a TLS handshake |
| Valid certificate for exact hostname, complete chain, unexpired, signed by client-trusted CA | Browser may reject the connection; do not expect browsers to learn HSTS over untrusted TLS |
| Response delivered over HTTPS to the client, or app detects scheme properly behind trusted proxy | Spring Security writer may omit the header if it perceives the request as HTTP |
| Valid `Strict-Transport-Security` header syntax | Browser may ignore it |
| Browser has seen valid HSTS or domain is on preload list | First HTTP visit remains exposed to interception |
| All covered hostnames/subdomains are HTTPS-ready | `includeSubDomains` or preload can break access |
| DNS, port 443, load balancer, CDN, ingress, and certificate renewal work reliably | HSTS can turn HTTPS outages into hard or unbypassable blocks |
| No other CDN/proxy layer emits conflicting headers | Avoid ambiguous multiple policies on one response |

**Do not do the following:** emit `Strict-Transport-Security` on an HTTP endpoint assuming browsers will trust it; disable certificate validation on a client and claim HSTS protects it; force `includeSubDomains` on a root domain while legacy HTTP-only services still exist.

## 5. Default HSTS in Spring Security Reactive

### 5.1. Default Header

Spring Security WebFlux **enables HSTS by default** in its security response headers. Per the Javadoc of `StrictTransportSecurityServerHttpHeadersWriter` and `ServerHttpSecurity.HeaderSpec.HstsSpec`:

- Default `maxAge` is **1 year** (equivalent to `31536000` seconds).
- Default `includeSubdomains` is **true**.
- Default `preload` is **false**.
- The writer adds `Strict-Transport-Security` **only when the request is recognized as secure/HTTPS**.

Consequently, an application with working HTTPS using default headers can emit:

~~~http
Strict-Transport-Security: max-age=31536000; includeSubDomains
~~~

**Important:** a Spring Security setup that "never touched headers" may still be emitting a **one-year policy including subdomains**! Before taking a production hostname live on HTTPS, verify your effective policy and full domain scope. If not yet ready to bind all subdomains, **explicitly configure `includeSubdomains(false)` and a short `maxAge`** during rollout.

`preload=false` as the default is also crucial: do not confuse Spring Security's default with illustrative documentation examples that enable preload.

### 5.2. Exact API for WebFlux

In reactive apps, configure inside:

~~~java
.headers(headers -> headers
        .hsts(hsts -> hsts
                .maxAge(Duration.ofSeconds(300))
                .includeSubdomains(false)
                .preload(false)))
~~~

This is a **snippet inside the `ServerHttpSecurity` configuration method**, requiring `java.time.Duration`. Notice the method name is `includeSubdomains` (lowercase "d" in `Subdomains`), and `maxAge` takes a `java.time.Duration`.

Do not copy Servlet syntax:

~~~java
// Servlet-only API; DO NOT use with ServerHttpSecurity:
http.headers(headers -> headers
        .httpStrictTransportSecurity(hsts -> hsts
                .maxAgeInSeconds(31536000)
                .includeSubDomains(true)));
~~~

These two snippets are **for comparison**, not to be run together. `HttpSecurity`/`SecurityFilterChain` is for Servlet, whereas this lesson uses `ServerHttpSecurity`/`SecurityWebFilterChain`.

### 5.3. Do Not Disable All Headers

Some legacy configs contain:

~~~java
.headers(headers -> headers.disable())
~~~

This is an **anti-pattern if used just to "fix HSTS"**: it strips many other protective headers such as `X-Content-Type-Options`, clickjacking protection, and cache control. If you need to disable HSTS specifically in an edge-managed environment, scope the configuration narrowly:

~~~java
.headers(headers -> headers
        .hsts(hsts -> hsts.disable()))
~~~

This snippet is intended only for setups where **TLS/HSTS is already handled at a single upstream point** and verified; it is not a recommendation to turn off HSTS in production. Never let the CDN, load balancer, and app emit conflicting HSTS headers/lifetimes and leave it to browser chance.

### 5.4. HSTS Does Not Automatically Redirect HTTP

Emitting HSTS on HTTPS responses and redirecting HTTP→HTTPS are two separate responsibilities. Spring Security WebFlux offers:

~~~java
.redirectToHttps(Customizer.withDefaults())
~~~

This optional snippet acts on **HTTP requests that actually reach the security chain** and are recognized as HTTP by the framework. If the app **listens only for HTTPS on port 8443**, there is no HTTP listener for Spring to send redirects from when clients send HTTP. In production, redirects are typically placed at the CDN, ingress, gateway, or reverse proxy on port 80.

## 6. HTTPS Must Be Ready Before Increasing max-age

### 6.1. TLS Certificates

In production, ensure:

1. The certificate covers the exact **hostname** the browser uses (SAN), not merely an IP or another hostname.
2. Complete intermediate certificate chain, signed by a browser-trusted CA, and unexpired.
3. HTTPS availability is stable on public entry points (usually port 443), including CDNs and ingresses.
4. Automated certificate renewal, pre-expiry alerts, and verified secret updates across all nodes.
5. Modern TLS protocols/ciphers (TLS 1.2/1.3 per policy), never transmitting secrets over HTTP.
6. End-to-end checks for login, logout, cookies, APIs, OAuth2 callbacks, `wss://` WebSockets, static assets, mobile, and legacy clients.
7. Verification of **proxy-to-backend** links per trust boundaries: TLS at the edge does not make internal traffic automatically safe on an untrusted internal network.

If TLS breaks, users with HSTS cached **cannot click past certificate warnings** to reach the host. That is the anti-MITM benefit, as well as an operational risk you must prepare for.

### 6.2. Redirecting from HTTP

`http://app.example.com` should be handled at the edge with a **301/308 redirect to HTTPS** even when HSTS is enabled: first-time visitors, bots, and non-HSTS clients still require redirection. Redirects do not replace HSTS because the very first redirect response can still be intercepted on an untrusted HTTP network.

Example Nginx snippet **illustrating only the HTTP redirect listener**, omitting the full TLS listener, upstream, and certificate configuration:

~~~nginx
server {
    listen 80;
    server_name app.example.com;
    return 308 https://app.example.com$request_uri;
}
~~~

Use a fixed canonical hostname instead of trusting arbitrary `Host` headers in redirects to avoid open redirects/misrouting. A separate TLS server block must configure certificates, proxying, HSTS headers, and security policies. Never just paste this block into production assuming HTTPS is complete.

### 6.3. Cookies and Application URLs

HSTS alone is not enough. For login sessions:

- Authentication cookies must include `Secure`, `HttpOnly`, and appropriate `SameSite`.
- Controller-generated URLs, email links, OAuth2 callback/redirect URIs, OpenAPI server URLs, and frontend API base URLs must use HTTPS and the canonical host.
- Never load HTTP scripts on HTTPS pages; consider CSP and test for mixed content.
- GET endpoints must never mutate state; retain CSRF protection for cookie-based POST/PUT/DELETE.
- Avoid redirect loops caused by scheme mismatches between reverse proxy and backend.

## 7. Runnable Example: Spring Boot WebFlux HTTPS + Short-Lived HSTS

This exercise uses **Java 17+**, Maven, Spring Boot **4.1.2**, Spring Reactive Web, and Spring Security. The demo serves HTTPS directly on port 8443 using a self-signed keystore to verify **server HSTS header emission**. Because self-signed certificates are not publicly trusted by browsers, this example **does not test public Internet browser HSTS acceptance**.

### 7.1. Create the Project

Generate a project from [Spring Initializr](https://start.spring.io/): group `com.example`, artifact `reactive-hsts-demo`, Maven, Java 17+, dependencies `Spring Reactive Web` and `Spring Security`. Minimal `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>reactive-hsts-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
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
~~~

Let the Spring Boot BOM select compatible Spring Security and Reactor versions. Do not add `spring-boot-starter-web`, as that belongs to Servlet/MVC rather than WebFlux.

### 7.2. Generate a Local Keystore with keytool

Create `src/main/resources` if it does not exist. On a machine with JDK 17+, run inside the project directory:

~~~bash
mkdir -p src/main/resources

keytool -genkeypair \
  -alias local-https \
  -keyalg RSA -keysize 2048 \
  -storetype PKCS12 \
  -keystore src/main/resources/dev-keystore.p12 \
  -storepass changeit -keypass changeit \
  -validity 90 \
  -dname "CN=localhost, OU=Development, O=Example, L=Test, ST=Test, C=US" \
  -ext "SAN=dns:localhost,ip:127.0.0.1" \
  -noprompt
~~~

This command is for Bash/Linux/macOS. On Windows PowerShell, create the directory with `New-Item -ItemType Directory -Force src/main/resources`, then run `keytool` on **a single line**, removing line-continuation backslashes.

After running, `src/main/resources/dev-keystore.p12` holds a **local private key**. Never commit keystores/private keys or real passwords to Git; `changeit` is only for local examples. Self-signed certificates cannot replace public CA certificates in production.

### 7.3. application.properties

Create `src/main/resources/application.properties`:

~~~properties
server.port=8443
server.ssl.enabled=true
server.ssl.key-store=classpath:dev-keystore.p12
server.ssl.key-store-password=changeit
server.ssl.key-store-type=PKCS12
server.ssl.key-alias=local-https

demo.hsts.max-age-seconds=300
~~~

This enables **HTTPS directly on Boot's embedded Reactor Netty server** on port 8443. The demo **does not open a separate HTTP port 8080**, so nothing on port 8080 serves redirects if a client sends HTTP. Edge redirects or an HTTP connector require a **separate** configuration.

### 7.4. Full Java Source

Create `src/main/java/com/example/hstsdemo/ReactiveHstsDemoApplication.java`:

~~~java
package com.example.hstsdemo;

import java.time.Duration;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;
import org.springframework.http.MediaType;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class ReactiveHstsDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveHstsDemoApplication.class, args);
    }

    @Bean
    SecurityWebFilterChain security(
            ServerHttpSecurity http, Environment environment) {

        long maxAgeSeconds = environment.getProperty(
                "demo.hsts.max-age-seconds", Long.class, 300L);

        if (maxAgeSeconds < 0) {
            throw new IllegalArgumentException(
                    "demo.hsts.max-age-seconds must not be negative");
        }

        return http
                .authorizeExchange(routes -> routes
                        .anyExchange().permitAll())
                .httpBasic(basic -> basic.disable())
                .formLogin(form -> form.disable())
                .headers(headers -> headers
                        .hsts(hsts -> hsts
                                .maxAge(Duration.ofSeconds(maxAgeSeconds))
                                .includeSubdomains(false)
                                .preload(false)))
                .build();
    }

    @RestController
    static class Pages {

        @GetMapping(value = "/", produces = MediaType.TEXT_PLAIN_VALUE)
        Mono<String> index() {
            return Mono.just("HTTPS_DEMO_OK");
        }

        @GetMapping(value = "/health",
                produces = MediaType.APPLICATION_JSON_VALUE)
        Mono<Map<String, String>> health() {
            return Mono.just(Map.of("status", "UP"));
        }
    }
}
~~~

**Notes:**

- `SecurityWebFilterChain` and `ServerHttpSecurity` are WebFlux APIs, not Servlet `HttpSecurity`.
- The demo intentionally uses `permitAll()` to focus on HTTPS/HSTS. **Never apply this rule to APIs holding user data**; production must still configure authentication and authorization.
- `maxAge(Duration.ofSeconds(300))` creates a **5-minute** policy suitable for controlled testing.
- `includeSubdomains(false)` avoids binding unrelated subdomains while learning.
- `preload(false)` does not request preload list inclusion.
- When the server receives a valid HTTPS request, the Spring Security writer adds `Strict-Transport-Security` before committing the response.
- The application does not generate TLS certificates itself; Boot loads the PKCS#12 file generated by `keytool` earlier.
- `Mono<String>` and `Mono<Map<...>>` let controllers run on the reactive stack without `block()`.
- `GET /health` is a demo endpoint, **not Spring Boot Actuator**. In production, decide carefully which health endpoints are exposed, who can access them, and what data they return.

### 7.5. Running the Application

In the directory containing `pom.xml`:

~~~bash
./mvnw clean package
./mvnw spring-boot:run
~~~

Windows: `.\mvnw.cmd clean package` then `.\mvnw.cmd spring-boot:run`. If no Maven wrapper is present, use your installed `mvn`.

Access port **8443** over HTTPS. Because the local certificate is self-signed, standard `curl` will not trust it:

~~~bash
curl -i https://localhost:8443/
~~~

Typically this fails TLS verification with `SSL certificate problem: self-signed certificate` or similar—**that is not an HSTS bug**.

To **check only the locally emitted headers**, you may use `-k`:

~~~bash
curl -k -i https://localhost:8443/
curl -k -i https://localhost:8443/health
~~~

Expected output for `GET /`:

~~~http
HTTP/1.1 200 OK
Strict-Transport-Security: max-age=300
Content-Type: text/plain;charset=UTF-8

HTTPS_DEMO_OK
~~~

Header order and additional framework headers may differ; what matters is **status 200**, body `HTTPS_DEMO_OK`, and an HSTS header with `max-age=300` **without `includeSubDomains` or `preload`** in this demo. Some responses may include other cache or security headers.

**Safety note:** `curl -k` skips chain/certificate checks **only for local testing**. It **does not prove** browsers stored HSTS, and `-k` must never be used to verify production TLS. In production, use `curl -i https://app.example.com/` **without `-k`** to verify trusted certificates.

### 7.6. Testing an HTTP Request and Understanding the Limit

~~~bash
curl -i http://localhost:8443/
~~~

This speaks plaintext HTTP to a **TLS-only port**; it may fail the handshake or return an error response, and **you should not expect a 301/308 redirect**. This demo has no HTTP listener; HSTS is an **HTTPS response header**, not a feature that automatically opens port 80/8080.

To demonstrate redirects, add an HTTP ingress/edge or a separate HTTP connector; in production, let the load balancer/CDN/ingress handle port 80 and forward to 443. If the backend itself genuinely receives HTTP requests and you want Spring Security to redirect them, use `.redirectToHttps(Customizer.withDefaults())` on the relevant chain—enable it only after confirming accurate forwarded schemes to prevent loops.

### 7.7. Changing max-age via Configuration

Try editing `demo.hsts.max-age-seconds=604800`, restarting, and observing `max-age=604800` via `curl -k -i`. This checks **server emission** locally only; never emit long-lived HSTS on a shared domain used by others for testing.

When preparing for production, change `includeSubdomains(false)` to `true` **only after every subdomain supports HTTPS**. Do not enable preload in self-study examples.

## 8. TLS Termination at a Reverse Proxy / Load Balancer

In many architectures, browsers connect via **HTTPS → CDN/ingress/ALB**, and the proxy calls Spring WebFlux over **internal HTTP**:

~~~text
Browser
  | HTTPS TLS (valid public certificate)
  v
CDN / reverse proxy / ingress :443
  | TLS terminated
  | X-Forwarded-Proto: https (set by trusted proxy)
  v
Spring WebFlux service :8080 (internal HTTP, private network)
  |
  v
SecurityWebFilterChain / HSTS headers
~~~

If Spring WebFlux sees the incoming proxy request as **`http://`** and is not configured to process forwarded headers, `StrictTransportSecurityServerHttpHeadersWriter` may **omit HSTS** even though the browser talked to the edge over HTTPS. Conversely, if the server trusts **`X-Forwarded-Proto: https` forged by an arbitrary client**, redirects, generated URLs, and security decisions can break.

### 8.1. Forwarded Headers Require a Trust Boundary

Spring Boot supports:

~~~properties
server.forward-headers-strategy=framework
~~~

In WebFlux, this strategy uses Spring Framework's mechanism to process `Forwarded`/`X-Forwarded-*` (via `ForwardedHeaderTransformer`). Another option is `native` if the embedded server/platform supports it and is configured properly:

~~~properties
server.forward-headers-strategy=native
~~~

**These are separate options; never declare both lines side by side in a real configuration.**

Enable forwarded-header support only when:

1. The application sits **behind proxies you control/explicitly trust**.
2. The proxy **strips or overwrites** any client-supplied `Forwarded`/`X-Forwarded-*` headers and sets accurate scheme/host/port values.
3. The backend is unreachable directly from the Internet, or rejects/isolates non-proxy traffic.
4. End-to-end HTTPS tests through browser → proxy → backend confirm `https` scheme detection and accurate redirect URLs.
5. No HTTP↔HTTPS redirect loops or client-controlled host redirects occur.

**Never trust a request as HTTPS solely because `X-Forwarded-Proto` exists.** Clients can inject that header themselves; relying on it to bypass security logic without a proxy trust boundary is a configuration vulnerability.

### 8.2. Set HSTS in Spring or at the Edge?

Both approaches can work, provided you establish **one unified policy**.

| Where HSTS is set | Advantages | Watch out for |
| --- | --- | --- |
| **Spring Security WebFlux** | Policy lives alongside code/security chains; easy to test | App must detect HTTPS behind proxies; every public response must traverse the chain |
| **CDN / load balancer / ingress** | Controlled at public TLS boundary, covering CDN error/redirect pages | Configure accurately across all hostnames/routes; avoid duplicate headers from the app |
| **Both emitting** | Identical policies if intentionally coordinated | Risk of conflicting values/lifetimes, unclear browser handling; avoid doing casually |

In production, if the edge sets HSTS on HTTPS responses, you may explicitly disable **only the HSTS writer** in Spring to prevent duplicates while keeping all other security response headers. If Spring remains responsible for emitting HSTS, test 200s, HTTPS redirects, 4xx/5xx error responses, and CDN caching paths.

**Never attach an HSTS header to an HTTP response at the edge assuming browsers will honor it.** HSTS is trusted only when delivered over HTTPS.

### 8.3. Testing via Public Domain

Once you have a public domain, valid CA certificate, and active edge HTTPS:

~~~bash
curl -i https://app.example.com/
curl -I https://app.example.com/login
curl -I http://app.example.com/
~~~

These are **placeholder deployment addresses**, not active domains. Run only after substituting your real hostname.

Verify that:

- HTTPS connects cleanly **without `-k`**, with a certificate matching the hostname.
- The HTTPS response carries **one** expected HSTS policy at the public edge.
- HTTP returns 301/308 to a canonicalized `https://...` URL without redirect loops.
- No credentials or session cookies leak over HTTP; auth cookies carry `Secure`.
- For web logins, the login page and error responses do not unintentionally lose HSTS.
- If the proxy calls the backend over HTTP, the backend accepts traffic only from the proxy and forwarded headers are sanitized.

## 9. Phased HSTS Rollout

HSTS is not an instant "toggle on and revert anytime" switch: browsers cache policies long-term. Plan per **specific domain**, with clear owners for TLS infrastructure, subdomains, and proxies.

### 9.1. Recommended Steps

1. **Inventory:** list all hostnames/subdomains, including deep levels, internal services, legacy apps, staging, OAuth callbacks, CDNs, service workers, WebSockets, and mobile clients.
2. **HTTPS first:** deploy valid certificates, HTTP→HTTPS redirects, fix mixed content and app-generated URLs; monitor TLS errors.
3. **Check current defaults:** Spring Security may already be emitting `max-age=31536000; includeSubDomains`; never assume "unconfigured means off."
4. **Canary:** start on a controlled hostname/subdomain with `max-age=300`, `includeSubDomains=false`, `preload=false` until the whole domain is audited.
5. **Increase gradually:** once stable, consider `604800` (1 week), `2592000` (1 month), then `31536000` (1 year), monitoring at least through one full interval before advancing in critical change processes.
6. **Add subdomains when safe:** enable `includeSubDomains` only after proving every covered subdomain—including internal DNS names—serves valid HTTPS.
7. **Preload (only if truly needed):** evaluate separately with domain-owner approval under [hstspreload.org](https://hstspreload.org/) rules; do not treat it as mandatory for every web app.
8. **Monitor continuously:** certificate expiration, renewal failures, 4xx/5xx, redirect loops, TLS handshakes, external synthetic checks, and infrequently used subdomains.

Example roadmap table:

| Phase | Header | Scope | Gate to next phase |
| --- | --- | --- | --- |
| A – trial | `max-age=300` | Single controlled hostname | Valid HTTPS and proper 200/3xx/4xx |
| B – one week | `max-age=604800` | Same hostname | Zero TLS/redirect/cookie issues |
| C – one month | `max-age=2592000` | Same hostname or verified subdomains | Full observation window, no broken links |
| D – long-term | `max-age=31536000` | Only with stable TLS operations | Certificate rotation and disaster recovery tested |
| E – expanded | `...; includeSubDomains` | Entire audited domain | All subdomains serve HTTPS |
| F – optional preload | `...; includeSubDomains; preload` | Eligible domain | Formal sign-off on long-term impact |

**There is no universal roadmap for every organization.** If a root domain still hosts legacy HTTP subdomains, never promote the root domain with `includeSubDomains` just because the main hostname supports HTTPS.

### 9.2. Why Is Preload High-Risk?

To qualify for preload submission under current guidelines, a site requires:

- A valid certificate.
- HTTP→HTTPS redirects on the **same hostname** if listening for HTTP on port 80.
- Every subdomain serving HTTPS, including internal names under the domain.
- HTTPS responses on the base domain emitting HSTS with `max-age` **at least 31536000 seconds**, `includeSubDomains`, and `preload`.
- Additional HTTPS redirects also emitting HSTS where required.

Setting the header alone is not enough: preload requires submission/acceptance; changes roll out via browser updates, and removal from the preload list can take a very long time. Preload is **not an instant rollback button**.

## 10. Rollback and Incident Handling

### 10.1. What Does max-age=0 Do?

To clear an HSTS policy stored directly for one host:

~~~http
Strict-Transport-Security: max-age=0
~~~

The browser must receive this header over **valid HTTPS** from that exact host. An HTTP response containing `max-age=0` **cannot clear** the policy, because browsers ignore HSTS over HTTP.

If the host falls under an `includeSubDomains` policy from a **parent host**, clearing the child host's policy does not lift the parent's policy. If the domain is preloaded, emitting `max-age=0` does not immediately remove it from shipped browser preload lists either. And if TLS fails on the host and HSTS users cannot connect over HTTPS, you cannot "quickly push max-age=0 over HTTP" to rescue them.

### 10.2. Plan Recovery **Before** Extending HSTS Lifetime

- Always maintain recovery plans for certificates/secrets, DNS, port 443 listeners, and TLS termination.
- Keep administrative infrastructure access independent of HSTS-protected websites (never rely solely on an HTTP-only subdomain that could be locked out).
- Test CDN/ingress or certificate changes in staging first.
- Monitor non-browser clients, since they may not enforce HSTS like Chrome/Firefox.
- If you discover an HTTP-only subdomain before enabling a long policy, fix it before raising `max-age`.
- Once a long policy has been emitted, even after removing the header, browsers that stored it will keep upgrading HTTP until expiration.

### 10.3. HSTS Does Not Fix Every SSL/TLS Flaw

HSTS does not replace:

- Trusted CA certificates with accurate SANs and valid dates.
- Modern TLS cipher and protocol configurations.
- `Secure` cookies and policies preventing secret exposure over HTTP.
- HTTPS on all backend hops required by your threat model.
- CSP/mixed-content blocking, CSRF protection, and authentication/authorization.
- Certificate verification when a `WebClient` calls upstream services; never configure a trust-all SSL context just to make requests "work."

## 11. Common Troubleshooting Table

| Symptom | Likely cause | How to investigate |
| --- | --- | --- |
| HTTPS 200 but HSTS missing | Security headers disabled, different chain matched, proxy stripped header, or Spring sees HTTP | Check chain, edge response, forwarded scheme |
| HTTP response has HSTS yet browser stays on HTTP | Browsers ignore HSTS over HTTP | Serve and test over HTTPS |
| `curl -k` shows HSTS yet browser doesn't remember | Self-signed/untrusted cert; curl doesn't test browser HSTS | Use valid domain/cert for browser E2E |
| Header appears on 200 only, missing on 301/403/500 | Edge/other route generated response, header config doesn't cover it | Inspect redirect and error responses too |
| Redirect loop between HTTP and HTTPS | Proxy terminates TLS but backend lacks forwarded proto | Trust proxy, `ForwardedHeaderTransformer` / `native` |
| Missing HSTS only in prod | SSL terminates at proxy; app sees HTTP scheme | Configure trusted forwarded headers or set HSTS at edge |
| Site and subdomains locked out after enabling includeSubDomains | Subdomain lacks valid TLS/cert | Audit/deploy TLS first; rollback is limited |
| Typing http auto-switches to https even without server redirect | Browser cached HSTS or domain is preloaded | Check browser HSTS state and parent policy |
| Header removed yet browser still forces HTTPS | `max-age` not expired or preloaded | HSTS does not vanish immediately upon header removal |
| Sending max-age=0 over HTTP fails to recover | Browsers ignore HTTP HSTS headers | Valid HTTPS required; parent/preload policies may persist |
| API client still calls HTTP | Client lacks HSTS support/storage | Enforce HTTPS on server/edge and client URLs |
| One domain emits two headers with different ages | Both app and CDN configure HSTS | Establish a single header emitter |
| Browser blocks certificate error with no bypass option | HSTS enforced, invalid cert | Fix the real certificate; never disable TLS verification |
| Opening real domain via IP breaks HSTS expectations | HSTS binds to hostname; cert SAN/Host differs | Access via the canonical hostname |

### 11.1. Separating SSL Failures from Security Header Issues

If `curl https://...` fails the TLS handshake, **do not blame HSTS** before verifying DNS, port 443, the certificate chain, and TLS protocols. If HTTPS works yet the header is absent, inspect the Spring Security writer, reverse proxy, and which component actually produces the public response.

If a response is 401/403, that is authentication/authorization; HSTS must be tested **independently of HTTP status** and must never substitute for access control.

## 12. Testing and Acceptance Criteria

### 12.1. Local Smoke Test

Against the section 7 demo project:

~~~bash
# HSTS present in response; -k skips verification only for local self-signed cert
curl -k -i https://localhost:8443/

# Verify JSON endpoint also includes the header
curl -k -i https://localhost:8443/health

# No automatic HTTP redirect since only TLS listener 8443 is enabled
curl -i http://localhost:8443/
~~~

Expect the first two HTTPS responses to carry `Strict-Transport-Security: max-age=300`. The final command speaks the wrong protocol to a TLS port and must **not** be treated as an HSTS failure when the server has no HTTP listener.

### 12.2. Production Acceptance Tests

| Test group | Steps | Passing criteria |
| --- | --- | --- |
| TLS | `curl -i https://app.example.com/` without `-k` | Valid certificate connection |
| HSTS | Check HTTPS 200/3xx/4xx | Expected header present, no duplicates |
| Redirect | `curl -I http://app.example.com/` | Redirects to canonical HTTPS |
| First-visit | Fresh browser with empty HSTS state | Safe redirect occurs, first-visit risk understood |
| Cached policy | Browser with learned policy visits HTTP link | Browser upgrades before sending HTTP network traffic |
| includeSubDomains | Test actual subdomain inventory | Every subdomain has working TLS |
| Cert rotation | Roll/renew certificate in canary | Zero broken TLS |
| Proxy scheme | Backend behind trusted proxy | No redirect loops; HSTS emitted at public edge |
| Security headers | Check remaining headers | CSP/X-Frame-Options/nosniff preserved (not lost via disable all) |
| Cookie auth | Login, logout, callback | `Secure` cookies, HTTPS URLs, no plaintext leaks |
| CDN errors | Trigger controlled 301/404/503 | Consistent HSTS policy within managed scope |
| Rollback | Test in canary domain | Understand cached `max-age` and non-instant reversal cases |

Never use `curl -k` when signing off on production certificate validity. Browser tests must use an **isolated** profile/cookie/HSTS state; a profile that previously cached another policy can yield misleading results.

### 12.3. Testing with Java/WebTestClient

You can write unit tests for `StrictTransportSecurityServerHttpHeadersWriter` or WebFlux Security integration tests when requests carry the `https` scheme. With `MockServerWebExchange`, **simulate a secure request properly**; sending an `http://` mock request expecting HSTS produces a false negative.

Hypothetical test snippet (**not a complete test class**):

~~~java
MockServerWebExchange exchange = MockServerWebExchange.from(
        MockServerHttpRequest.get("https://app.example.com/"));

StrictTransportSecurityServerHttpHeadersWriter writer =
        new StrictTransportSecurityServerHttpHeadersWriter();
writer.setMaxAge(Duration.ofSeconds(300));
writer.setIncludeSubDomains(false);
writer.setPreload(false);

StepVerifier.create(writer.writeHttpHeaders(exchange))
        .verifyComplete();

String header = exchange.getResponse().getHeaders()
        .getFirst("Strict-Transport-Security");
assertEquals("max-age=300", header);
~~~

Requires Spring Test, Reactor Test, JUnit, and matching imports. This is only a **contract-illustrating snippet** and does not prove the HTTP server itself serves TLS: real TLS testing still requires running a server with certificates or testing through the public edge. If a mocked HTTPS request lacks SSL metadata required by the writer in your version, use an integration test against a real HTTPS listener rather than faking security via header spoofing.

## 13. Production Deployment Checklist

1. Identified all public hostnames, internal subdomains, root domain, and related domains to protect.
2. Real TLS/HTTPS operates reliably with trusted CA certificates, accurate SANs, full chain, and auto-renewal.
3. HTTP→HTTPS redirects operate at the appropriate entry point, covering first-time visitors.
4. Verified whether Spring Security's default one-year/`includeSubDomains` HSTS is active rather than assuming.
5. Increase `max-age` only after testing/monitoring over a representative window.
6. Enable `includeSubDomains` only when all subdomains, including internal ones, operate over HTTPS.
7. Enable `preload` only after security review and owner sign-off, understanding preload addition/removal timelines.
8. CDN, ingress, and app agree on a single HSTS emitter with no duplicate or conflicting headers.
9. Backends behind TLS proxies recognize the request scheme accurately and trust `X-Forwarded-*` only from trusted proxies.
10. Browser/client-generated URLs, OAuth2 redirect URIs, `Secure` cookies, static assets, and WebSockets all use HTTPS.
11. Never use `curl -k` to claim production TLS testing passed.
12. HSTS does not replace CSRF, authentication, authorization, CSP, or TLS certificate management.
13. Alerts exist for approaching certificate expiration, HTTPS health checks, synthetic probes, and recovery plans.
14. Never call `headers.disable()` just to alter HSTS policy; preserve all other headers.
15. Tested with both fresh browser profiles and profiles with cached HSTS across hostnames and subdomains.
16. Rollback runbook accounts for `max-age=0` working only over HTTPS and not immediately overriding preload/parent policies.

## 14. Self-Check Questions

**Q1.** Does Spring Security reactive add `Strict-Transport-Security` on HTTP requests by default?

**Answer:** No. The HSTS writer emits the header only when the request is recognized as HTTPS/secure. If public clients use HTTPS while a proxied backend sees HTTP, configure trusted forwarded-scheme handling or emit the header at the edge.

**Q2.** What does `Strict-Transport-Security: max-age=31536000; includeSubDomains` mean?

**Answer:** The browser remembers for roughly one year from the most recent valid response that the hostname and all subdomains in scope must be accessed via HTTPS.

**Q3.** Does simply redirecting HTTP to HTTPS completely prevent SSL stripping?

**Answer:** No. The very first HTTP request from a user who has not yet learned HSTS can still be intercepted. HSTS protects subsequent visits after the browser learns the policy, while preloading can address first visits once listed.

**Q4.** Why doesn't `curl -k` prove browsers are protected by HSTS?

**Answer:** `-k` skips certificate validation; browsers only trust HSTS from trusted HTTPS. `curl` also does not persist HSTS like browsers do.

**Q5.** Should `preload(true)` be turned on immediately once the app has a certificate?

**Answer:** No. Preload requires every subdomain to support HTTPS, a long `max-age`, specific criteria, and long lead times for addition/removal. Evaluate full-domain policy before deciding.

**Q6.** Why does an API behind a reverse proxy fail to emit HSTS even when users connect over HTTPS?

**Answer:** TLS terminates at the proxy, so the backend may see an HTTP request. Configure trusted proxy forwarded headers in WebFlux, or emit HSTS at the edge.

**Q7.** Can you send `max-age=0` over HTTP to rescue a site with a broken certificate?

**Answer:** No. Browsers ignore HSTS headers over HTTP; policy removal is accepted only over valid HTTPS. Parent-host policies and preload entries can also remain in force.

**Q8.** Why did the demo use `includeSubdomains(false)` and `max-age=300`?

**Answer:** It is a cautious setup for testing HSTS emission without locking out subdomains and keeping cache lifetime short. Production should increase the lifetime only after HTTPS is verified.

## 15. Official Documentation and References

- [Spring Security — HTTP, Redirect to HTTPS, and HSTS in WebFlux](https://docs.spring.io/spring-security/reference/reactive/exploits/http.html)
- [Spring Security — Security HTTP Response Headers (Reactive)](https://docs.spring.io/spring-security/reference/reactive/exploits/headers.html)
- [Javadoc — ServerHttpSecurity.HeaderSpec.HstsSpec](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.HeaderSpec.HstsSpec.html)
- [Javadoc — StrictTransportSecurityServerHttpHeadersWriter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/header/StrictTransportSecurityServerHttpHeadersWriter.html)
- [Javadoc — ServerHttpSecurity, redirectToHttps](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html)
- [Spring Boot — Running Behind a Front-end Proxy Server](https://docs.spring.io/spring-boot/4.1/how-to/webserver.html)
- [MDN — Strict-Transport-Security](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Strict-Transport-Security)
- [HSTS Preload — Requirements and Deployment Recommendations](https://hstspreload.org/)
- [RFC 6797 — HTTP Strict Transport Security](https://www.rfc-editor.org/rfc/rfc6797.html)
- [OWASP — HTTP Strict Transport Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Strict_Transport_Security_Cheat_Sheet.html)
