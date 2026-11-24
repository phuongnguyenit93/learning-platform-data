# Testing Abnormal Paths Across Proxy, Servlet Container, and Security Matchers

> **Scope:** Spring Security **Servlet** (Spring Boot 3.x, Spring Security 6.x, Java 17+). This lesson focuses on testing `HttpFirewall` and path-interpretation consistency across reverse proxies, Servlet containers, Spring Security `RequestMatcher`s, and Spring MVC. The goal is to catch **ambiguous or inconsistently normalized paths** before they create authorization vulnerabilities.

## 1. Why Test Paths Across Multiple Layers?

For an API with an administrative resource `GET /api/admin/report` restricted to `ROLE_ADMIN`, a request can traverse multiple systems:

```text
Client
  |
  | HTTP request-target (path in the actual request)
  v
CDN / WAF / API gateway / reverse proxy
  |  May decode, normalize, rewrite, shift prefix
  v
Servlet container (Tomcat / Jetty / Undertow)
  |  Splits contextPath / servletPath / pathInfo;
  |  has its own rules on characters and URL encoding
  v
Spring Security FilterChainProxy
  |  HttpFirewall inspects and wraps request before matching filter chain
  |  SecurityFilterChain + RequestMatcher determine authorization
  v
DispatcherServlet / Spring MVC HandlerMapping
  |  Maps URL to controller
  v
HTTP response
```

Risk arises when **each layer interprets a path differently**. For instance, a proxy might transform a path form into `/api/admin/report` while downstream security rules are written against another form; or the security layer sees a "public" path while the router executes an "admin" endpoint.

Logically dangerous scenario:

```text
Path form seen by request matcher: /api/public/../admin/report
                               |
                     matcher thinks it is not /api/admin/**
                               |
Path form executed by controller: /api/admin/report
                               |
                  Actual path is a resource requiring ADMIN
```

This is purely an **illustrative mismatch model**, not an assertion that default Spring Security allows such a bypass. Testing aims to prove early rejection or proper authorization **after all transformations**.

Distinguish four outcomes:

- **Rejected at proxy/container**: the application may never see the request.
- **Rejected by `HttpFirewall`**: the request entered the Servlet filter chain but never reached resource matchers.
- **Accepted and passed to Spring Security**: must be authorized according to the actual path executed.
- **No matching route**: fails safely (e.g., 404 or 403 per policy). A "non-match" must never fall into a `permitAll` branch and execute a sensitive endpoint.

Never conclude "Spring Security blocked it" solely because a client received HTTP 400/403: you need evidence pinpointing the responding layer.

## 2. Path Representations to Distinguish

### 2.1. Raw Request-Target, Decoded URL, and Servlet Paths

Suppose a client sends:

```http
GET /api/%2e%2e/admin/report HTTP/1.1
Host: app.example.test
```

`%2e` is the percent-encoded representation of a dot, yet **you cannot assume** every layer handles it identically or decodes the same number of times. A proxy may preserve, reject, decode, or normalize dot segments; a container may block before the app; the app and framework may observe only the transformed value.

Common observable concepts:

| Artifact | Meaning | Point of Caution |
|---|---|---|
| HTTP request-target | Path/query portion actually sent by the client on the HTTP connection | Proxy may alter it before upstream; `curl` often normalizes some URLs without `--path-as-is` |
| URI in proxy access log | Value recorded by the proxy depending on log variables and config | May be raw request or rewritten path; verify which log field is used |
| `HttpServletRequest.getRequestURI()` | Request URI as represented by the container, without query string | Not necessarily byte-for-byte identical to the external Internet request-target |
| `getContextPath()` | Web application prefix on the container | Does not necessarily match external path after gateway prefix rewrites |
| `getServletPath()` / `getPathInfo()` | Path segments mapped by the container to the servlet | Splitting and character handling depend on container and mapping |
| `HttpFirewall.getFirewalledRequest(...)` | Request inspected/wrapped for Spring Security | Firewall may throw `RequestRejectedException` before matchers run |
| `SecurityFilterChain` / `RequestMatcher` | Determines which chain and rule handle the request | Matchers must interpret consistently with the URL actually served by the app |
| Spring MVC `HandlerMapping` | Determines the executing handler/controller | Mapping config, path variables, context path, and servlet mapping all matter |

A `query string` like `?next=/api/admin/report` is a **parameter**, not a path segment of the current route. Do not apply authorization rules by arbitrarily concatenating or normalizing query strings into the path.

### 2.2. Common Abnormal Forms

| Category | Example Test on Simulated Path | What to Verify |
|---|---|---|
| Repeated slashes | `/api//admin/report` | Do proxy/container/firewall collapse `//` or reject? |
| Dot segment | `/api/./admin/report` | Is `./` stripped before matchers and controllers? |
| Parent segment | `/api/x/../admin/report` | Does it resolve to the admin route or get blocked? |
| Encoded dots | `/api/%2e/admin/report`; `/api/%2e%2e/admin/report` | How many times decoded/normalized, and at which layer? |
| Encoded slash | `/api/%2fadmin/report` | Is encoded slash rejected or treated as a separator? |
| Backslash | `/api/%5cadmin/report` or literal `\` | How do container, proxy, or OS interpret it? |
| Semicolon/path parameter | `/api/admin;v=1/report` | Is it blocked, or is `;v=1` stripped when routing/matching compares? |
| Double encoding | `/api/%252e%252e/admin/report` | Does any layer decode again after security already checked? |
| Trailing slash | `/api/admin/report/` | Do MVC and matchers share the same trailing-`/` policy? |
| Case | `/API/admin/report` | Are there case-insensitive matchers or proxy transformations? |
| Rewritten prefix | External `/service/api/admin/report` → upstream `/api/admin/report` | Which path do filter chain and controller authorize against? |
| Normal path with path-like query | `/api/public?next=/api/admin/report` | Query is not mistaken for the admin route |

These examples are **test inputs for authorized environments**, with no guarantee of a single fixed status across all versions and proxies. A case may yield 400, 403, 404, or a valid rewrite; what matters is **never granting wrong permissions and never accidentally running sensitive operations**.

## 3. Where Does Spring Security's HttpFirewall Block?

On the Servlet stack, `FilterChainProxy` uses `HttpFirewall` to inspect and wrap `HttpServletRequest` before deciding which `SecurityFilterChain` applies. The standard default implementation is `StrictHttpFirewall`. It proactively rejects many URL representations difficult to parse safely—such as unusual separators, sensitive percent-encodings, and semicolons—according to the active version's rule set.

Logic flow:

```text
Request from container
        |
        v
StrictHttpFirewall.getFirewalledRequest(request)
        |
        +---- detects disallowed representation ---> RequestRejectedException
        |                                          --> error handling (typically HTTP 400,
        |                                              depending on version/handler config)
        |
        v
Request accepted by firewall
        |
        v
Select SecurityFilterChain -> RequestMatcher -> AuthorizationFilter
        |
        v
MVC HandlerMapping -> Controller
```

**Do not conflate three outcomes**:

1. `RequestRejectedException` is the firewall's decision on a request not allowed to proceed further.
2. `401 Unauthorized` indicates missing/invalid authentication, not the firewall blocking the URL.
3. `403 Forbidden` from authorization may mean insufficient user permissions; HTTP 403 from a proxy, CSRF, or another mechanism must be distinguished via logs and traces.

Spring Security also includes `DefaultHttpFirewall` and various options to relax `StrictHttpFirewall` (such as allowing semicolons or encoded slashes in certain use cases). **Never relax globally to "fix request errors"** before verifying policy across all proxies, containers, matchers, and controllers, as that can introduce inconsistencies or disable dangerous-input detection.

`HttpFirewall` is a checkpoint **inside the Servlet application**. It cannot reconstruct the raw string if an upstream proxy already rewrote, normalized, or blocked the request. Consequently, direct `StrictHttpFirewall` unit tests alone **are insufficient** to prove the full Internet → proxy → container → Spring Security path is safe.

## 4. Security Invariants to Write Down Before Testing

To make tests meaningful, define three example routes:

- `GET /api/public`: permitted without authentication.
- `GET /api/admin/report`: requires `ROLE_ADMIN`.
- All other routes: **deny by default**, unless explicitly declared in the real application.

Invariants to preserve:

**A — No privilege escalation.** Requests from anonymous users or users holding only `ROLE_USER` **must never** return `/api/admin/report` data, regardless of extra slashes, dot segments, semicolons, encoding, prefix rewrites, or trailing slashes.

**B — No mismatch between matcher and handler.** Whenever the container/MVC ultimately executes an admin-protected endpoint, Spring Security must enforce policy matching **that endpoint**. Never let a request match as "public" in security yet execute as "admin" in the controller.

**C — Ambiguous inputs fail or resolve cleanly.** They may be rejected at the proxy, container, or `HttpFirewall`. If forwarded, every layer must agree on route resolution and preserve authorization.

**D — Normal behavior stays intact.** `/api/public` continues returning 200; valid admins still access their resources; nonexistent endpoints never leak another route's data.

**E — Rejecting layer is traceable.** Every test tracks a request ID, client result, edge/upstream record (when available), Servlet/filter status, and whether the handler ran. Never log passwords, `Authorization`, cookies, or raw tokens.

Do not inspect status codes alone: an API could accidentally return 200 with sensitive data, or return 404 from middleware while still triggering side effects. Use **instrumented business markers** in staging (such as handler counters and non-production test fixtures) to verify which controller actually ran.

## 5. Runnable Spring Boot 3 / Security 6 Example

This section builds a small Servlet app with explicit rules and `StrictHttpFirewall`. You can copy it into a new Gradle Spring Boot project with a wrapper. The example uses Spring Boot 3.3.5 and Java 17; no proxy setup is needed to run the baseline.

### 5.1. Gradle Declaration

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

### 5.2. Controller and Real Paths

File `src/main/java/demo/path/PathAuditApplication.java`:

```java
package demo.path;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class PathAuditApplication {
    public static void main(String[] args) {
        SpringApplication.run(PathAuditApplication.class, args);
    }

    @GetMapping("/api/public")
    public Map<String, String> publicEndpoint() {
        return Map.of("resource", "public");
    }

    @GetMapping("/api/admin/report")
    public Map<String, String> adminEndpoint() {
        // Synthetic sample data for illustration, not production data.
        return Map.of("resource", "admin-report");
    }
}
```

File `src/main/java/demo/path/PathSecurityConfig.java`:

```java
package demo.path;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.WebSecurityCustomizer;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.firewall.HttpFirewall;
import org.springframework.security.web.firewall.StrictHttpFirewall;

@Configuration
public class PathSecurityConfig {
    @Bean
    HttpFirewall httpFirewall() {
        // Intentionally retain strict defaults.
        return new StrictHttpFirewall();
    }

    @Bean
    WebSecurityCustomizer webSecurityCustomizer(HttpFirewall firewall) {
        // Attach declared firewall to FilterChainProxy.
        return web -> web.httpFirewall(firewall);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/admin/report")
                    .hasRole("ADMIN")
                // Leave no gaps on unmatched routes.
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

**Why is this configuration instructive?** The specific admin rule precedes the fallback. `denyAll()` ensures unlisted paths are never accidentally reachable. `StrictHttpFirewall` checks abnormal inputs before matchers. Do not use `web.ignoring()` for `/api/**`, because bypassing the entire security filter chain also bypasses its firewall.

The example **does not relax** `allowUrlEncodedSlash`, `allowSemicolon`, or similar flags. When a real application needs matrix variables or special paths, analyze request mapping, proxy, container, and security policy separately before deciding.

### 5.3. Testing Configuration and Firewall Directly With JUnit

File `src/test/java/demo/path/PathSecurityTest.java`:

```java
package demo.path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.security.web.firewall.HttpFirewall;
import org.springframework.security.web.firewall.RequestRejectedException;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PathSecurityTest {
    @Autowired MockMvc mvc;
    @Autowired HttpFirewall firewall;

    @Test
    void publicPathStillWorks() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.resource").value("public"));
    }

    @Test
    @WithMockUser(roles = "USER")
    void ordinaryUserCannotReadAdminReport() throws Exception {
        mvc.perform(get("/api/admin/report"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void authorizedAdminCanReadReport() throws Exception {
        mvc.perform(get("/api/admin/report"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.resource").value("admin-report"));
    }

    @ParameterizedTest
    @ValueSource(strings = {
        "/api//admin/report",
        "/api/admin;v=1/report",
        "/api/%2fadmin/report",
        "/api/%5cadmin/report"
    })
    void firewallRejectsSelectedAmbiguousPaths(String requestUri) {
        // Test firewall directly with simulated URI and servlet path.
        // Not a substitute for real container/reverse proxy tests.
        MockHttpServletRequest request =
                new MockHttpServletRequest("GET", requestUri);
        request.setServletPath(requestUri);

        assertThrows(RequestRejectedException.class,
                () -> firewall.getFirewalledRequest(request));
    }
}
```

Run in a project with Gradle Wrapper:

```bash
./gradlew test
./gradlew bootRun
```

These assertions verify **baseline auth** and firewall behavior on selected direct input strings. In direct tests, `MockHttpServletRequest` keeps the simulated URI untouched; it does **not** fully replicate Tomcat, reverse proxies, browser URL parsers, or TLS infrastructure. Real integration testing in Sections 6–8 determines whether the full pipeline is secure.

The demo app does not provision a `ROLE_ADMIN` user for HTTP Basic; tests create a mock principal via `@WithMockUser`. When running `bootRun`, anonymous `GET /api/admin/report` gets an authentication challenge (typically 401), while `/api/public` returns JSON. Never use Boot's console-generated password as a production authentication policy.

## 6. Real HTTP Testing at Upstream and Reverse Proxy

### 6.1. Establishing a Baseline on Canonical Paths

Before mutating URLs, verify normal requests:

| Path | Caller | Target Outcome |
|---|---|---|
| `GET /api/public` | Anonymous | HTTP 200, JSON `{"resource":"public"}` |
| `GET /api/admin/report` | Anonymous | Rejected as unauthenticated (HTTP Basic typically 401) |
| `GET /api/admin/report` | `ROLE_USER` | 403 |
| `GET /api/admin/report` | `ROLE_ADMIN` | 200, JSON `{"resource":"admin-report"}` |
| `GET /api/unknown` | Any | Rejected by fallback; never returns `admin-report` |

Role-specific cases are verified via `MockMvc` in the example; real HTTP testing requires **authorized** test accounts or staging login mechanisms, never real user accounts or profiles.

### 6.2. Sending Exact Paths With curl

Some HTTP clients automatically strip dot segments (`/./`, `/../`) before sending. When testing, distinguish **the string you type** from **the actual request-target sent on the wire**. `curl --path-as-is` preserves path segments during transmission; `--globoff` prevents `curl`-side URL globbing.

Bash script for a test machine targeting a **designated base URL** (e.g., `http://127.0.0.1:8080` or a staging proxy domain):

```bash
#!/usr/bin/env bash
set -euo pipefail

BASE_URL="$1"

paths=(
  "/api/public"
  "/api/admin/report"
  "/api//admin/report"
  "/api/./admin/report"
  "/api/x/../admin/report"
  "/api/%2e/admin/report"
  "/api/%2e%2e/admin/report"
  "/api/%2fadmin/report"
  "/api/%5cadmin/report"
  "/api/admin;v=1/report"
  "/api/%252e%252e/admin/report"
  "/api/admin/report/"
  "/API/admin/report"
  "/api/public?next=/api/admin/report"
)

for path in "${paths[@]}"; do
  printf '%-43s ' "$path"
  curl --path-as-is --globoff --silent --show-error \
    --output /dev/null --write-out '%{http_code}\n' \
    "$BASE_URL$path"
done
```

Run the script above **only against authorized local/staging environments**. To test Spring Boot directly, save as `probe-paths.sh` and run:

```bash
bash probe-paths.sh http://127.0.0.1:8080
```

For an upstream behind a gateway, rerun against the **public staging** URL with the same test set. Never publish a table claiming "every abnormal path always returns 400": proxies, Servlet containers, and the firewall may block at different layers; nonexistent paths may return 404/403 per route; HTTP clients may refuse to send certain malformed strings.

**Observation note:** the script prints only status codes for triage. If any abnormal path returns **200**, inspect the body, executed endpoint, and principal to confirm whether it was a true privilege bypass or merely `/api/public`. If you see 400/403, trace the rejecting layer instead of immediately assuming the firewall acted.

### 6.3. Inspecting Request-Target and Response Headers

To see what `curl` sends, combine `--verbose` with `--path-as-is` on one case:

```bash
curl --path-as-is --globoff --verbose \
  --output /dev/null \
  "http://127.0.0.1:8080/api/x/../admin/report"
```

Over HTTP/1.1, `curl -v` normally displays the request line with the path; over HTTP/2, it may appear as the `:path` pseudo-header. What the client actually transmits also depends on `curl` version, URL parser, and protocol. Verify via controlled ingress logs or network traces if needed.

To inspect response headers and body on a specific path:

```bash
curl --path-as-is --globoff -i \
  "http://127.0.0.1:8080/api//admin/report"
```

Never substitute `curl -I` for GET: `-I` sends `HEAD`, which may take a different route/matcher. Always use the exact HTTP method you need to protect.

### 6.4. Comparing Both Paths in the Same Environment

Fill out a unified comparison table:

| Case | Client Sends | Direct Container Result | Via Proxy Result | Blocking Layer / Executed Route |
|---|---|---|---|---|
| Baseline public | `/api/public` | Record observed result | Record observed result | Public controller |
| Baseline admin | `/api/admin/report` | Record observed result | Record observed result | Authorization |
| Double slash | `/api//admin/report` | Record observed result | Record observed result | Proxy/container/firewall |
| Encoded slash | `/api/%2fadmin/report` | Record observed result | Record observed result | Proxy/container/firewall |
| Dot segment | `/api/x/../admin/report` | Record observed result | Record observed result | Proxy/container/firewall/route |
| Semicolon | `/api/admin;v=1/report` | Record observed result | Record observed result | Proxy/container/firewall/route |
| Double encoded | `/api/%252e%252e/admin/report` | Record observed result | Record observed result | Decode passes per layer |
| Trailing slash | `/api/admin/report/` | Record observed result | Record observed result | Security matcher and MVC mapping |

This is a **recording template**, not pre-measured output. For valid comparisons, use the same application version and test data. Direct/container calls sometimes use a different `Host` or context path: document that difference and align fixtures/routing equivalently. If the proxy terminates HTTPS to HTTP upstream, external and internal schemes also differ; do not conflate environment differences with URL behavior.

## 7. Pinpointing Which Layer Rejected or Altered the Path

A `400 Bad Request` error can originate from the reverse proxy, Servlet container, or Spring Security's `RequestRejectedHandler`. To distinguish them, maintain a minimal trace chain:

1. **Client** records requested URL, method, protocol, and timestamp. For sensitive requests, never log `Authorization`/cookies/tokens.
2. **Edge/proxy** logs a reliable correlation ID, request path before and after rewrites (if any), client status, and upstream status (if any). Never assume the "URI" log field is always the raw path: read the proxy's exact documentation/config.
3. **Upstream access log** records the URI observed by the Servlet container alongside status. If no upstream record exists, the request was likely blocked before the application.
4. **Security** logs firewall rejections or authorization denials via configured loggers/metrics, avoiding printing unfiltered exceptions/paths or raw credentials.
5. **Controller** uses test-environment-only markers/counters to prove which handler executed. Never add sensitive-data logging to production just for debugging.

Example inference table:

| Evidence | Likely Conclusion | What to Verify Next |
|---|---|---|
| Edge logs 400, upstream has no request | Blocked before container | WAF rules, URI parser, proxy rewrites |
| Upstream logs 400, security has no trace | Container likely blocked it | Container access log, parser, filter ordering |
| Security logs `RequestRejectedException` | `HttpFirewall` rejected it | Request representation reaching firewall, status-returning handler |
| 401/403 from security | Authentication/authorization stopped it | Selected matcher/chain, principal/test fixture |
| HTTP 404 yet unexpected controller marker fired | Routing or logging inconsistency requiring investigation | Controller mapping, error dispatch |
| HTTP 200 with `admin-report` body for unprivileged user | **Critical failure** | Inspect chain/matchers/rewrites and halt rollout |

**Never expose paths containing tokens in logs** during testing. Use non-sensitive fixture paths and a controlled `X-Test-Case-Id` header. For `X-Forwarded-*` and client correlation IDs, trust headers only after a trusted ingress/proxy strips and resets them; client-spoofed headers must never dictate identity or permissions.

## 8. Typical Discrepancies Across Proxy, Container, and Matchers

### 8.1. Reverse Proxy Rewrites/Normalization

Proxy configuration can affect: `//`, dot segments, percent encoding, path prefixes, trailing slashes, URI forwarding when `proxy_pass` includes or omits a URI, and rewrite rules. For example, many systems expose `/service/api/admin/report` externally while upstream receives `/api/admin/report`.

Save the configuration of **the exact environment under test** and test both direct/upstream and edge paths. With NGINX, how `proxy_pass` handles URI parts and log variables can yield different results; other API gateways/CDNs also have their own normalization behaviors. Never assume "a reverse proxy forwards bytes verbatim."

If a proxy normalizes a path so upstream sees a valid path, the firewall may never know the original request was abnormal. Hence **edge and application policies must align**: either reject at the edge, or forward a normalized form handled consistently by Spring Security and MVC without bypass paths.

### 8.2. Servlet Container and URL Encoding

Tomcat, Jetty, and Undertow differ in parsers, mappings, and options for encoded slashes/backslashes/path parameters; they can reject requests before Servlet filters run. Options such as encoded solidus support or relaxed URI characters can alter what passes between layers.

When testing, record **container name, version, context path, servlet mapping**, and any special URL decoding/normalization settings. Never change them solely because a test expected 400 and observed 404: verify the authorization invariant and root cause instead.

### 8.3. SecurityMatcher and RequestMatcher vs. MVC Mapping

Spring Security may define multiple `SecurityFilterChain`s, each chosen via `securityMatcher(...)`; within each chain, `requestMatchers(...)` apply rules. Meanwhile, MVC `HandlerMapping` selects the executing controller. Never assume security matcher patterns and MVC routes interpret every abnormal representation identically if proxies/containers transformed them.

A risky configuration pattern: a very strict `/api/admin/**` chain paired with a fallback `/**` chain using `permitAll` for everything unmatched. If an abnormal representation misses the admin matcher while MVC still routes to admin, a vulnerability opens. **Keep fallbacks strict** and test real HTTP requests.

When using context paths or proxy prefixes, never try to patch around it by matching raw client-supplied `X-Forwarded-Prefix`. Forwarded headers must be handled consistently and trusted only from trusted proxies; that is a separate trust-boundary concern, not a reason to drop `HttpFirewall`.

### 8.4. Semicolons and Matrix Variables

Some applications use path parameters/matrix variables like `/items;color=red/123`. By strict default, `StrictHttpFirewall` rejects semicolons to prevent URL-matching ambiguity. If genuinely required by business logic, the fix is not simply turning on `setAllowSemicolon(true)` app-wide: you must test the post-container URL, route policies, MVC, caches, and security matchers across the full matrix.

Absent an explicit business need, keeping the default policy and using query parameters where appropriate is safer. Never use paths with special characters as a workaround to evade container or Spring Security rules.

## 9. Layered Testing Methodology: Unit, Integration, End-to-End

| Level | Where It Runs | What It Guarantees | What It Cannot Prove Alone |
|---|---|---|---|
| `HttpFirewall` unit | `MockHttpServletRequest` → `StrictHttpFirewall` | Strings reaching the firewall are rejected/accepted per config | Proxy, container HTTP parser, post-rewrite URLs |
| MVC/Security integration | `MockMvc` + Spring Security | Normal endpoints enforce auth/authz and fallback rules work | Raw bytes on the wire, reverse proxy/parser behavior |
| Embedded container | `@SpringBootTest(webEnvironment = RANDOM_PORT)` or real server | Container processes real paths before filters and returns HTTP responses | Deployment-environment proxy/CDN/gateway |
| End-to-end via proxy | Real staging domain + client preserving request-target | Full pipeline, statuses, headers, rewrites, and absence of permission bypass | Production variants if staging config differs |
| Browser | Real browser when frontend issues requests | Certain URLs may be normalized by the browser before sending | Malformed requests browsers refuse to send |

**Two assertion groups to verify in parallel**:

- **Policy**: anonymous/`ROLE_USER` never receives `admin-report` data; `ROLE_ADMIN` can access via canonical path; public routes work properly.
- **Consistency**: for abnormal paths, if processed, security and controller must agree on the route; if rejected, identify the rejecting layer without treating 400/403/404 as sole proof.

Run `MockMvc` and firewall unit tests in CI; run embedded-container integration tests on every Spring Security/container upgrade; run an E2E probe suite on staging whenever proxy rewrites, WAF rules, context paths, or API gateways change. Avoid mutating payloads; use GETs against non-sensitive fixtures and trace markers.

## 10. Expansion Matrix for Regressions and Upgrades

Build test cases across multiple axes while keeping combinations meaningful:

| Axis | Branches to Test | Rationale |
|---|---|---|
| Path input | Canonical, `//`, `./`, `../`, `%2e`, `%2f`, `%5c`, `;`, `%25`, trailing `/` | Covers common normalization/decoding ambiguity points |
| Caller | Anonymous, `ROLE_USER`, `ROLE_ADMIN` | Detects privilege bypasses or over-blocking |
| Connection path | Direct container, via reverse proxy | Catches proxy rewrites ahead of the firewall |
| Method | `GET` and relevant business methods (if any) | Avoids path-only matchers missing method distinctions |
| Security rules | Public routes, protected routes, deny fallback | Detects unintended chain/rule fallthrough |
| Configuration | Before/after upgrading Spring Security, container, proxy | Catches behavioral regressions |

When a test fails, record the **exact request-target**, method, HTTP protocol, edge/upstream URLs, per-layer statuses, selected chain/matcher, controller marker, library versions, and relevant configs. For percent-encoded paths in particular, include both uppercase and lowercase hex sequences if proxies/parsers differ.

Never automatically "fix the test" by permitting every encoded slash or semicolon: policy changes require an explicit threat model, proof of consistent routing/matching, and end-to-end verification.

## 11. Self-Check Questions

**Question 1.** A request `/api//admin/report` returns 400 via the gateway, whereas sending it directly to the container triggers `RequestRejectedException`. What can you conclude?

**Answer:** Both paths block it, but at **two different layers**. Confirm the gateway actually returned 400 without hitting upstream; direct calls hit the firewall. Never use identical status codes as proof of the same root cause.

**Question 2.** Spring Security has a strict admin chain and a `permitAll` fallback chain. Why is this a prime target for abnormal-path testing?

**Answer:** If the admin chain fails to match a URL representation while MVC still executes the admin resource after transformation, requests could fall into the overly broad fallback. The foundational fix is consistent matcher/route design, proper firewall settings, and a protected fallback.

**Question 3.** Why doesn't a passing `StrictHttpFirewall` unit test prove a public API behind a proxy is safe?

**Answer:** Unit tests feed simulated requests directly into the firewall, bypassing proxy and Servlet container decoding/rewriting. E2E tests must prove the **actual request-target** through the infrastructure is still rejected or properly authorized.

**Question 4.** If `curl --path-as-is` receives 404 for an encoded path, is 404 enough to conclude safety?

**Answer:** Not yet. Verify no controller ran unexpectedly, no sensitive data appeared in the body, and test across different user roles. Attribute the 404 to the exact layer that returned it.

**Question 5.** Should `setAllowUrlEncodedSlash(true)` be enabled so every encoded-slash test turns into 200?

**Answer:** No. Relaxation must come from a real business need after auditing proxy/container/matcher/MVC behavior, access policies, and regression tests. The goal is **correct and safe routing**, not accepting every input.

## 12. Acceptance Checklist

- [ ] Documented exact URLs and security rules for public routes, sensitive routes, and fallback.
- [ ] Recorded versions/configs of proxy, container, Spring Security, servlet mappings, and rewrite rules.
- [ ] Verified actual request-targets using clients that do not strip path segments (when needed).
- [ ] Tested repeated slashes, dot/parent segments, percent encoding, encoded slashes/backslashes, semicolons, double encoding, trailing slashes, and prefix rewrites.
- [ ] Executed the same matrix directly against the container and through the proxy with anonymous, ordinary-user, and admin fixtures.
- [ ] Distinguished errors across proxy, container, `HttpFirewall`, authorization, and Spring MVC using controlled correlation IDs/traces.
- [ ] Confirmed no abnormal path lets anonymous or unprivileged users read admin data or invoke admin actions.
- [ ] Confirmed normal routes work properly and the fallback opens no unintended routes.
- [ ] Kept tokens, cookies, credentials, and personal data out of test logs.
- [ ] Added observed discrepancies to the regression suite before changing configs or upgrading versions.

**Core takeaway:** `HttpFirewall` is the layer rejecting ambiguous inputs in Spring Security Servlet, yet route safety must be proven across the **entire chain: client → proxy → container → firewall → RequestMatcher → MVC handler**. The right outcome is that rejected paths are explainable or handled with **the exact same access controls as the underlying resource**—not merely an HTTP status that "looks safe."