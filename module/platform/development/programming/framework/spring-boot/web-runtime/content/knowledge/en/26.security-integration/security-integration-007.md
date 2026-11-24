# Protecting Static Resources, Management Endpoints, and Diagnostic Information

A Spring Boot application typically serves several kinds of HTTP resources: CSS/JavaScript meant for everyone, pages and APIs for logged-in users, administrative operations, health checks, metrics, and diagnostic tools such as logs, thread dumps, environment properties, or heap dumps. **These resource categories must not share a single access policy by default.** Login page CSS must load before authentication; admin pages require role checks; health endpoints need enough information for probes without exposing infrastructure layout; and heap dumps or environment values generally should not be exposed over production HTTP.

The lesson goal is to design a **minimal access surface**, combining **Spring Security authorization**, **Spring Boot Actuator exposure**, and **network/content restrictions**. The main examples target **Spring Boot 3.x, Spring MVC/Servlet, Spring Security 6.x, and Java 17+**. The WebFlux-specific section is clearly marked as a different API and must not be mixed into the MVC program.

**Three layers of defense:**

1. **Do not expose unnecessarily:** an endpoint with no HTTP mapping cannot be invoked via that route.
2. **Enforce authentication and authorization:** exposed endpoints must still be protected with appropriate roles/permissions.
3. **Restrict returned content and network access:** authorized callers should see only needed data, and management channels should not be open to the public internet by default.

## 1. Learning Objectives

After this article, you will be able to:

- Distinguish public static resources, authenticated pages, admin endpoints, OPS endpoints, health probes, and sensitive diagnostics.
- Use `PathRequest.toStaticResources().atCommonLocations()` with `permitAll()` rather than excluding all static requests from the filter chain.
- Understand `SecurityFilterChain`, `securityMatcher`, `requestMatchers`, `@Order`, `hasRole`, `authenticated`, and `anyRequest`.
- Understand the differences among **enabled**, **exposed over HTTP/JMX**, and **authorized** in Spring Boot Actuator.
- Use `EndpointRequest.toAnyEndpoint()` and `EndpointRequest.to("health")` for Actuator instead of brittle hardcoded matchers.
- Build a Spring Boot app with public CSS, authenticated pages, admin APIs, restricted diagnostics, and a secured Actuator.
- Verify 200, 401, 403, and 404 responses with `curl` and `MockMvc`.
- Design liveness/readiness health endpoints without leaking details, and manage separate management ports, sanitization, CSRF, and networking.
- Recognize anti-patterns that lead to data leaks or loss of observability during deployment.

## 2. Resource Classification and Access Table

Before writing security configuration, list all endpoints and their sensitivity levels:

| Group | Examples | Starting Rule | Notes |
| --- | --- | --- | --- |
| Public static | `/css/site.css`, `/js/app.js`, logo, favicon | `permitAll()` for appropriate paths | Preserves security headers; never place secrets in static directories |
| Public pages | `/`, `/login`, `/about` | Intentional `permitAll()` | Never open `/**` |
| User pages/APIs | `/account`, `/orders` | `authenticated()` + data ownership checks | Login alone is not enough to read another user's data |
| Administration | `/admin/**` | `hasRole("ADMIN")` or stricter policy | Protect all HTTP methods |
| Internal diagnostics | `/internal/diagnostics` | `hasRole("OPS")`, restricted output | Never treat “hard-to-guess URLs” as security |
| Health probes | `/actuator/health`, `/livez`, `/readyz` when enabled | Access just enough for LB/kubelet, minimal output | DOWN health can return 503 |
| Metrics | `/actuator/metrics`, `/actuator/prometheus` | OPS/internal scrapers only | Never use labels containing tokens or user IDs |
| Structural info | `/actuator/beans`, `/actuator/mappings`, `/actuator/conditions` | Usually unexposed in production | Leaks app/bean/mapping structure |
| Configuration | `/actuator/env`, `/actuator/configprops` | Usually unexposed | Sanitization does not replace exposure control |
| Sensitive dumps | `/actuator/heapdump`, `/actuator/logfile`, `/actuator/httpexchanges` | Unexposed except controlled investigation | Can contain secrets, PII, session data |
| Mutating operations | `/actuator/loggers` and `/actuator/shutdown` | Tightly restricted or disabled | Some operations use POST/PUT/DELETE |

**Opening an HTTP path does not make the underlying data safe to publish.** Files in `src/main/resources/static` can be served over the web by Spring MVC; accidentally putting `backup.zip`, keys, customer CSV exports, logs, or heap dumps in that folder is a design flaw even before Spring Security is considered.

## 3. How Spring Security Selects Filter Chains and Authorization Rules

In a Servlet app, requests pass through Spring Security's `FilterChainProxy`. Multiple `SecurityFilterChain` beans can exist, each with a matcher deciding which URL group it handles. Spring Security picks the **first matching chain**; within a chain, authorization matchers are evaluated in rule order.

```text
Browser / HTTP client
         |
         v
 Servlet filters -> Spring Security FilterChainProxy
         |
         +-- Chain #1: securityMatcher(EndpointRequest.toAnyEndpoint())
         |      +-- health -> permitAll
         |      +-- other Actuator endpoints -> ROLE_OPS
         |
         +-- Chain #2: remaining requests
                +-- static CSS/JS/images -> permitAll
                +-- GET / -> permitAll
                +-- /admin/** -> ROLE_ADMIN
                +-- /internal/diagnostics -> ROLE_OPS
                +-- all other routes -> authenticated
         |
         v
 DispatcherServlet -> Controller/Resource Handler/Actuator
```

Two distinct concepts:

- `http.securityMatcher(...)`: whether **the entire chain** applies to the request.
- `authorizeHttpRequests(...requestMatchers(...))`: **authorization rules within the matched chain**.

If only a chain matching Actuator exists without a chain for the rest of the app, requests not matching Actuator may fall outside expected protection. Declaring a custom chain means the author must understand how security auto-configuration backs off.

### 3.1. Authentication and Authorization

- **Authentication** proves who the caller is.
- **Authorization** decides whether that caller is permitted to perform a specific action.
- `authenticated()` only requires a verified identity; it **does not** check whether the user owns an order or holds admin rights.
- `hasRole("OPS")` checks the `ROLE_OPS` authority by default, not the plain string `OPS`.
- `hasAuthority("OPS")` checks the exact authority `OPS`.
- `permitAll()` permits access under that authorization rule; it does not mean the request automatically skips headers, filters, or remaining safeguards.

URL-based authorization is only one layer. For multi-tenant data, the service layer must also check user ID/tenant ID/record ownership and business conditions.

### 3.2. Rule Order Matters Greatly

**Wrong** because the broad `/**` rule comes first:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/**").permitAll()
    .requestMatchers("/admin/**").hasRole("ADMIN")
);
```

The admin rule may never be reached. Fix by placing specific rules before fallbacks and ending with `anyRequest().authenticated()` or `denyAll()` per policy.

## 4. Static Resources: permitAll Instead of Ignoring

### 4.1. Spring Boot Static Mapping

Spring MVC / Boot 3.x searches static resources in:

```text
classpath:/META-INF/resources/
classpath:/resources/
classpath:/static/
classpath:/public/
```

`src/main/resources/static/css/site.css` is served by default at `/css/site.css`. You can customize `spring.mvc.static-path-pattern` or `spring.web.resources.static-locations`. WebJars handle `/webjars/**` paths.

Do not confuse static files with Thymeleaf templates in `templates`. An HTML page rendered by a controller may request public CSS; the browser must load CSS even before the user logs in.

### 4.2. The Right Way to Open Them

With Spring Boot 3.x Servlet:

```java
.requestMatchers(
    PathRequest.toStaticResources().atCommonLocations()
).permitAll()
```

Import `PathRequest` from `org.springframework.boot.autoconfigure.security.servlet.PathRequest`. This matcher covers common static resource locations; if you change resource locations or static path patterns, verify and add the exact paths that must be public.

Files like `robots.txt` or favicon may need extra rules if not covered by the common matcher:

```java
.requestMatchers("/favicon.ico", "/robots.txt").permitAll()
```

That is a **snippet inside `authorizeHttpRequests`**, not a standalone program.

### 4.3. Why Avoid `web.ignoring`?

An older pattern:

```java
web.ignoring().requestMatchers("/css/**", "/js/**");
```

If a request bypasses the security filter chain entirely, it can lose the security response headers added by Spring Security. Spring Security now recommends `permitAll` for static resources; Spring Security 6 also reduced the session-checking overhead for public rules.

`permitAll` **does not** make the app completely secure by itself. For instance, Content Security Policy (CSP) must be designed per web app; do not assume every header has a suitable default.

### 4.4. “Private” Static Files Are No Longer Simple Public Static Files

If you have documents like `/reports/private.pdf` or customer uploads, do not place them under static `permitAll`. Use a download controller/service with object-level authorization, or protected object storage with short-lived signed URLs. If a CDN or NGINX serves files directly without hitting Spring Boot, JVM rules **do not run**. Enforce protection at the CDN/storage/edge, not just via backend `requestMatchers`.

## 5. Spring Boot Actuator: Three Separate Security Gates

Actuator provides operational endpoints such as `health`, `info`, `metrics`, `env`, `beans`, `mappings`, `conditions`, `threaddump`, `heapdump`, and `loggers`. For a client to actually use an endpoint, all of the following must hold simultaneously:

1. The endpoint exists, is **enabled**, and has its required dependencies.
2. The endpoint is **exposed** over the relevant protocol (HTTP/JMX).
3. The request passes **network policy** and **authentication/authorization**.

```text
Endpoint available?
     |
     +-- disabled/unavailable ---> no such endpoint exists
     |
     v
Exposed over HTTP?
     |
     +-- no --------------------> no HTTP mapping for endpoint
     |
     v
Network/proxy permits?
     |
     +-- no --------------------> blocked outside app
     |
     v
Spring Security permits?
     |
     +-- no --------------------> usually 401 or 403
     |
     v
Endpoint returns information or executes operation
```

**Boot 3.3 exposes only `health` over HTTP/JMX by default.** When Spring Security is on the classpath and there is **no** custom `SecurityFilterChain` bean, Boot automatically secures Actuator endpoints other than health. **Once you declare a custom `SecurityFilterChain`**, Boot steps back from web security auto-configuration and you must protect both Actuator and application URLs yourself.

### 5.1. Exposure and Authorization Are Two Separate Concerns

Configuration exposing only three endpoints:

```properties
management.endpoints.web.exposure.include=health,info,metrics
```

This line does not grant anonymous callers permission to read `metrics`. Conversely, adding `hasRole("OPS")` for `env` does not expose `env` if it has not been included.

`management.endpoints.web.exposure.exclude` takes precedence over `include`. JMX exposure uses separate properties `management.endpoints.jmx.exposure.include/exclude`, so disabling HTTP exposure does not automatically close JMX.

**Not recommended for production:**

```properties
management.endpoints.web.exposure.include=*
```

This can bring many enabled endpoints onto the HTTP surface, widening risk even behind Basic auth. If needed temporarily for investigation, prefer including only the exact required ID, restricting to a private network, auditing, and rolling back afterward.

### 5.2. Actuator Sensitivity Table

| Endpoint | Data/Function | Typically Appropriate Policy |
| --- | --- | --- |
| `health` | Service health status | Minimal output for probes |
| `info` | Intentionally supplied metadata | Verify no unnecessary build/commit/internal details leak |
| `metrics`/`prometheus` | App, JVM, HTTP metrics | Trusted OPS/scrapers only; never put PII in labels |
| `env`/`configprops` | Configuration/environment | Unexposed by default in production; still sanitize |
| `beans`/`mappings` | Spring beans/HTTP routes layout | Do not expose except controlled diagnostics |
| `conditions` | Auto-configuration evaluation reasons | Usually unexposed |
| `threaddump` | Thread stacks | Can reveal internal details |
| `heapdump` | JVM heap snapshot | Highly sensitive; may hold secrets, tokens, PII |
| `logfile` | Application logs | Can hold session IDs, emails, URLs, traces |
| `httpexchanges` | Recent HTTP request/response metadata if repository configured | Reveals patterns and headers |
| `loggers` | View/modify logging levels | Restrict role and write operations |
| `shutdown` | Stop application, disabled by default | Keep disabled except rare specialized needs |

“Authenticated” is still not sufficient to download heap dumps or change logger levels. Production requires separate human/machine permissions, management networks, MFA/SSO, auditing, and approval workflows where appropriate.

## 6. Health Endpoint and Minimal Information

`GET /actuator/health` may return when healthy:

```json
{"status":"UP"}
```

This is an **example**; when the app is DOWN or readiness is not met, the status and HTTP code can differ.

Spring Boot offers:

```properties
management.endpoint.health.show-details=never
management.endpoint.health.show-components=never
```

`show-details` accepts `never`, `when-authorized`, and `always`. Boot 3.3 defaults to `never`. If you pick `when-authorized` without specifying `management.endpoint.health.roles`, any authenticated user may qualify to see details under the health endpoint policy—which is often broader than intended.

**Never pair `permitAll` on health with `show-details=always` lightly.** Database topology, caches, external APIs, health contributors, or error messages are not details that anonymous internet clients need to see.

### 6.1. Liveness and Readiness

In Kubernetes, Boot provides health groups:

```text
/actuator/health/liveness
/actuator/health/readiness
```

Boot enables probes automatically in Kubernetes environments and can enable them elsewhere via:

```properties
management.endpoint.health.probes.enabled=true
```

- **Liveness**: is the process alive or should it restart? Do not tie DB/shared dependencies to liveness just to trigger cascading restarts across all pods whenever the DB blips.
- **Readiness**: is the app ready to serve traffic? Include external dependencies according to actual serving ability rather than blindly adding every dependency.
- **Startup probe**: helpful for slow-starting apps when infrastructure might otherwise kill them before startup finishes.

When management runs on a separate port, probes hitting only the management web server can miss failures on the main app port. Boot supports:

```properties
management.endpoint.health.probes.add-additional-paths=true
```

to expose `/livez` and `/readyz` on the main port under appropriate configuration. When enabling additional paths, update your **application security chain** for those exact two paths or restrict probe access to trusted networks; do not let kubelet get 401. At the same time, do not open them more broadly than infrastructure requires.

## 7. Runnable Spring Boot 3.x Java 17+ Example

The demo includes:

- `GET /`: public text.
- `GET /css/site.css`: public CSS via Spring MVC static resource handling.
- `GET /account`: requires logged-in user.
- `GET /admin/summary`: requires ADMIN role.
- `GET /internal/diagnostics`: requires OPS role.
- `GET /actuator/health`: minimal health for anonymous callers.
- `GET /actuator/info` and `/actuator/metrics`: OPS role only.
- `/actuator/env`, `/heapdump`, and other sensitive endpoints are **not exposed**.

For quick curl verification, it uses HTTP Basic and **two in-memory demo users**. This is strictly a local lab; never use demo credentials in production.

### 7.1. Creating the Project and Dependencies

In [Spring Initializr](https://start.spring.io/), choose **Java 17+**, **Spring Boot 3.3.x** (or a compatible 3.x release), **Gradle/Groovy**, and dependencies **Spring Web**, **Spring Security**, and **Spring Boot Actuator**.

In the Initializr-generated `build.gradle`, the core dependencies block is:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

This is a **dependencies snippet**, not a standalone complete `build.gradle`. Initializr supplies plugins, repositories, versions/BOM, and the Gradle Wrapper. Spring Security 6.x does not use `WebSecurityConfigurerAdapter` from older tutorials. Do not mix in Spring Boot 4.x code without checking starter/API changes.

Create the files:

```text
src/
  main/
    java/demo/
      SecureRuntimeApplication.java
      SecurityConfiguration.java
      ProtectedEndpoints.java
    resources/
      application.properties
      static/css/site.css
  test/
    java/demo/
      SecurityRulesTest.java
```

### 7.2. SecureRuntimeApplication.java

File `src/main/java/demo/SecureRuntimeApplication.java`:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecureRuntimeApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecureRuntimeApplication.class, args);
    }
}
```

Placing the main class in package `demo` enables scanning of controllers and security configuration in the same package.

### 7.3. SecurityConfiguration.java

File `src/main/java/demo/SecurityConfiguration.java`:

```java
package demo;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.boot.autoconfigure.security.servlet.PathRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class SecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain actuatorChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher(EndpointRequest.toAnyEndpoint())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(EndpointRequest.to("health")).permitAll()
                .anyRequest().hasRole("OPS"))
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    PathRequest.toStaticResources().atCommonLocations())
                    .permitAll()
                .requestMatchers("/", "/favicon.ico").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .requestMatchers("/internal/diagnostics").hasRole("OPS")
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults());

        // Let Spring Security apply default CSRF.
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService demoUsers(
            PasswordEncoder encoder,
            @Value("${demo.user-password}") String userPassword,
            @Value("${demo.ops-password}") String opsPassword) {
        return new InMemoryUserDetailsManager(
            User.withUsername("viewer")
                .password(encoder.encode(userPassword))
                .roles("USER")
                .build(),
            User.withUsername("operator")
                .password(encoder.encode(opsPassword))
                .roles("USER", "OPS", "ADMIN")
                .build());
    }
}
```

Explanation:

1. `@Order(1)` causes the Actuator chain to be evaluated first. `EndpointRequest.toAnyEndpoint()` matches endpoints according to the active Actuator mapping; it adapts better than hardcoding `/actuator/**` if the base path changes.
2. `EndpointRequest.to("health")` matches health and health group subpaths. Health is `permitAll`, while all other exposed Actuator endpoints require `ROLE_OPS`.
3. `@Order(2)` protects the remaining URLs. Public static resources are `permitAll`, admin routes require ADMIN, and internal diagnostics require OPS.
4. `anyRequest().authenticated()` prevents new URLs from accidentally becoming public before explicit rules are added. It does not replace object-level permission checks inside services.
5. `httpBasic` enables curl testing. There is no `csrf.disable()` because this example is GET-only and has no reason to turn off CSRF app-wide.
6. Demo passwords are BCrypt-hashed at initialization. **BCrypt does not turn short example passwords into production-grade credentials**; use a real identity provider/secret management in production.

**Important:** a custom `SecurityFilterChain` causes Boot's Actuator web-security auto-configuration to back off. You must have chains covering both Actuator and the application. With multiple chains, ordering and `securityMatcher` rules must be tested.

### 7.4. ProtectedEndpoints.java

File `src/main/java/demo/ProtectedEndpoints.java`:

```java
package demo;

import java.security.Principal;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProtectedEndpoints {

    @GetMapping("/")
    public String index() {
        return "public-page\n";
    }

    @GetMapping("/account")
    public ResponseEntity<String> account(Principal principal) {
        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body("account=" + principal.getName() + "\n");
    }

    @GetMapping("/admin/summary")
    public ResponseEntity<String> adminSummary() {
        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body("admin-access=granted\n");
    }

    @GetMapping("/internal/diagnostics")
    public ResponseEntity<String> diagnostics() {
        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body("diagnostics=limited\n");
    }
}
```

`CacheControl.noStore()` is used on user/admin/diagnostic data to discourage caches from storing responses. It does not replace authentication or stop proxies/logs from recording bodies. `/internal/diagnostics` only returns a short string; real production diagnostics must control returned content, masking, and dedicated auditing.

### 7.5. Static CSS

File `src/main/resources/static/css/site.css`:

```css
body {
    margin: 2rem;
    font-family: sans-serif;
}

h1 {
    color: #234a75;
}
```

Thanks to Spring MVC's static resource handler, this file is accessible at `GET /css/site.css`. Because requests go through the security chain with `permitAll`, it requires no Basic auth yet can still receive default security headers.

### 7.6. application.properties

File `src/main/resources/application.properties`:

```properties
server.port=8080

# Expose only the Actuator endpoints needed for the lesson.
management.endpoints.web.exposure.include=health,info,metrics

# Do not expose component/health details to anonymous callers.
management.endpoint.health.show-details=never
management.endpoint.health.show-components=never

# Disable the discovery page; this does NOT replace security.
management.endpoints.web.discovery.enabled=false

# Do not expose Actuator over JMX in this example.
management.endpoints.jmx.exposure.exclude=*

# Keep configuration values sanitized.
management.endpoint.env.show-values=never
management.endpoint.configprops.show-values=never

# Minimize error details returned by Spring Boot.
server.error.include-message=never
server.error.include-stacktrace=never

# LOCAL DEMO ONLY. Production must not use fallback passwords.
demo.user-password=${DEMO_USER_PASSWORD:local-user-only}
demo.ops-password=${DEMO_OPS_PASSWORD:local-ops-only}
```

Remember that `management.endpoints.web.discovery.enabled=false` only turns off the links listing page; it **does not block direct requests** to exposed endpoints. Primary defense remains exposure allowlists + security rules + network restrictions.

In production, never commit demo accounts or static passwords. Use a secret manager, SSO, machine identity, MFA, or mTLS as appropriate; also restrict which clients can reach the management port.

### 7.7. Running

From the project directory with the Gradle Wrapper:

```bash
./gradlew bootRun
```

PowerShell:

```powershell
.\gradlew.bat bootRun
```

This is a Spring app with dependencies; running `javac SecurityConfiguration.java` alone without the classpath will not compile. The app listens on `http://localhost:8080` by default under the demo configuration if the port is free.

In this lesson, fallback passwords are **strictly for local HTTP testing**:

```text
viewer   / local-user-only
operator / local-ops-only
```

To supply different passwords via environment variables:

```bash
export DEMO_USER_PASSWORD='replace-local-user'
export DEMO_OPS_PASSWORD='replace-local-ops'
./gradlew bootRun
```

PowerShell:

```powershell
$env:DEMO_USER_PASSWORD = "replace-local-user"
$env:DEMO_OPS_PASSWORD = "replace-local-ops"
.\gradlew.bat bootRun
```

HTTP Basic sends decodable credentials in the Authorization header, so **never use plain HTTP over untrusted networks**. In production, use TLS and managed identity mechanisms.

## 8. Verifying with curl: 200/401/403/404

### 8.1. Public Static

```bash
curl -i http://localhost:8080/css/site.css
curl -i http://localhost:8080/
```

Expected HTTP 200 for both. `/` returns text:

```text
public-page
```

If CSS returns 404, check file path and resource mapping; if CSS returns 401, check matchers. **Do not fix a CSS 404 by indiscriminately adding `permitAll`.**

### 8.2. Authentication-Required Page

```bash
curl -i http://localhost:8080/account
```

Expected **401 Unauthorized** from Basic security.

```bash
curl -i -u viewer:local-user-only \
  http://localhost:8080/account
```

Expected 200 with body:

```text
account=viewer
```

### 8.3. Administration

```bash
curl -i -u viewer:local-user-only \
  http://localhost:8080/admin/summary
```

Expected **403 Forbidden**: user is logged in without `ROLE_ADMIN`.

```bash
curl -i -u operator:local-ops-only \
  http://localhost:8080/admin/summary
```

Expected 200, body:

```text
admin-access=granted
```

### 8.4. Internal Diagnostics

```bash
curl -i -u viewer:local-user-only \
  http://localhost:8080/internal/diagnostics

curl -i -u operator:local-ops-only \
  http://localhost:8080/internal/diagnostics
```

Expected 403 and 200 respectively; response when authorized:

```text
diagnostics=limited
```

### 8.5. Actuator Health and Metrics

```bash
curl -i http://localhost:8080/actuator/health

curl -i http://localhost:8080/actuator/metrics

curl -i -u viewer:local-user-only \
  http://localhost:8080/actuator/metrics

curl -i -u operator:local-ops-only \
  http://localhost:8080/actuator/metrics
```

When healthy, health typically returns 200 with status `UP` and no component details. Metrics returns 401, 403, and 200 respectively based on authentication and `ROLE_OPS`. Never assume health always returns 200: when health is DOWN, Boot can return 503 per status mapping.

### 8.6. Unexposed Endpoint

`env` is not in the exposure list. To separate route errors from authentication, test **with the authenticated operator**:

```bash
curl -i -u operator:local-ops-only \
  http://localhost:8080/actuator/env
```

Expected **404 Not Found** in the example. Calling the same URL anonymously may return 401 from the application fallback chain **before MVC determines the URL does not exist**. Thus 401 does not prove an endpoint is exposed, and 404 does not prove security rules are right; consider exposure as well.

### 8.7. Results Matrix

| Route | Anonymous | Viewer | Operator |
| --- | --- | --- | --- |
| `GET /` | 200 | 200 | 200 |
| `GET /css/site.css` | 200 | 200 | 200 |
| `GET /account` | 401 | 200 | 200 |
| `GET /admin/summary` | 401 | 403 | 200 |
| `GET /internal/diagnostics` | 401 | 403 | 200 |
| `GET /actuator/health` | 200 if UP | 200 if UP | 200 if UP |
| `GET /actuator/metrics` | 401 | 403 | 200 |
| `GET /actuator/env` | May be 401 from fallback | 404 | 404 |

This table assumes the app runs with the demo HTTP Basic setup, Actuator exposure list, and role assignments above. Changing the web stack, management context, or security entry points may alter statuses; verify against your actual environment.

## 9. Automated Testing with MockMvc

`spring-security-test` is already in the dependencies from Section 7.1. Create `src/test/java/demo/SecurityRulesTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityRulesTest {

    @Autowired
    MockMvc mvc;

    @Test
    void cssIsPublic() throws Exception {
        mvc.perform(get("/css/site.css"))
            .andExpect(status().isOk());
    }

    @Test
    void accountRequiresLogin() throws Exception {
        mvc.perform(get("/account"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(roles = "USER")
    void userCannotViewAdmin() throws Exception {
        mvc.perform(get("/admin/summary"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = {"USER", "OPS", "ADMIN"})
    void operatorCanViewAdmin() throws Exception {
        mvc.perform(get("/admin/summary"))
            .andExpect(status().isOk());
    }

    @Test
    void publicHealth() throws Exception {
        mvc.perform(get("/actuator/health"))
            .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(roles = "USER")
    void userCannotViewMetrics() throws Exception {
        mvc.perform(get("/actuator/metrics"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "OPS")
    void opsCanViewMetrics() throws Exception {
        mvc.perform(get("/actuator/metrics"))
            .andExpect(status().isOk());
    }
}
```

Run:

```bash
./gradlew test
```

`@WithMockUser` mocks authentication in tests; it does not prove HTTP Basic passwords are verified, cookie policies are safe, or a separate management port is properly configured. Combine MockMvc with integration tests over real HTTP and proxy/network checks. If management moves to a separate web context/port, MockMvc for the main application may not represent the management listener completely.

## 10. Separating the Management Port and Network Policy

A production configuration might place Actuator on a separate port:

```properties
server.port=8080
management.server.port=8081
management.server.address=127.0.0.1
management.endpoints.web.exposure.include=health,metrics
```

This is an **alternative to the demo**, not lines to append while expecting all `:8080` tests to stay the same. `management.server.address` can only differ when the management port differs from the main port. Binding `127.0.0.1` makes sense when the scraper runs on the same host or via an authorized port-forward; in Kubernetes, other pods cannot connect to this pod's loopback directly.

If the management port listens on all interfaces and the firewall is open to the internet, separating the port alone **does not create a trusted network**. You need Security Groups/NetworkPolicy/service mesh/ingress ACLs, TLS/mTLS, and proper identities.

Actuator security rules can run in a separate management web context; verify on **real ports** rather than assuming main-server filter configs automatically protect all management-server routes properly. Also never expose a public ingress to `/actuator/**` merely because monitoring needed access.

### 10.1. Health Probes on the Main Port

Boot 3.3 supports additional paths:

```properties
management.endpoint.health.probes.enabled=true
management.endpoint.health.probes.add-additional-paths=true
```

This typically adds `/livez` and `/readyz` on the main application port; health on a separate management port does not necessarily detect issues on the main port. When enabling additional paths, the example's application chain uses `anyRequest().authenticated()`, so a credential-less kubelet may receive 401. Permit **only those exact paths**, restrict probe source networks, and verify during rolling deployments. Never use `anyRequest().permitAll()` to fix probe failures.

## 11. Never Let Diagnostic Information Leak Over HTTP

### 11.1. env and configprops

`/actuator/env` and `/actuator/configprops` can disclose property names, configuration sources, and permitted values. Boot 3.3 **sanitizes values** by default (e.g., `******`). To keep policy explicit:

```properties
management.endpoint.env.show-values=never
management.endpoint.configprops.show-values=never
```

`when-authorized` can allow authenticated users to view values depending on `management.endpoint.env.roles` or endpoint-specific roles; when no roles are configured, “authorized” can be broader than expected. `always` raises leak risk; never turn it on carelessly in production. Even when values are masked, property names and sources can still reveal architecture. **Unexposing when unnecessary** is the first line of defense.

### 11.2. Heap Dumps and Thread Dumps

`heapdump` can contain passwords, session attributes, OAuth/access tokens, and personal data still in memory. It is not a “harmless debug file”. During investigations, use an isolated channel, temporary permissions, auditing, encryption at rest, and a deletion workflow. `threaddump` can expose class names, threads, stack frames, and runtime context; restrict it similarly.

Never place a heapdump into a static directory or public object storage after capturing it just for quick sharing. Never expose this endpoint behind a CDN merely because it is locked with a weak Basic password.

### 11.3. logfile, httpexchanges, and metrics

Log files can contain URIs, headers, request IDs, emails, exceptions, and past accidentally logged data. `httpexchanges` with a configured repository can record HTTP metadata; control retention and sensitive fields. Metrics should use low-cardinality labels such as route template, status code, and service; **never** put raw user IDs, access tokens, secret-bearing URLs, or emails into metric tags. Observability systems themselves require access control, auditing, and retention policies.

### 11.4. loggers and State-Changing Operations

Actuator `loggers` supports changing logging levels when the endpoint/operation is exposed; `shutdown` is disabled by default. Carelessly raising to DEBUG/TRACE can fill disks and print sensitive info. Some Actuator operations use `POST`/`PUT`/`DELETE`, while Spring Security enables CSRF protection by default for unsafe methods. A user with `ROLE_OPS` lacking a CSRF token can still receive 403. **Never disable CSRF globally**; design narrow exceptions for machine clients already backed by proper authentication/mTLS/network controls if business needs truly require it.

## 12. 401, 403, 404, and 503 Are Not Interchangeable

| Code | Typical Scenario | How to Distinguish |
| --- | --- | --- |
| 200 | Public static, health UP, authorized admin/metrics | Check both content and headers |
| 401 | Unauthenticated or invalid Basic credentials | `WWW-Authenticate` or entry point |
| 403 | Authenticated without required role, or CSRF blocked | Inspect security/CSRF logs |
| 404 | Unexposed route or nonexistent resource | Call with authorized credentials, check exposure list |
| 405 | Path has a handler yet method is unsupported | Check HTTP method mappings |
| 503 | Health DOWN/unready per status mapping | Check status/health group/traffic readiness |

A URL with no handler can still return 401 from Spring Security before controller lookup if fallback `authenticated()` matches first. Thus never use 401 as proof an endpoint is exposed. And never fix a 404 with `permitAll`, since authorization does not create new files or routes.

## 13. Static CDNs, Reverse Proxies, and Security Boundaries

If browsers fetch `/assets/app.js` from a CDN cache instead of the JVM, Spring Security **does not run** on that request. For public CSS/JS, that is normal and great for performance. For private resources:

- Object storage buckets must be private; never rely on obscure URLs.
- Use short-lived signed URLs or a download controller enforcing permission/object-level checks.
- CDN caching must never share User A's response with User B.
- NGINX/ingress must not route public traffic to the management port unintentionally.
- Never trust client-supplied `X-Forwarded-For` to grant OPS/internal access.

Protect management in layers: unexposed by default, network-restricted, authenticated/authorized, and least-data responses. In a multi-pod setup, health probes typically come from internal kubelets and metrics scrapers from a monitoring namespace; that is very different from opening `/actuator/**` with `permitAll` to the entire internet.

## 14. Error Pages, Sessions, CSRF, and CORS

### 14.1. Error Responses Can Also Leak Information

`server.error.include-stacktrace=always` or custom exception handlers returning raw exception messages can leak package names, database paths, and secrets in messages. Use `server.error.include-stacktrace=never` and send only safe messages to clients; keep details in secured logs.

When `/error` is blocked by a security fallback or dispatcher types differ, you can see 401/redirect loops instead of the original error. Inspect `DispatcherType.ERROR`/`FORWARD`, Spring Security filters, and exception handling for your exact version. Never open `/**` just to fix an error page.

### 14.2. Cookies/Sessions Are Not an Authorization System

With form login/sessions, an authenticated cookie may exist yet the user still must hold resource permissions. In the Basic auth demo, credentials only prove identity; `USER` cannot read admin routes. For tenant-scoped PDF downloads, enforce owner/tenant checks in the service regardless of login state.

### 14.3. CSRF and Admin Writes

A POST changing a log level or performing an admin action can be blocked by CSRF even with the right role; this protects browser-authenticated flows. When using non-browser machine credentials, align CSRF with your threat model and limit exceptions to the relevant API rather than disabling protection app-wide without cause.

### 14.4. CORS Does Not Lock Down Endpoints

CORS determines whether browser JavaScript from another origin may read responses. `curl`, Prometheus, and server-to-server clients **are not restricted by CORS**. Actuator CORS is disabled by default unless configured; add allowed origins only when an admin frontend genuinely needs it alongside proper permissions and credentials policies.

## 15. WebFlux Differs from Servlet APIs

The main sample uses Spring MVC/Servlet `HttpSecurity` and imports `PathRequest` from the `servlet` package. With Spring WebFlux, use `ServerHttpSecurity`, `SecurityWebFilterChain`, and reactive matchers:

```java
import org.springframework.boot.autoconfigure.security.reactive.PathRequest;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

// Snippet inside a @Configuration bean for a WebFlux project:
@Bean
SecurityWebFilterChain reactiveSecurity(ServerHttpSecurity http) {
    return http.authorizeExchange(exchanges -> exchanges
            .matchers(PathRequest.toStaticResources().atCommonLocations())
                .permitAll()
            .pathMatchers("/admin/**").hasRole("ADMIN")
            .anyExchange().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

This is a **snippet** needing `@Bean` imported inside a `spring-boot-starter-webflux` project—**not a standalone class**, and never copied into an MVC app. Reactive Actuator has `EndpointRequest` in a different package with `ServerWebExchange` matchers; protect Actuator accordingly. Do not include both Web and WebFlux starters assuming controllers will default to reactive.

## 16. Common Pitfalls and Fixes

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Login page CSS returns 401 | Static paths not `permitAll` | Use `PathRequest` or exact paths |
| CSS lacks security headers | Request skipped via `web.ignoring` | Keep inside filter chain with `permitAll` |
| Regular user can read admin | Broad rule first, unmatched chain, or edge bypass | Fix `@Order`/matchers, inspect proxy |
| Metrics become public after refactoring | Custom `SecurityFilterChain` backed off Boot actuator security | Write a dedicated Actuator chain |
| Metrics returns 404 | Missing exposure or dependency | Check `include` and starter |
| Metrics returns 401 | Unauthenticated | Use valid user/machine credentials |
| Metrics returns 403 | Missing `ROLE_OPS` or another policy | Check authorities and security logs |
| Health returns 401 making pod unready | Probe not permitted or wrong port | Permit exact health paths on trusted network |
| Health leaks DB/cache | `show-details=always` or overly broad group config | Keep `never` or appropriate roles |
| `env` leaks secrets | Overly permissive exposure/`show-values` | Unexpose, sanitize, handle incident |
| `heapdump` downloadable from public internet | Open management route or CDN/storage | Disable exposure, block at network |
| POST loggers returns 403 despite OPS role | Missing CSRF | Design token or appropriate machine auth |
| Admin data stays cached after logout | Wrong `Cache-Control`/CDN policy | Use `no-store`/`private`, add cache tests |
| Separate management port still scanned | Listening publicly / open firewall | Restrict listener, NetworkPolicy, mTLS |
| Nonexistent endpoint returns 401 to anonymous | Security blocked before MVC routing | Verify with authenticated test and exposure |
| Probes on management port UP while app port dead | Two web servers not sharing serving path | Main-port additional probes or separate checks |

## 17. Production Test Suite You Should Have

1. **Anonymous** GET public CSS/JS: 200 response, right content-type, and security headers.
2. **Anonymous** GET account/admin/metrics: designed authentication challenge or status.
3. **Authenticated user** GET account: 200; GET admin/diagnostic/metrics: 403.
4. **OPS/ADMIN** GET role-matched endpoints: 200; wrong roles: 403.
5. **Unexposed endpoints**: verify 404 when called with privileged credentials, rather than mistaking fallback 401.
6. **Health**: minimal summary; liveness/readiness respond properly across startup, shutdown, and dependency failure.
7. **CSRF**: unsafe admin operations cannot execute without tokens in browser flows.
8. **Private static files**: user A cannot read B's files via CDN, object storage, or guessed URLs.
9. **Proxy/Ingress**: public internet cannot reach the management port or internal diagnostic paths unintentionally.
10. **Deployment**: changes to Spring Boot/Security versions, actuator exposure, static mappings, or context paths do not open extra URLs.
11. **Observability**: 401/403 anomalies, endpoint access logs, and audits never record raw tokens/secrets.
12. **Regression**: automated tests for chain order, role mapping, health probe access, and exposure lists.

Beyond MockMvc, run HTTP integration tests against real ports and test behind reverse proxies/CDNs. JVM tests alone cannot catch every bucket policy, ingress, or NetworkPolicy misconfiguration.

## 18. Practice Exercises

**1.** `/css/site.css` is public; use `web.ignoring` or `permitAll`?  
**Answer:** Prefer `permitAll` to keep security filters/headers intact while ensuring the resource contains no private data.

**2.** With a custom `SecurityFilterChain` for `/admin/**`, will Actuator still be fully auto-protected as before?  
**Answer:** No. A custom chain causes Actuator web-security auto-configuration to back off. You need policies/chains covering actuator endpoints.

**3.** Does `management.endpoints.web.exposure.include=health,metrics` let anyone read metrics?  
**Answer:** No. Exposure only creates HTTP availability; authentication/authorization still govern access.

**4.** Health is `permitAll` with `show-details=always`; what is the risk?  
**Answer:** Dependency/component status can leak to anonymous callers; use minimal summaries or explicit role policies.

**5.** Why doesn't `hasRole("OPS")` match a user whose only authority is `OPS`?  
**Answer:** The default rule looks for `ROLE_OPS`. Keep role/authority conventions consistent.

**6.** A logged-in user gets 403 on a POST changing log levels. Is it definitely a missing role?  
**Answer:** No. It may be a missing CSRF token or another policy; check security logs and the request.

**7.** Why can an unexposed `/actuator/env` still return 401 to anonymous callers?  
**Answer:** A security fallback can intercept before route lookup. Test with valid credentials to distinguish route 404 from auth 401.

**8.** A CDN serves `/private/report.csv` directly. Is a Spring MVC rule `/private/** authenticated()` enough?  
**Answer:** No, the CDN does not go through Spring Security; enforce protection at the edge/storage or route through an authenticated controller.

**9.** Liveness depends on the database. A DB outage restarts all pods in a cascade. What is the issue?  
**Answer:** Liveness depends on an external system; distinguish readiness and prevent cascading restarts.

**10.** Does setting `management.server.port=8081` automatically block Actuator from the internet?  
**Answer:** No. You also need proper bind addresses, firewall/NetworkPolicy, identity, and ingress routing checks.

## 19. Pre-Merge Checklist

- [ ] Categorized routes: public static, user, admin, OPS, probes, and sensitive diagnostics.
- [ ] Static resources use `permitAll`, never removed from the entire `SecurityFilterChain` without special justification.
- [ ] No credentials, dumps, backups, or user data placed in public static directories.
- [ ] Specific rules precede fallbacks; no `/** permitAll` accidentally shadows admin rules.
- [ ] Multiple `SecurityFilterChain` beans have clear order and matchers, all tested.
- [ ] Custom security does not omit Actuator or main application routes.
- [ ] Minimal exposure list, separate JMX exposure, never `include=*` in production.
- [ ] Health exposes only necessary data; details/roles and probe paths verified.
- [ ] Management port resides on an appropriate network, never exposed publicly by default.
- [ ] Diagnostics never leak env values, user/session tokens, heap dumps, or logs.
- [ ] CSRF on unsafe admin methods preserved or replaced according to threat model.
- [ ] Both user-level and object-level authorization enforced, not login alone.
- [ ] Caching on admin/user responses configured to prevent sharing sensitive data.
- [ ] 200/401/403/404 matrix verified via curl and automated tests.
- [ ] Proxies, CDNs, ingress, object storage, and monitoring networks tested separately.
- [ ] Logging/auditing enabled without storing unnecessary secrets or tokens.

## Official References

- [Spring Boot 3.3 — Spring Security](https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html)
- [Spring Boot 3.3 — Actuator Endpoints, Exposure, Security, Health](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html)
- [Spring Boot 3.3 — Monitoring/Management Over HTTP](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html)
- [Spring Boot 3.3 — Servlet Static Resources](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html)
- [Spring Boot 3.3 — Servlet PathRequest](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/security/servlet/PathRequest.html)
- [Spring Boot 3.3 — StaticResourceRequest](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/security/servlet/StaticResourceRequest.html)
- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Boot 3.3 — Observability](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html)

**Key takeaway:** static resources should be **public within exact bounds**; management endpoints need **verified identity, roles, and business permissions**; diagnostic information requires **restricted exposure, network controls, and sanitized output**. All of these layers must be configured and tested together; an “obscure URL” or generic `authenticated()` rule is not enough to protect a production runtime.