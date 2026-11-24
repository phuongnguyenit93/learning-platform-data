# Checking Static Resources, Error Endpoints, and Actuator in Access Policies

> **Module:** Spring Security - servlet. **Group:** HTTP Authorization. Implementation example for Java 17+, Spring Boot 3.x, Spring Security 6.x, and Servlet/Spring MVC. This lesson focuses on **designing and testing access policies** for three surfaces that are very easy to misconfigure: static resources, error-handling endpoints, and Actuator.

## 1. Why Do These Three URL Groups Need Separate Verification?

A web application has business endpoints like `/account`, `/orders`, `/admin/reports`. Yet when Spring Security is added, business controllers are not the only things affected by `SecurityFilterChain`:

1. **Static resources** such as CSS, JavaScript, favicon, images, or webjars usually must be loaded by unauthenticated users so the login page renders properly. Permitting too broadly or using `web.ignoring()` unnecessarily can bypass security filters and headers.
2. **Error endpoints** such as `/error` may be invoked by the Servlet container using **`DispatcherType.ERROR`** after an error occurs on the original request. If authorization runs again on the error dispatch and is not handled, the app can turn a 404/500 error into a login redirect or cause error-handling loops. Conversely, opening all error handling while returning stack traces, session data, or request details is dangerous.
3. **Spring Boot Actuator** provides operational endpoints such as `/actuator/health`, `/actuator/info`, `/actuator/metrics`, and more sensitive endpoints. Deciding which endpoints are **exposed** differs from deciding **who can access** exposed endpoints.

These three surfaces cannot be solved with a single `requestMatchers("/**").permitAll()`, nor should every resource redirect to the login page by default. A clearly ordered policy and proper tests for both anonymous and authenticated states are required.

**Overarching principle:** classify URLs by purpose, restrict public access, apply the right authorization to each surface, and verify that permitting a request does not expose sensitive data.

## 2. HTTP Processing Chain: Matchers Selecting Chains and Matchers Checking Permissions

In Spring Security Servlet, `FilterChainProxy` selects a `SecurityFilterChain` matching the request, then filters in that chain perform their work, where authorization is typically enforced by `AuthorizationFilter`.

```text
Browser / API client / monitoring agent
                 |
                 v
        Servlet container
                 |
                 v
   DelegatingFilterProxy ("springSecurityFilterChain")
                 |
                 v
   FilterChainProxy selects SecurityFilterChain
                 |
                 +--> CsrfFilter (when applicable)
                 +--> Authentication filters
                 +--> AuthorizationFilter
                           |
                 Order of authorization rules
                           |
          +----------------+-----------------+
          |                |                 |
      static CSS/JS    ERROR dispatch   Actuator health/metrics
          |                |                 |
      permitAll?       permitAll?       public or OPS role?
          |                |                 |
          +----------------+-----------------+
                           |
                      MVC / Actuator
                           |
                  status/body/headers
```

Two concepts are very easy to confuse:

- **`http.securityMatcher(...)`**: restricts the **entire filter chain**. For a URL outside the chain, none of that chain's rules or security filters apply.
- **`authorizeHttpRequests(...requestMatchers(...))`**: defines the policy for requests **that entered the chain**. These rules are typically evaluated in declaration order, with the first matching rule deciding access.

Therefore place specific rules before general rules, for example:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public/**").permitAll()
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated()
)
```

This is only a fragment, not a standalone application. If `.anyRequest().authenticated()` is moved ahead of the admin rule, later rules may fail to register or never execute; the policy becomes wrong or configuration is rejected. When creating multiple chains with `@Order`, check which chain is selected first, because a high-priority catch-all chain can block dedicated chains for Actuator or web.

## 3. Static Resources: What Should Be Public and What Should Be Protected?

Example Spring Boot project layout:

```text
src/main/resources/
└── static/
    ├── css/site.css
    ├── js/app.js
    ├── images/logo.svg
    └── favicon.ico
```

With standard MVC configuration, `classpath:/static/css/site.css` is served at URL **`/css/site.css`**, not `/static/css/site.css`. Other default locations may include `/public`, `/resources`, `/META-INF/resources`, and WebJars depending on libraries/configuration. Read the **actual public URL**, not merely the folder name in the source tree.

Common categories:

| Category | Usually Reasonable Policy | Risk If Done Wrong |
| --- | --- | --- |
| CSS/JS needed to render login | `permitAll()` | Anonymous users redirected, login loses styling or loops |
| Favicon, logo, public marketing images | `permitAll()` | Unnecessary 302/401 responses |
| `/webjars/**` for public pages | `permitAll()` when actually used | Blocks UI libraries or exposes too many assets unintentionally |
| JavaScript embedding API secrets | **Must not be placed in public static assets** | Anyone can download the file; URL authorization cannot fix bundled secrets |
| User-exported report files | Endpoint/controller + owner/tenant authorization | `permitAll("/downloads/**")` can leak data |
| Personal attachments stored under `/static/private/` | Should not be placed in public static directories | Easily exposed by broad public matchers or CDN/caching |
| User-uploaded files | Object storage or handler checking permissions/file types | XSS/content-sniffing/malware if served with wrong Content-Type |

**Important:** never conclude a file is safe from its URL path alone. Only assets classified as public should get `permitAll`. For user-specific files, store them outside public static-resource locations and serve them via a permission-checking controller/resource handler or signed URLs with clear policies.

### 3.1. `PathRequest.toStaticResources().atCommonLocations()`

Spring Boot offers a helper for common static resource locations:

```java
import org.springframework.boot.autoconfigure.security.servlet.PathRequest;

// Used inside HttpSecurity's authorizeHttpRequests.
.requestMatchers(PathRequest.toStaticResources().atCommonLocations())
    .permitAll()
```

This helper avoids manually writing an error-prone list like `/css/**`, `/js/**`, `/images/**`, `/webjars/**`. Yet it **does not automatically detect every custom directory**. When changing resource handler locations, static path patterns, or placing assets under other URLs, re-verify the actual matcher and add narrow rules as needed.

For instance, if `/assets/vendor/theme.css` is served by a custom resource handler, do not assume the helper will match it. Likewise, never use `permitAll("/**/*.css")` by file extension if controllers have dynamic resources or sensitive URLs that could accidentally end in `.css`.

### 3.2. `permitAll()` vs. `web.ignoring()`

These two approaches **are not equivalent**:

```java
// Generally preferred:
.requestMatchers(PathRequest.toStaticResources().atCommonLocations())
    .permitAll()
```

```java
// Example configuration bypassing the chain; requires careful consideration:
@Bean
WebSecurityCustomizer webSecurityCustomizer() {
    return web -> web.ignoring().requestMatchers("/css/**");
}
```

The second snippet is a separate fragment requiring `WebSecurityCustomizer` import, shown solely to illustrate the difference; **do not add it to the main example below**.

- With `permitAll()`, requests **still pass through the Spring Security filter chain**, so security headers, corresponding policies, and filter mechanisms still operate. The authorization rule ultimately permits the request.
- With `web.ignoring()`, matching requests usually **skip the Spring Security chain**, meaning chain-provided protections do not run on that path. Never use it merely because static resources "need no permission checks".
- `permitAll()` in Spring Security 6 is optimized to avoid fetching `Authentication` on the permit branch, reducing performance concerns compared to skipping the chain.
- A missing static resource can still return **404**, yet if the rule denies anonymous users, the request may be blocked/redirected **before MVC determines the file does not exist**.

Apply `permitAll` for public resources; use ignoring only when explicitly required, understanding the lost filters/headers and confirming with tests.

## 4. Favicon Paths, Login Pages, and Blocked Assets

A common situation: `GET /login` works, yet CSS fails to load.

```text
GET /login                 -> HTTP 200 HTML
GET /css/site.css          -> HTTP 302 Location: /login
GET /js/app.js             -> HTTP 302 Location: /login
GET /favicon.ico           -> HTTP 302 Location: /login
```

Visually, the browser looks unstyled or JS fails to run, while the backend reports no clear security error. The fix is **not** `anyRequest().permitAll()`. Permit specifically the assets needed by unauthenticated pages.

If a custom login page has assets under `/login-assets/**`, add a dedicated rule for that path. When registering a login URL like `/login` or `/auth/signin`, distinguish it from CSS/JS paths; POST login handling, CSRF, and GET login are separate mechanics.

For `/favicon.ico`, it may be served from a location or pattern outside the common static helper; when needed, add a specific matcher `.requestMatchers("/favicon.ico").permitAll()`. If the file does not exist, 404 is expected instead of 302, which should be verified.

## 5. Error Endpoints: Distinguishing the `/error` URL from `DispatcherType.ERROR`

Spring Boot has an HTTP error-handling mechanism, usually using the `/error` endpoint handled by `BasicErrorController` or a custom `ErrorController`. However, an error dispatch **is not simply an ordinary GET with path `/error`**.

Servlets define dispatch types such as:

- `DispatcherType.REQUEST`: normal request from client.
- `DispatcherType.ERROR`: container dispatch during error handling.
- `DispatcherType.FORWARD`: server-side forward to another resource.
- `DispatcherType.INCLUDE`, `ASYNC`: other dispatch cases to understand if used by the application.

In Spring Security 6, authorization can be evaluated on eligible dispatches, not just the original request. If a request causing an error is redispatched by the container to `/error`, the error dispatch can be blocked by authorization rules because `SecurityContext` is not considered authenticated on that dispatch or the default matcher has not permitted it.

To handle per policy:

```java
import jakarta.servlet.DispatcherType;

.authorizeHttpRequests(auth -> auth
    .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
    // Other rules.
)
```

**Meaning:** server-generated ERROR dispatches are allowed through authorization to render/return the error response; it does not make the initial **REQUEST** public. A browser cannot simply send a custom HTTP header to turn `HttpServletRequest.getDispatcherType()` into `ERROR`: the dispatch type is decided by the Servlet container.

### 5.1. Should `/error` Also Be Permitted by Path?

In some applications, you may see:

```java
.requestMatchers("/error").permitAll()
```

This rule allows the `/error` path on normal matching requests as well, whereas `dispatcherTypeMatchers(ERROR)` targets the **dispatch type**. The two rules have different scopes. Choose based on your error architecture and how the framework forwards/dispatches errors. The full example below uses both to demonstrate the semantics and avoid loops on the default error endpoint.

However, permitting access to the error page **does not mean** exposing:

- Stack traces, exception classes, or sensitive message content.
- `Authorization` headers, cookies, session IDs, or CSRF tokens.
- SQL exceptions or backend configuration.
- Cross-tenant domain details or private payloads in error attributes.

A public error endpoint should return minimal information, the appropriate status, and a redacted correlation ID.

### 5.2. Should `DispatcherType.FORWARD` Be Permitted?

Some apps use `RequestDispatcher.forward(...)` or view resolvers to internally forward to JSPs/templates. Then `DispatcherType.FORWARD` may need separate handling. You might consider:

```java
.dispatcherTypeMatchers(
    DispatcherType.ERROR, DispatcherType.FORWARD).permitAll()
```

This is a **policy-dependent fragment**, not a recommendation to open FORWARD unconditionally. If application code can forward to a sensitive controller/resource from a public request, permitting all FORWARDs can drop authorization at the target dispatch. Verify the trustworthiness of forward origins and original request rules. The main example only automatically permits `ERROR`, without broadening `FORWARD`.

### 5.3. Distinguishing "Processing Error" from "Insufficient Permission"

An anonymous request to `/admin/reports` is normally blocked by Spring Security and routed to `AuthenticationEntryPoint` (login redirect or 401), **not necessarily creating a Servlet ERROR dispatch**. An authenticated user lacking a role may get 403 from `AccessDeniedHandler`; not every 403 goes through `/error` either.

Therefore never take a 302 test status and conclude `/error` is misprotected. To test error dispatches genuinely, trigger an error flow in a **Servlet container**, or in unit/MockMvc tests check specifically that a request with `DispatcherType.ERROR` matches the authorization rule.

## 6. Testing Error Endpoints Safely

A Boot app can configure minimal error bodies in production:

```yaml
server:
  error:
    include-message: never
    include-stacktrace: never
    include-binding-errors: never
```

These settings reduce diagnostic details in responses. They **do not replace** data security in exception handlers, access logs, reverse proxies, or custom error controllers. For authentication/authorization errors, keep `401`/`403` and minimal bodies per API contract; never turn all errors into HTTP 200 with one HTML page.

Useful tests:

1. Anonymous GET to a non-existent URL under public static -> **no login redirect**, typically 404.
2. Anonymous GET to a private URL -> **must not return private data**, may redirect to login or return 401.
3. Error dispatch from a failing controller -> appropriate 404/500 status/response, no login redirect loop.
4. Direct REQUEST to `/error` -> defined behavior without leaking stack traces.
5. Request from a user lacking a role -> proper 403/authorization handling, no admin data leak.
6. No internal info returned to anonymous users in JSON/HTML error bodies.

A `MockMvc` test with `request.setDispatcherType(ERROR)` verifies the dispatcher rule, yet **does not fully simulate** a real container redispatching after an exception. Combine both `MockMvc` and HTTP integration tests on a real web server.

## 7. Actuator: Exposure, Authentication, and Authorization Are Three Separate Layers

Spring Boot Actuator provides endpoints supporting application observability and management. They are an important HTTP surface, not "a group of internal-only URLs" by name.

Three decisions to separate:

1. **Does the endpoint exist and is it exposed over the web?** Decided by the `spring-boot-starter-actuator` dependency, endpoint enablement, and `management.endpoints.web.exposure.*` (plus other availability options depending on Spring Boot version).
2. **Which endpoints may be accessed without logging in?** For example, health for load balancers.
3. **Who may view the remaining exposed endpoints?** Operations role `OPS`, admin, monitoring identity, or service-to-service security; add network controls if data is sensitive.

A `requestMatchers("/actuator/**").permitAll()` rule is very dangerous if someone later exposes `env`, `beans`, `configprops`, `heapdump`, `threaddump`, `loggers`, or mutating endpoints. Not every endpoint leaks secrets in every configuration, yet **never open all of Actuator just to make health checks public**.

### 7.1. Use `EndpointRequest` Instead of Hardcoding Every Path

Spring Boot Actuator provides a matcher:

```java
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;

// Example fragment inside authorizeHttpRequests:
.requestMatchers(EndpointRequest.to("health")).permitAll()
.requestMatchers(EndpointRequest.toAnyEndpoint()).hasRole("OPS")
```

`EndpointRequest` knows the configured Actuator endpoints in the application context and depends less on the default `/actuator` path. This helps when changing `management.endpoints.web.base-path` or endpoint mappings. **Rule order matters**: public health must precede `toAnyEndpoint()`, or health may require the `OPS` role.

Do not confuse:

- `EndpointRequest.to("health")`: matcher for the Actuator health endpoint (including related paths per version/config).
- `EndpointRequest.toAnyEndpoint()`: matches enabled/exposed Actuator endpoints in context; **does not itself expose** unenabled/unexposed endpoints.
- `management.endpoints.web.exposure.include`: specifies which endpoints are exposed over the web; it does **not** mean anyone is allowed to view them.

### 7.2. Choose Minimal Exposure

For the demo, we can explicitly expose:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
  endpoint:
    health:
      show-details: never
```

This is an example for a simple application. `health` can be public so load balancers see overall status; `info` and `metrics` require `ROLE_OPS`. In production, health details can expose database/queue/disk info, so `show-details`, health groups, probes, and internal/external endpoints must be designed per audience. `info` may be empty if no contributors are configured; that does not mean it is automatically safe across all deployments.

**Never expose `*\`** (all actuator endpoints) merely for observability convenience; create an allowlist of genuinely needed endpoints, add authorization, and restrict network access.

### 7.3. Actuator Differs from Controllers by Path

A self-written `@GetMapping("/actuator/custom")` controller does not automatically become an Actuator endpoint recognized by `EndpointRequest.toAnyEndpoint()`. Likewise, `/actuator/does-not-exist` may not match `EndpointRequest` and fall through to a catch-all rule. If you add controllers under an admin prefix, add dedicated policies and tests rather than relying solely on URL prefix or `EndpointRequest`.

## 8. When Actuator Runs on a Separate Management Port/Context

Spring Boot can use a management port distinct from the application port:

```yaml
management:
  server:
    port: 9090
```

In that case management endpoints can be served in a different **management server/application context**; the security chain applied to the application port must not automatically be assumed to protect Actuator on port 9090. Verify filter chains/auto-config and security rules in **both contexts**. Set up firewalls, private networks, mTLS, or service-to-service authentication per operational requirements.

Examples and tests below assume **Actuator runs on the same application port/context** (the default when `management.server.port` is unset). Do not copy those MockMvc results to prove a separate management port is secure.

When `management.endpoints.web.base-path=/manage`, URLs change from `/actuator/health` to `/manage/health`; `EndpointRequest` adapts better than hardcoding `/actuator/**`, though integration tests must still verify exact URLs, health groups, and scopes.

## 9. Sample Policy Table Before Writing Code

We want:

- CSS/JS/image assets and favicon public.
- Public page `/public` public.
- Error dispatches allowed to render errors; responses do not leak exception details.
- Actuator health public, returning only overall status.
- Actuator info/metrics require `ROLE_OPS`.
- `/admin/**` requires `ROLE_ADMIN`.
- `/account` and unclassified business URLs require login.
- Default form login serves browsers; CSRF stays enabled.

| Request | Anonymous | Regular User | OPS | ADMIN |
| --- | --- | --- | --- | --- |
| GET /css/site.css | 200 | 200 | 200 | 200 |
| GET /js/app.js | 200 | 200 | 200 | 200 |
| GET /public | 200 | 200 | 200 | 200 |
| GET /actuator/health | 200 | 200 | 200 | 200 |
| GET /actuator/info | Redirect to login | 403 | 200 | 403 if ADMIN lacks OPS |
| GET /actuator/metrics | Redirect to login | 403 | 200 | 403 if ADMIN lacks OPS |
| GET /account | Redirect to login | 200 | 200 | 200 |
| GET /admin/report | Redirect to login | 403 | 403 if OPS lacks ADMIN | 200 |
| GET /dispatch-probe, normal REQUEST | Redirect to login | 200 | 200 | 200 |
| Internal ERROR dispatch to /dispatch-probe | Passes authorization | Passes | Passes | Passes |
| GET /css/missing.css | Typically 404 if path public | Typically 404 | Typically 404 | Typically 404 |

**Note:** the table separates **independent role scopes**, without assuming `ADMIN` always includes `OPS`. `hasRole("OPS")` checks `ROLE_OPS`; `hasRole("ADMIN")` checks `ROLE_ADMIN` under the default role prefix. Actual HTTP codes and redirects may vary by authentication entry point and custom handlers.

## 10. Example: Spring Boot 3.x / Spring Security 6.x / Java 17+

This is a learning example running on Servlet MVC, one shared `SecurityFilterChain`, with Actuator on the same port. To reproduce, create a Spring Boot 3.x Gradle project with Java 17, add the dependencies, and place the files at their exact paths.

### 10.1. Gradle Dependencies

In a project with the Spring Boot Gradle plugin and dependency management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

### 10.2. Main Application + Security Config + Controller

File `src/main/java/example/accesspolicy/AccessPolicyApplication.java`:

```java
package example.accesspolicy;

import jakarta.servlet.DispatcherType;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.boot.autoconfigure.security.servlet.PathRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class AccessPolicyApplication {

    public static void main(String[] args) {
        SpringApplication.run(AccessPolicyApplication.class, args);
    }
}

@Configuration
class AccessSecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                // Servlet container dispatches internally when handling errors.
                .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()

                // Only common static locations classified as public.
                .requestMatchers(
                    PathRequest.toStaticResources().atCommonLocations()
                ).permitAll()
                .requestMatchers("/favicon.ico", "/public", "/error")
                    .permitAll()

                // Actuator exposure and authorization are 2 separate layers.
                .requestMatchers(EndpointRequest.to("health")).permitAll()
                .requestMatchers(EndpointRequest.toAnyEndpoint())
                    .hasRole("OPS")

                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            // Do not disable CSRF; application has browser form login.
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails viewer = User.withUsername("viewer")
            .password(encoder.encode("viewer-pass"))
            .roles("USER")
            .build();

        UserDetails operator = User.withUsername("operator")
            .password(encoder.encode("operator-pass"))
            .roles("OPS")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-pass"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(viewer, operator, admin);
    }
}

@RestController
class AccessController {

    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/account")
    String account(Authentication authentication) {
        return "hello " + authentication.getName();
    }

    @GetMapping("/admin/report")
    String adminReport() {
        return "admin report";
    }

    @GetMapping("/dispatch-probe")
    String dispatchProbe() {
        return "dispatch-probe";
    }
}
```

**This is a valid Java 17 file:** only `AccessPolicyApplication` is public, while the other two top-level classes are package-private inside the component-scanned package. Imports `PathRequest`/`EndpointRequest` belong to **Spring Boot**, `DispatcherType` belongs to **`jakarta.servlet`**, and `SecurityFilterChain` belongs to Spring Security.

**Details that determine the safety of the code:**

- The `DispatcherType.ERROR` rule precedes `anyRequest().authenticated()`, so internal errors can render responses without redirecting to login on re-authorization.
- `PathRequest` permits common locations; it does not open all of `/**`.
- `/error` is permitted to prevent error rendering from hitting an authentication challenge in the example; production must sanitize error responses.
- `EndpointRequest.to("health")` comes **before** `toAnyEndpoint()`: health is public, while other endpoints require `ROLE_OPS`.
- `/admin/**` requires `ROLE_ADMIN` separately, not letting `OPS` exceed privileges.
- `anyRequest().authenticated()` is the catch-all; for APIs requiring strict zero trust, you can choose `denyAll()` and explicitly allowlist every intended route, in which case `/account` must be declared explicitly.
- `formLogin` is just basic authentication for studying authorization. If production requires MFA login, JWT, or mTLS for Actuator, design them additionally per threat model.
- Passwords and users are strictly for local demos; production must use a secret store, identity provider, and HTTPS.

### 10.3. Actuator and Error Response Configuration

File `src/main/resources/application.yml`:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
  endpoint:
    health:
      show-details: never

server:
  error:
    include-message: never
    include-stacktrace: never
    include-binding-errors: never
```

For the health-check demo, `management.server.port` is omitted: Actuator shares the app port. `metrics` is exposed **intentionally** and the security rule requires `ROLE_OPS`. Never enable `management.endpoints.web.exposure.include: "*"` in real applications without a very tight design. `show-details: never` restricts health details for all users in the example.

### 10.4. Static Resources to Create

File `src/main/resources/static/css/site.css`:

```css
body {
    color: #123456;
    font-family: sans-serif;
}
```

File `src/main/resources/static/js/app.js`:

```javascript
window.accessPolicyDemoReady = true;
```

File `src/main/resources/static/images/mark.svg`:

```xml
<svg xmlns="http://www.w3.org/2000/svg"
     width="40" height="40" viewBox="0 0 40 40">
  <circle cx="20" cy="20" r="16" fill="#2563eb"/>
</svg>
```

You can create `src/main/resources/static/favicon.ico` if you have a real favicon. A favicon file is not required to test CSS/JS; however, `/favicon.ico` is permitted publicly and can still return 404 when the file is absent.

### 10.5. Running and Observing

From the project root with the Gradle wrapper:

```bash
./gradlew bootRun
```

Windows PowerShell: `./gradlew.bat bootRun`.

Once the app runs on `localhost:8080`:

```bash
curl -i http://localhost:8080/css/site.css
curl -i http://localhost:8080/js/app.js
curl -i http://localhost:8080/actuator/health
curl -i -H "Accept: text/html" http://localhost:8080/account
curl -i -H "Accept: text/html" http://localhost:8080/actuator/metrics
```

**Expected** results:

- CSS, JS: HTTP 200 when files exist.
- Actuator health: HTTP 200, JSON containing general status like `{"status":"UP"}` when the demo operates normally.
- Anonymous `/account`: typically redirects to the login page with `formLogin`.
- Anonymous `/actuator/metrics`: does not return the metrics list; routed to login/entry point per configuration.
- Logged-in operator with `ROLE_OPS` can access `/actuator/metrics`; viewer lacking the role must be denied.

This is behavior **expected from the code**, not output captured from a real execution. `curl` does not automatically hold a browser login session. You cannot simply add Basic credentials `curl -u` to this demo expecting HTTP Basic to work, because the example **only enables `formLogin`**, not `httpBasic`.

## 11. Testing with MockMvc: Static Resources Must Be Public While Admin/Metrics Stay Closed

Spring Boot Test and Spring Security Test let you test authorization directly inside the Servlet filter chain.

Create `src/test/java/example/accesspolicy/AccessPolicySecurityTest.java`:

```java
package example.accesspolicy;

import jakarta.servlet.DispatcherType;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AccessPolicySecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void cssIsPublicAndServedAsRealStaticResource() throws Exception {
        mvc.perform(get("/css/site.css"))
            .andExpect(status().isOk())
            .andExpect(content().string(containsString("color:")));
    }

    @Test
    void javascriptIsPublic() throws Exception {
        mvc.perform(get("/js/app.js"))
            .andExpect(status().isOk())
            .andExpect(content().string(
                containsString("accessPolicyDemoReady")));
    }

    @Test
    void imageIsPublic() throws Exception {
        mvc.perform(get("/images/mark.svg"))
            .andExpect(status().isOk())
            .andExpect(content().string(containsString("<circle")));
    }

    @Test
    void publicControllerIsPublic() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void healthIsPublicButShowsOnlyBasicStatus() throws Exception {
        mvc.perform(get("/actuator/health"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").exists());
    }

    @Test
    void anonymousCannotSeeActuatorMetrics() throws Exception {
        mvc.perform(get("/actuator/metrics")
                .accept(MediaType.TEXT_HTML))
            .andExpect(status().is3xxRedirection())
            .andExpect(header().string(
                "Location", containsString("/login")));
    }

    @Test
    void normalUserCannotSeeActuatorMetrics() throws Exception {
        mvc.perform(get("/actuator/metrics")
                .with(user("viewer").roles("USER")))
            .andExpect(status().isForbidden());
    }

    @Test
    void opsUserCanSeeActuatorMetrics() throws Exception {
        mvc.perform(get("/actuator/metrics")
                .with(user("operator").roles("OPS")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.names").exists());
    }

    @Test
    void infoEndpointAlsoRequiresOps() throws Exception {
        mvc.perform(get("/actuator/info")
                .with(user("viewer").roles("USER")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/actuator/info")
                .with(user("operator").roles("OPS")))
            .andExpect(status().isOk());
    }

    @Test
    void adminPageRequiresDifferentRole() throws Exception {
        mvc.perform(get("/admin/report")
                .with(user("operator").roles("OPS")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/admin/report")
                .with(user("admin").roles("ADMIN")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin report"));
    }

    @Test
    void anonymousBusinessEndpointRedirectsToLogin() throws Exception {
        mvc.perform(get("/account").accept(MediaType.TEXT_HTML))
            .andExpect(status().is3xxRedirection())
            .andExpect(header().string(
                "Location", containsString("/login")));
    }

    @Test
    void authenticatedUserCanSeeAccount() throws Exception {
        mvc.perform(get("/account")
                .with(user("viewer").roles("USER")))
            .andExpect(status().isOk())
            .andExpect(content().string("hello viewer"));
    }

    @Test
    void errorDispatchAndNormalRequestUseDifferentRules()
            throws Exception {

        mvc.perform(get("/dispatch-probe")
                .accept(MediaType.TEXT_HTML))
            .andExpect(status().is3xxRedirection());

        mvc.perform(get("/dispatch-probe")
                .with(request -> {
                    request.setDispatcherType(DispatcherType.ERROR);
                    return request;
                }))
            .andExpect(status().isOk())
            .andExpect(content().string("dispatch-probe"));
    }
}
```

Command to run:

```bash
./gradlew test
```

**Note on test confidence:** the test snippet is written to run with the example project and dependencies, but **has not been compiled or executed in this document**. Responses may differ when versions, classpath, `ErrorController`, or management context differ from the demo.

What the tests prove and do not prove:

- `get("/css/site.css")` returning 200 proves **both passing security and MVC serving the file**. `permitAll` alone does not guarantee the file actually exists.
- `user("viewer").roles("USER")` is a Spring Security Test request post-processor **constructing an authenticated principal**, suitable for testing **authorization**; it does not test password verification from a database.
- `get("/actuator/metrics").with(user("operator").roles("OPS"))` proves OPS has permission when the endpoint is exposed. It does not prove the endpoint listens only on a private network or secure management port.
- `request.setDispatcherType(DispatcherType.ERROR)` **simulates dispatch-type rule evaluation in a mock environment**, not that an HTTP client can send arbitrary dispatcher types. To test real 500/404 flows, use an embedded Servlet container and trigger a real error.
- Actuator tests rely on `application.yml` already exposing `health,info,metrics`. If metrics is not exposed, a 404/no-handler response does not prove the OPS rule is wrong.
- Never use `@WithMockUser` or `.with(user(...))` to prove login endpoints work; those are test-level authentication setups.

## 12. Additional Tests for Errors, Missing Resources, and HTTP Methods

An application usually needs tests beyond the happy path:

| Case | Why Test It | Expectation / Observable |
| --- | --- | --- |
| GET /css/missing.css | Public matcher does not guarantee resource exists | Typically 404, **no login redirect** |
| GET /css/site.css when anonymous | Login page must load assets | 200 with right MIME/body |
| GET /favicon.ico when file absent | Do not confuse 404 with authorization failure | 404 or valid fallback |
| Direct GET /error | Verify safe error body | No stack trace/token exposure |
| Container ERROR dispatch after controller error | Verify forwarding/error rendering | No login redirect loop, right status |
| Anonymous GET /admin/report | Block private controller | Login redirect/401 per entry point |
| User with ROLE_USER GET /admin/report | Insufficient permission | 403 |
| Anonymous GET /actuator/health | Public health | 200, minimal response |
| Anonymous GET /actuator/metrics | Operations must not be public | Must not return metrics list |
| ROLE_OPS GET /actuator/metrics | Operator has permission | 200 if endpoint exposed |
| POST to mutation-supporting Actuator endpoint | CSRF and permission | Denied if missing permission or CSRF |
| OPTIONS/preflight on Actuator | CORS policy | Per origin/method rules, never auto-open metrics |
| Separate management port | Does security apply to the right context? | Must test both app port and management port |
| Custom resource handler `/assets/**` | Does `PathRequest` match? | Add narrow matcher if needed |
| Unexposed HTTP `/actuator/env` | Not accessible | Do not infer endpoint exists solely from security rules |

### Why Does 404 Sometimes Become 302?

If an anonymous user requests `/css/missing.css` and security has **no public matcher** for that URL, authorization can trigger the login entry point before the resource handler detects the missing file. The result is 302, not 404. With the right static matcher, the request passes authorization, MVC sees the missing file, and returns 404/a valid error response.

### Real Error Dispatch Through a Web Server

With a real servlet container, create a test-only controller capable of throwing an internal error, then verify `/error` or a custom error controller is dispatched properly:

- Original request is `DispatcherType.REQUEST`.
- Container can perform `DispatcherType.ERROR`.
- Response is not replaced by a login redirect due to a blocked error dispatch.
- No stack traces or private exception details are exposed.
- If the response was already committed earlier, error dispatch has special constraints that should also be tested.

Never create an endpoint intentionally returning 500 in an unprotected production environment; error-triggering fixtures belong in a test profile.

## 13. When Multiple `SecurityFilterChain`s Are Needed: Separating UI, API, and Actuator Controlledly

A complex application can have multiple chains, e.g.:

```text
@Order(1): securityMatcher(EndpointRequest.toAnyEndpoint())
     -> health public, others ROLE_OPS
@Order(2): securityMatcher("/api/**")
     -> bearer token / stateless policy
@Order(3): match other requests
     -> form login, static resources, error handler
```

This is a **design diagram**, not complete code. Each chain has its own authentication mechanisms, CSRF/session, and authorization. If `EndpointRequest` mismatches/misses, an Actuator endpoint can fall into the web chain or a catch-all chain and be mishandled. If a general chain with higher priority precedes the actuator chain, later actuator rules may **never run**.

When designing multi-chain setups:

1. Document which matcher covers which paths and chain order.
2. Ensure error dispatches are still handled properly without causing security error loops.
3. Do not confuse `web.ignoring` with a public chain having security headers.
4. Leave endpoints outside any chain only when that is an **approved decision**; missed requests can leave gaps in protection.
5. Test both URLs and dispatcher types, not just one static URL in the first chain.
6. Check actuator exposure and security on the management context if splitting ports.

### `securityMatcher` vs. `requestMatchers` in Practice

If you write:

```java
http.securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/actuator/health").permitAll()
        .anyRequest().authenticated());
```

This is a **fragment** assuming only a chain matching `/api/**`: the health rule sits inside a chain that does not match `/actuator/health`, so it will never apply to health. Do not fix it by widening `/api/**` to `/**` arbitrarily; identify the right chain for actuator.

## 14. CSRF, Authentication Method, and Actuator Management Actions

Actuator has both read-only endpoints and endpoints that can allow administrative mutations depending on configuration/version (e.g., configuring log levels, shutdown if enabled, etc.). If the app uses browser sessions/form login, default CSRF protection can block unsafe methods such as POST/PATCH/DELETE before the action runs.

Do not disable CSRF globally just so a monitoring agent POST succeeds. Instead classify:

- **Read-only health/info/metrics:** GET, protected by authorization and network per purpose.
- **State-changing management endpoints:** require strong authentication, narrow operational roles, CSRF mitigation when browsers use ambient credentials, audit logs, and network isolation.
- **Machine-to-machine scrapers:** typically use dedicated identities, mTLS/bearer tokens, or non-browser-session mechanisms; never turn one scraper's exception into granting access to all users.

If configuring `csrf.ignoringRequestMatchers(...)` for machine endpoints, do so only after a threat model proves **ambient browser credentials are not accepted** and equivalent protections exist. `permitAll` is only authorization, not disabling CSRF; `hasRole("OPS")` also does not automatically disable CSRF on POST.

## 15. Headers, Caching, CORS, and Sensitive Data

### 15.1. Static Caching and Secrets/Ownership

Public CSS/JS can be cached at CDNs/browsers to reduce load. That does not mean private reports can be stored along static paths. If credentials or internal configs are bundled inside JS, everyone fetching the public file can read them; even if server-side APIs require `ROLE_ADMIN`, secrets leaked via static assets are unprotected.

Conversely, APIs returning per-account data must authorize every request and set appropriate cache policies; never serve private data from a shared public CDN key.

### 15.2. Security Headers

`permitAll()` still sends requests through the Spring Security chain where header filters set appropriate security headers. `web.ignoring()` typically skips them. Do not assume every header produced by Spring Security survives downstream CDNs/proxies; test responses through the real public origin.

Some headers to consider:

- `Content-Security-Policy` for web resources when applicable to reduce XSS risk.
- `X-Content-Type-Options: nosniff` to limit MIME type sniffing.
- Separate `Cache-Control` for private APIs and static assets.
- `Strict-Transport-Security` only effective over HTTPS with an appropriate policy.
- `Referrer-Policy` for navigation-related data.

Do not set "no caching on all static files" just out of fear of data leaks; use fingerprinted assets and public caching for truly public content while protecting private resources on separate endpoints.

### 15.3. CORS Does Not Replace Actuator Authorization

If a frontend on another origin needs to call health/metrics, CORS policy controls whether browser JavaScript can read the response. It does not replace authentication, authorization, or network ACLs. Never recklessly set `Access-Control-Allow-Origin: *` on operational endpoints using credentials; and never treat CORS as a firewall protecting Actuator from non-browser clients.

### 15.4. Liveness/Readiness Probes

Kubernetes liveness/readiness probes may target a health group or URL other than `/actuator/health` per Boot config. Decide whether probes are public on a private network or require machine identity. A `401` due to a wrong health rule can cause containers to restart continuously. Opening all of Actuator to "fix probes" is wrong in scope. Test the exact path, port, status, and audience of each probe.

## 16. Common Configuration Mistakes

| Mistake | Symptom or Risk | Fix |
| --- | --- | --- |
| Blocking all URLs except `/login` | CSS/JS/favicon redirect to login | `permitAll` for needed static locations |
| Using `web.ignoring("/**")` | Skips all of Spring Security | Permit only public resources inside the chain |
| `requestMatchers("/static/**")` for files in `classpath:/static/css` | Actual URL is `/css/**`, fails to match | Distinguish filesystem location from URL and test |
| Making `/css/**` public while storing private exports | User data leak | Never place private files under public static handlers |
| Making `/actuator/**` public | Exposes operational surface unintentionally | Public health, other endpoints allowlisted + OPS/network |
| Configuring only `EndpointRequest` without exposing metrics | Metrics returns 404 or no handler | Set exposure properly, then check permissions |
| Exposing metrics yet security matcher mismatches | Endpoint exposed or wrongly redirects to login | Use `EndpointRequest.toAnyEndpoint()`, test in practice |
| Placing `toAnyEndpoint()` before `to("health")` | Health ends up requiring OPS role | Place specific rules before general rules |
| Placing `anyRequest().authenticated()` before specific rules | Later rules fail to apply or config errors | Reorder matchers properly |
| Permitting only path `/error` while ignoring error dispatch semantics | Error statuses turn into login redirects | Understand `DispatcherType.ERROR` and error handling |
| Opening all `FORWARD` without checks | Risk of policy bypass on target dispatch | Open only after assessing trusted internal forwards |
| Public error controller printing stack traces | Leaks internal details | Sanitize error responses/properties |
| Thinking `MockMvc ERROR` equals container E2E error | Tests green yet container behaves differently | Add real HTTP integration tests |
| Changing management port while testing only app port | Management port lacks protection | Test both contexts, network rules, and auth |
| Disabling CSRF app-wide to call Actuator | Opens CSRF risk on browser endpoints | Scope exceptions tightly per threat model |
| Testing `hasRole("OPS")` with user lacking role expecting 401 | Authenticated missing permission usually returns 403 | Distinguish authentication 401/redirect and authorization 403 |
| Confusing `ROLE_ADMIN` with `ROLE_OPS` | Incorrect permission matrix | Define a role hierarchy if genuinely needed |
| Checking only URL/status without checking body or logs | May return 200 with error page or proxy cache | Test body, Content-Type, dispatch, and security metadata |

## 17. Review Questions with Answers

**Question 1.** Is `src/main/resources/static/css/site.css` loaded at URL `/static/css/site.css` or `/css/site.css` in default Boot MVC?

**Answer:** Usually `/css/site.css`. `static` is a resource location directory, not an automatic URL path prefix. Custom static handler configs can alter the URL path.

**Question 2.** Why is `permitAll()` usually better than `web.ignoring()` for public resources?

**Answer:** `permitAll` still passes through the Spring Security chain and appropriate filters/headers; ignoring typically skips the chain completely. With Spring Security 6, permit-all also optimizes authorization without needing `Authentication` lookup when permitted.

**Question 3.** An anonymous request to `/css/missing.css` gets a 302 to login. Does that prove the file exists?

**Answer:** No. The request can be blocked by authorization before MVC checks whether the resource is missing. Inspect static matchers; with the right public path, missing files typically return 404.

**Question 4.** How does `DispatcherType.ERROR` differ from a direct GET to `/error`?

**Answer:** `ERROR` is an **internal dispatch type** performed by the Servlet container when handling errors. `/error` is a **path**; normal requests can also target it. `dispatcherTypeMatchers(ERROR)` and `requestMatchers("/error")` have different scopes.

**Question 5.** Is an error page with `permitAll` allowed to display full stack traces?

**Answer:** No. Allowing error page rendering via authorization does not mean returning sensitive exception details. Sanitize, preserve accurate statuses, and restrict logs/responses per environment.

**Question 6.** Why must `EndpointRequest.to("health")` precede `EndpointRequest.toAnyEndpoint()`?

**Answer:** Authorization rules are evaluated in order. If the broad Actuator matcher catches it first, health can end up requiring OPS even though public access was intended.

**Question 7.** Why does adding `management.endpoints.web.exposure.include: metrics` not mean metrics became public?

**Answer:** Exposure only makes the endpoint reachable over HTTP; authorization still decides principal access. Combine with roles/network controls.

**Question 8.** When the management port is 9090, is testing `/actuator/metrics` on port 8080 sufficient to prove security?

**Answer:** No. The management server/context may differ; check the exact port, security chain, authentication, and network ACL on 9090.

**Question 9.** Does `@WithMockUser(roles="OPS")` prove a real user has a valid password?

**Answer:** No. It constructs a mock authenticated principal to test authorization. To test authentication, exercise the login/provider flow separately.

**Question 10.** Should `DispatcherType.FORWARD` be opened globally just because one JSP view fails to render?

**Answer:** Only when analysis of trusted forward paths, chains, and policies confirms it is appropriate. Opening all FORWARDs can let target dispatches bypass the authorization you intended to enforce.

**Question 11.** For an unexposed Actuator endpoint, should you fix it with `permitAll("/actuator/**")`?

**Answer:** No. Authorization does not make an unexposed endpoint appear; determine the required exposure first, then protect exposed endpoints with least privilege.

**Question 12.** Why is a 404/500 turning into a 302 login during error handling a concern?

**Answer:** It can mask real errors and cause redirect loops or hard-to-debug UX. Inspect dispatch types, error URLs, and security policies at each processing stage.

## 18. HTTP Policy Acceptance Checklist

- [ ] Inventory public static URLs, private downloads, business routes, error endpoints, and Actuator.
- [ ] Identify which `SecurityFilterChain` actually matches each URL; verify multi-chain ordering.
- [ ] Public static resources use `permitAll`, without skipping the entire filter chain unnecessarily.
- [ ] Confirm `PathRequest` covers the project's actual resource handler locations; add narrow custom matchers if needed.
- [ ] Keep no secrets, private exports, or sensitive user uploads in public static directories.
- [ ] Test that existing assets return 200; missing assets typically return 404 instead of login redirects.
- [ ] Test `DispatcherType.ERROR` and the `/error` URL along the Servlet container flow.
- [ ] Sanitize error responses, preserve statuses, and leak no stack traces/tokens/cookies.
- [ ] Do not open `DispatcherType.FORWARD` or all dispatches unconditionally without analysis.
- [ ] Actuator exposure includes only needed endpoints; no uncontrolled wildcard exposure.
- [ ] Public health stays within allowed scope with minimal details; probes hit the right port/path.
- [ ] Sensitive metrics/info/management endpoints require `ROLE_OPS` or stronger authentication.
- [ ] Verify `EndpointRequest.to("health")` precedes `toAnyEndpoint()` alongside catch-all policies.
- [ ] Test OPS, ADMIN, and USER roles independently; never assume an automatic role hierarchy.
- [ ] If the management server runs on a separate port, test its port/context/security/network separately.
- [ ] Keep CSRF in mind for unsafe management methods if browser credentials are used.
- [ ] Verify security headers/caching/CORS on both public assets and private endpoints.
- [ ] Test anonymous, authenticated lacking permission, authorized, and non-existent URLs.
- [ ] Use MockMvc for filter/rule checks; supplement with HTTP integration tests for error dispatches, proxies/CDNs, and network ACLs.
- [ ] Ensure logging/monitoring leaks no user tokens, session IDs, or exception secrets.
- [ ] Have automated regression tests when changing base path, deployment port, resource handlers, chain order, or actuator exposure.

## Conclusion

**Static resources, error endpoints, and Actuator require three distinct types of rules**, even though all pass through authorization in Spring Security Servlet. Public resources should be selectively `permitAll`; error dispatches must be handled with `DispatcherType.ERROR` and safe error bodies; Actuator requires separating **exposure** from **authorization**, keeping only health (or minimal probes) public when appropriate while protecting the rest with operational roles and network controls.

To verify properly, test **request URL, dispatch type, matcher/chain order, role, and body/status**, not just seeing a login page or 200. A solid policy permits strictly the needed resources without leaking private data or admin endpoints, and stays consistent when adding custom static handlers, changing base paths, splitting security chains, or moving Actuator to a separate management port.
