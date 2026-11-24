# permitAll vs. WebSecurityCustomizer.ignoring: Filter Protection Differences in Spring Security Servlet

In a **Spring MVC application running on the Servlet stack**, these two configurations might appear to create the same "no login required" URL:

- `authorizeHttpRequests(...).requestMatchers("/public/**").permitAll()`;
- `WebSecurityCustomizer` with `web.ignoring().requestMatchers("/public/**")`.

In reality, they are **not equivalent**. `permitAll()` is an **authorization rule** for requests that still traverse the security filter chain. `ignoring()` causes matching requests to **bypass Spring Security's filters**. The difference directly affects CSRF, security headers, optional authentication, security context, logging, and the ability to enforce protective policies later.

This lesson examines **Spring Security for Servlet** (`HttpSecurity`, `SecurityFilterChain`, `WebSecurityCustomizer`, `HttpServletRequest`), especially the common bean configuration style in Spring Boot 3.x / Spring Security 6.x. For other versions, consult the corresponding API and migration guide; the concept of **allowing at the authorization step** versus **bypassing security filters** remains central.

## 1. At which layers does Spring Security process a Servlet request?

When an application enables Spring Security Web, the container invokes servlet filters, among which `DelegatingFilterProxy` typically forwards security processing to the `springSecurityFilterChain` bean. This bean is `FilterChainProxy`, which selects the first **`SecurityFilterChain`** matching the request.

```text
HTTP request
    |
Servlet container FilterChain
    |
DelegatingFilterProxy ("springSecurityFilterChain")
    |
FilterChainProxy
    |-- select SecurityFilterChain by request matcher
    |       |
    |       +-- SecurityContext / authentication-related filters
    |       +-- header / CSRF / exception-handling filters
    |       +-- AuthorizationFilter (authorizeHttpRequests)
    |       +-- other security filters per configuration
    |
DispatcherServlet -> Controller -> Service
```

The diagram is a conceptual model; the **exact filter order and list** depend on enabled features, version, and configuration. Do not assume every application has the exact same filter list.

Three decisions to distinguish:

1. **Select chain:** `FilterChainProxy` finds the `SecurityFilterChain` configuration matching the request.
2. **Run filters:** filters in that chain get a chance to read/save authentication, handle exceptions, CSRF, headers, and so on per configuration.
3. **Authorize:** the authorization step evaluates rules like `permitAll`, `authenticated`, `hasRole`, or `access`.

**`permitAll` takes effect at step 3; `web.ignoring` takes effect before step 2.** A request allowed to reach a controller does not mean it bypassed all security filters.

Specifically, security filters here are filters **belonging to Spring Security**. Standalone Servlet filters registered by the application or container outside `FilterChainProxy` can still run for `web.ignoring` requests; do not interpret `ignoring` as "skipping every filter in the entire server".

## 2. permitAll: still runs the security chain, only removes the permission requirement for that URL

Typical Servlet configuration:

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/**").permitAll()
            .anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

This is an **illustrative bean method snippet**; the complete runnable project is in section 5. For `GET /public/ping`:

1. The request matches the application's `SecurityFilterChain` configuration.
2. Spring Security filters in the chain are still activated if present and applicable.
3. Reaching `AuthorizationFilter`, the `permitAll` rule allows the request without **requiring a logged-in principal**.
4. The request proceeds to the controller; the controller decides the response content and HTTP status.

### Does permitAll still include security headers?

**Yes, if header-writing filters are configured and run.** For example, Spring Security's `HeaderWriterFilter` can add default headers such as `X-Content-Type-Options: nosniff` or `X-Frame-Options: DENY`. Exactly which headers appear also depends on configuration, HTTP/HTTPS protocol, and version. **Content-Security-Policy is not always enabled by default**, so CSP requires explicit configuration if desired.

### Does permitAll disable CSRF?

**No.** CSRF is a separate check, typically applied to state-changing HTTP methods when CSRF protection is enabled. For instance, `POST /public/submit` can receive `403 Forbidden` due to a missing CSRF token **even though the URL is `permitAll`**. Those are two independent conditions: permitted at authorization yet still subject to CSRF rules.

Do not disable CSRF globally just to "fix a 403" when a website still uses cookies/sessions. If a truly stateless API authenticates solely via explicitly sent bearer tokens, CSRF handling differs and must match the credential model.

### Does permitAll skip authentication filters?

**No.** A public endpoint does not require successful authentication to pass authorization, but active authentication filters may still process any credentials that are sent. For example, if a client sends invalid `Authorization: Basic ...` to a public endpoint, `BasicAuthenticationFilter` may respond with an authentication error **before the controller runs**. Thus "public" does not mean "all invalid credentials are ignored".

In modern Spring Security versions using `authorizeHttpRequests`, authorization for `permitAll` typically does not need to query `Authentication` merely to decide allowance; that benefit does not mean all other filters stop running.

### Does permitAll discard information about a logged-in user?

**Not automatically.** When a request carries valid session/bearer credentials and the chain processes them per configuration, controllers or services can see the current authentication. A public page can personalize for logged-in users while still allowing anonymous access. This differs from removing all Spring Security filters from the request.

## 3. WebSecurityCustomizer.ignoring: bypassing the security filter chain

`WebSecurityCustomizer` configures at the `WebSecurity` level, typically used as follows:

```java
@Bean
WebSecurityCustomizer webSecurityCustomizer() {
    return web -> web.ignoring()
        .requestMatchers("/assets/**");
}
```

This is a **deliberate alternative option**, not a required part of the `permitAll` sample configuration. When a request matches an ignored matcher:

- Spring Security does not run the normal set of `SecurityFilterChain` filters for that request.
- Spring Security does not evaluate `hasRole`/`authenticated`/`permitAll` authorization rules on ignored requests.
- CSRF protection, security headers, and other mechanisms **provided by the Spring Security filter chain** do not execute for ignored requests.
- Authentication/security context is not initialized or populated **by filters belonging to the bypassed chain**. Independent mechanisms outside Spring Security may still exist, but you must not rely on them as an effect of `ignoring`.

For example, if you write both `web.ignoring().requestMatchers("/assets/**")` and `requestMatchers("/assets/**").authenticated()` in a security chain: ignored requests will never reach that authorization rule. A stricter rule lower down cannot "re-protect" a URL already ignored beforehand.

**Practical warning:** Spring Security generally recommends **`permitAll` instead of `ignoring`** for static resources in modern applications. Any benefit of bypassing filters must be specifically justified and measured; never use `ignoring` as a quick workaround for 401/403 errors.

## 4. Comparing mechanisms and consequences

| Criterion | `permitAll()` | `WebSecurityCustomizer.ignoring()` |
|---|---|---|
| Configuration location | `HttpSecurity.authorizeHttpRequests` inside a `SecurityFilterChain` | `WebSecurity.ignoring` at the web security configuration level |
| Does the request pass through Spring Security filters? | **Yes** (filters of the matching chain still process it) | **No** for the Spring Security chain's filters |
| Is login required to pass URL authorization? | No | Spring Security authorization is not evaluated for ignored URLs |
| Spring Security CSRF filter | Can still apply, depending on method/configuration | Does not run through the security chain |
| Security headers written by Spring Security | Can be added per configuration | Not added by the security chain |
| Valid sent authentication | Can be processed and placed in context | Not processed by bypassed authentication filters |
| `AuthorizationFilter` | Selected and applies the allow rule | Does not run |
| Method security like `@PreAuthorize` | Independent control layer, can still block | Can still work if enabled, but must not rely on security context from a bypassed chain |
| Typical appropriate use cases | Public pages, login, limited public health endpoints, static assets | Only requests genuinely meant to stay outside the **entire Spring Security filter chain**, very rare |
| Risk when misused | Confusing CSRF/authentication-filter errors with authorization errors | Losing headers, CSRF, authentication context, and filter-level protections |

Do not read this table as a guaranteed fixed HTTP result. An application may have a reverse proxy, custom servlet filters, controller validation, and exception handlers that add independent checks or headers. The table compares only **Spring Security Servlet** responsibilities.

## 5. Complete example with permitAll and MockMvc tests

The example below uses **Spring Boot 3.3.5 / Boot-managed Spring Security 6 / Java 17** as a concrete build baseline to reproduce behavior easily. This is an **illustrative baseline**, not a claim that this version remains supported or is the latest stable release. For real projects, pick a supported Spring Boot version and verify that exact version's JDK/dependency requirements.

Structure:

```text
security-permitall-demo/
├── pom.xml
└── src/
    ├── main/java/example/securitydemo/
    │   ├── SecurityDemoApplication.java
    │   ├── ServletSecurityConfig.java
    │   └── DemoController.java
    └── test/java/example/securitydemo/
        └── SecurityBoundaryTest.java
```

### 5.1. Maven declaration

Create `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>security-permitall-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
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

Do not pin separate versions for `spring-security-web` or `spring-security-config`: Spring Boot parent manages a compatible Spring dependency set.

### 5.2. Application and controller

Create `src/main/java/example/securitydemo/SecurityDemoApplication.java`:

```java
package example.securitydemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityDemoApplication.class, args);
    }
}
```

Create `src/main/java/example/securitydemo/DemoController.java`:

```java
package example.securitydemo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {
    @GetMapping("/public/ping")
    public String ping() {
        return "PUBLIC_OK";
    }

    @PostMapping("/public/submit")
    public String submit() {
        return "SUBMITTED";
    }

    @GetMapping("/private/data")
    public String privateData() {
        return "PRIVATE_OK";
    }
}
```

### 5.3. Configuring only permitAll, without ignore

Create `src/main/java/example/securitydemo/ServletSecurityConfig.java`:

```java
package example.securitydemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ServletSecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

Do not disable `csrf`. That way the example clearly shows: **a POST to a `permitAll` URL can still be blocked by the CSRF filter**, while a GET to that URL is served publicly. `httpBasic` creates the authentication mechanism for private paths; if credentials are missing, the result is typically HTTP 401. Spring Boot may generate a default development user/password when no `UserDetailsService` is configured; the demo does not use the default account in tests.

### 5.4. Integration tests proving filters actually run

Create `src/test/java/example/securitydemo/SecurityBoundaryTest.java`:

```java
package example.securitydemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityBoundaryTest {
    @Autowired
    MockMvc mvc;

    @Test
    void publicGetIsPermittedAndSecurityHeadersStillAppear() throws Exception {
        mvc.perform(get("/public/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("PUBLIC_OK"))
            .andExpect(header().string("X-Content-Type-Options", "nosniff"));
    }

    @Test
    void publicPostStillNeedsCsrfToken() throws Exception {
        mvc.perform(post("/public/submit"))
            .andExpect(status().isForbidden());
    }

    @Test
    void publicPostWithCsrfTokenIsPermitted() throws Exception {
        mvc.perform(post("/public/submit").with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("SUBMITTED"));
    }

    @Test
    void privateGetWithoutLoginIsUnauthorized() throws Exception {
        mvc.perform(get("/private/data"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser
    void privateGetWithMockUserIsAccessible() throws Exception {
        mvc.perform(get("/private/data"))
            .andExpect(status().isOk())
            .andExpect(content().string("PRIVATE_OK"));
    }
}
```

`@WithMockUser` places a mock user into the test context; it does not create a production user. The `csrf()` function from `spring-security-test` attaches a valid CSRF token for test requests; it does not prove a production application automatically sends valid CSRF tokens.

Run with **compatible JDK 17+, Maven on PATH, and internet or Maven cache**:

```bash
mvn -version
mvn test
mvn spring-boot:run
```

`mvn test` is expected to have **all 5 tests pass** under the exact project/version above. Maven has no fixed stdout string because logs depend on machine and environment; do not treat this as executed output unless actually run.

Once the server runs on default port 8080, open another terminal:

```bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/private/data
curl -i -X POST http://localhost:8080/public/submit
```

Expected behavioral results:

| Request | Typical HTTP status | Explanation |
|---|---|---|
| `GET /public/ping` without credentials | `200`, body `PUBLIC_OK` | URL is `permitAll`, controller runs; security headers may be added |
| `GET /private/data` without credentials | `401` | `authenticated()` rule and HTTP Basic entry point |
| `POST /public/submit` without CSRF token | `403` | CSRF blocks even though URL is `permitAll` |
| `POST /public/submit` with valid CSRF token | `200`, body `SUBMITTED` | In integration tests using `with(csrf())` |

Do not copy a fake `MockMvc` token into curl: real CSRF tokens tie into repository/session/cookie mechanisms and must be sent according to design. For apps using HTTP Basic in browsers, automatic credential sending is why you should not casually disable CSRF.

## 6. Experimenting with ignoring to see the difference (learning environment only)

Keep the files from section 5 intact and **temporarily add** a new bean to `ServletSecurityConfig`, along with its import:

```java
import org.springframework.security.config.annotation.web.configuration.WebSecurityCustomizer;

// Inside class ServletSecurityConfig:
@Bean
WebSecurityCustomizer webSecurityCustomizer() {
    return web -> web.ignoring()
        .requestMatchers("/public/**");
}
```

This is an **illustrative configuration snippet inserted into an existing class**, not a standalone Java file. This configuration deliberately bypasses Spring Security for `/public/**` and is **not recommended** as a production configuration for dynamic endpoints.

When tried in section 5's project:

- `GET /public/ping` is still served by the controller and usually returns `200`, but Spring Security does not add `X-Content-Type-Options` for the ignored route.
- `POST /public/submit` without a CSRF token can now be served by the controller and return `200`, because Spring Security's CSRF filter does not run on ignored requests.
- `/private/data` still uses the security chain as before because it does **not** match the ignore matcher.
- A Spring Security warning may point out that ignoring requests is not recommended.

These differences hold when **no other filter/proxy** adds headers or blocks POSTs and the rest of the application configuration stays unchanged. That is why you should not use a single `GET=200` outcome to conclude the two mechanisms are identical.

**After observing, remove the temporary `WebSecurityCustomizer` bean** to return to the safe `permitAll`-based configuration in section 5. The demonstration does not modify data or security of any other application.

## 7. Static resources: when to use permitAll, and when to even consider ignoring?

Suppose an application serves CSS/JS/static images at `/assets/**`:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/assets/**", "/favicon.ico").permitAll()
    .anyRequest().authenticated())
```

This is a code fragment inside `HttpSecurity` configuration. With Spring Boot 3.x and MVC, you can also use the convenience matcher `PathRequest.toStaticResources().atCommonLocations()` if it matches your actual resource layout; do not assume it covers every custom static directory.

**Prefer `permitAll`** because security headers still apply, filter-chain security policies and logging remain consistent, and configuration is easy to adapt if URLs evolve into dynamic resources. With recent Security versions, `permitAll` also avoids unnecessary authentication lookups just to make an access decision, so performance arguments for ignoring static resources are weaker than often assumed.

Only consider `ignoring` if you have proven a scope of resources is completely public, contains no sensitive data, needs **none** of Spring Security's filters, and has strong measured performance/operational evidence. Even then, carefully verify security headers at CDN/reverse proxy, caching, authentication, and negative tests; never apply broad matchers like `/**`, `/api/**`, or `/admin/**`.

### Public endpoints beyond static resources

- **Login pages, public info pages, public data APIs:** normally use `permitAll` because HTTP security processing is still needed.
- **Webhook or callback APIs not relying on user login:** do not assume they must be `ignore`d. They still usually require HMAC signatures, OAuth, mTLS, or application-level secret checks and can use `permitAll` in URL authorization where appropriate.
- **Health/readiness endpoints:** may be limitedly public or require authentication depending on environment. Do not bypass the entire chain just because an endpoint serves monitoring; clearly define what data is exposed.
- **CORS preflight (OPTIONS):** configure CORS and preflight handling properly with Spring Security; do not use `web.ignoring("/**")` or ignore APIs to mask CORS errors.
- **Actuator, Swagger/OpenAPI, static app bundles:** decide public scope individually; do not open all of `/actuator/**` or `/api/**` just to reach a few resources.

## 8. Do not confuse ignoring with securityMatcher and multiple SecurityFilterChains

These are different APIs:

- `http.securityMatcher("/api/**")`: specifies the **request scope managed by this `SecurityFilterChain`**.
- `auth.requestMatchers("/api/public/**").permitAll()`: specifies an **authorization rule inside the selected chain**.
- `web.ignoring().requestMatchers("/assets/**")`: excludes requests from the **Spring Security filter chain**.

Multi-chain example:

```java
@Bean
@Order(1)
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public/**").permitAll()
            .anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}

@Bean
@Order(2)
SecurityFilterChain fallbackSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth.anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

This is a **standalone snippet in terms of the two bean methods**, though placing it in a Java configuration class still requires importing `@Bean`, `@Order`, `HttpSecurity`, `Customizer`, and `SecurityFilterChain`. Do not copy it alongside section 5's `securityFilterChain` bean without adjusting the design.

According to `@Order`, `/api/public/ping` selects the API chain and receives `permitAll` **within that chain**; requests outside `/api/**` are governed by the fallback chain. If a narrow `securityMatcher` is specified **without a fallback chain**, requests matching no security chain may proceed outside Spring Security's protection; that is a dangerous configuration if endpoints are accidentally exposed.

**First matching chain selection** is different from "running all chains sequentially". Therefore a `permitAll` rule in one chain has no effect on a request already selected into an earlier chain; never guess the outcome without first determining which chain handles the request.

## 9. Important misconceptions when testing

### "permitAll skips every filter"

False: `permitAll` does not turn off `CsrfFilter`, `HeaderWriterFilter`, authentication filters, or custom filters in the chain. Write tests for public GET with security headers and public POST without a CSRF token, as in section 5.

### "If ignoring is used, @PreAuthorize is definitely disabled"

Inaccurate. **Method security** is an independent inspection layer at the method level if enabled via `@EnableMethodSecurity`. A method annotated with `@PreAuthorize` can still reject calls. However, when a URL is ignored, authentication may not be loaded into `SecurityContextHolder` by web security filters; the outcome depends on how method security obtains the principal and other configuration. Never rely on method security to justify dropping all web filters.

### "Putting permitAll below anyRequest still works"

Normally no. Rules must be configured in a **valid order**, from specific matchers to fallback; `anyRequest()` catches all remaining requests. If matchers are misordered, Spring Security may throw an error or the specific rule will not achieve its intended effect. Ensure:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public/**").permitAll()
    .anyRequest().authenticated())
```

### "WebSecurityCustomizer.ignoring is how to fix a 403 CSRF error"

That **evades** the CSRF filter and can open a CSRF vulnerability if browsers automatically send credentials. Identify the method, session/cookie, token, and protection requirements; configure CSRF properly in `HttpSecurity` instead of dropping the entire filter chain.

### "An ignored path means all Spring Security config is irrelevant"

For an ignored request, the Security filter chain does not run; however, global servlet filters, Reverse Proxy/CDN headers, controller validation, independent method security, and other interceptors may still exist. During incident analysis, inspect the **actual HTTP path**.

### "A 200 on GET proves the public route is properly protected"

Not sufficient. You must also check 401/403, anonymous vs. authenticated, POST without a CSRF token, security headers, login/logout, filter logs, and role-based access conditions. An endpoint returning 200 could have passed through `permitAll` or bypassed all security filters; status alone cannot distinguish them.

## 10. How to diagnose which filters process a request

1. **Confirm the Servlet stack:** `spring-boot-starter-web`, `HttpSecurity` configuration, and `SecurityFilterChain` beans are present; do not confuse with WebFlux's `SecurityWebFilterChain`.
2. **List security matchers:** check `WebSecurityCustomizer`, `securityMatcher`, `@Order` across multiple chains, and the `anyRequest` fallback.
3. **Inspect logs during development:** configure `org.springframework.security` logging at DEBUG only in an appropriate environment; Spring Security can log chain selection and filter application, but do not leave DEBUG enabled long-term in production if logs contain sensitive data.
4. **Test concrete mechanisms:** default headers, CSRF on POST, invalid basic/bearer credentials, anonymous/private authorization.
5. **Run MockMvc integration tests:** verify status, headers, body, and CSRF, combined with business service/method authorization tests.
6. **Check Servlet filters outside Security:** if ignored yet headers/checks still appear, look for other filters or proxies instead of claiming `ignoring` failed to work.

When debugging authorization, avoid concluding "403 is caused by `hasRole`" before determining whether the request was blocked by the CSRF filter or by service/method security.

## 11. Choosing configuration by scenario

| Scenario | Usually appropriate choice | What to verify |
|---|---|---|
| Public HTML page using session/cookie | `permitAll` | CSRF on form POST, security headers, session |
| Public GET controller, personalizable on login | `permitAll` | Authentication processed if sent; anonymous still allowed |
| Public REST returning non-sensitive data | `permitAll` | CORS, rate limiting/abuse controls, headers, method rules |
| Static CSS/JS/images of web MVC | Usually `permitAll` | Caching/CDN, security headers, measured performance |
| Internal health endpoint | `permitAll` or `authenticated` per policy | Do not expose sensitive operational info |
| Resource truly meant to bypass **all Spring Security filters** | Consider `ignoring` only for very narrow exceptions | Header/CSRF/authentication risks, clear documentation and tests |
| API protected by bearer token | Matching chain + `oauth2ResourceServer` / `authenticated` / scope rules | Token validity, issuer/audience, policy; do not ignore APIs |
| Path with authorization varying by HTTP method | `requestMatchers(HttpMethod, path)` + specific rules | CSRF independent of authorization and method safety |

**Rule of thumb:** when the requirement is **"no login needed to access this URL"**, start with `permitAll`. Use `ignoring` only when the requirement is genuinely **"run no Spring Security filters for this request"**, and the consequences are well understood.

### Self-check questions

**1.** `POST /public/submit` is `permitAll`; why did it return HTTP 403?  
*Answer:* The CSRF filter still runs and can reject a POST missing a token; authorization allowance does not mean CSRF is disabled.

**2.** For the same static URL, why does `ignoring` stop Spring Security from adding default headers?  
*Answer:* The request does not pass through header-writing filters in the Spring Security chain. Headers might still be added by another component, but not by that chain.

**3.** Can you use `web.ignoring().requestMatchers("/api/**")` and then `hasRole("ADMIN")` to protect an API?  
*Answer:* No. Ignoring prevents requests from reaching authorization rules in the chain. Never use this for protecting APIs.

**4.** When an MVC website needs a public homepage while still knowing whether a user is logged in, what should be used?  
*Answer:* `permitAll`; security filters can still load valid authentication, while anonymous callers remain permitted.

**5.** Is `http.securityMatcher("/api/**")` equivalent to `web.ignoring().requestMatchers("/api/**")`?  
*Answer:* No. `securityMatcher` limits a chain to handling those URLs; `ignoring` excludes URLs from Spring Security filters.

**Conclusion:** `permitAll()` **permits at the authorization step while maintaining the Spring Security filter chain**; `WebSecurityCustomizer.ignoring()` **bypasses that filter chain itself**. For most public endpoints in Spring MVC/Servlet, `permitAll` is the least surprising choice and preserves HTTP protection layers.