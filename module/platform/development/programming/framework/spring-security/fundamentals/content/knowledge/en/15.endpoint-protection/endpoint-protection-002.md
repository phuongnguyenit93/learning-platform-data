# Allowing Public Endpoints with `permitAll`

> **Module:** Spring Security - fundamentals  
> **Group:** Endpoint protection  
> **Focus:** Use `permitAll()` to allow matching requests through the **HTTP-level authorization check**, while keeping the application inside the Spring Security filter chain.

## 1. Objectives

After this lesson, you should be able to:

- Explain accurately what `permitAll()` allows and which protection layers **remain active**.
- Configure public paths such as `GET /public/ping` or a login page alongside endpoints requiring authentication.
- Understand how `requestMatchers(...)`, HTTP methods, rule order, and `anyRequest()` determine which requests are permitted.
- Distinguish `permitAll()` from `authenticated()`, `anonymous()`, `denyAll()`, `web.ignoring()`, and `securityMatcher(...)`.
- Verify behavior with HTTP requests and Spring Security MockMvc tests, especially the scenario where a **public POST still needs a CSRF token** when CSRF is enabled.

## 2. What Does `permitAll()` Actually Do?

An endpoint is called **public** when the application's access policy allows clients to use it without requiring login. In modern Servlet Spring Security, you can declare:

~~~java
// DSL illustration inside HttpSecurity configuration.
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public/**").permitAll()
    .anyRequest().authenticated()
);
~~~

`permitAll()` is an **authorization** decision: for requests matching the matcher, this access check returns allowed without needing to look up a specific `Authentication` to make the decision. In the Spring Security 6+ `authorizeHttpRequests` model, a `permitAll` rule also does not need to fetch `Authentication` from the HTTP session just to check authorization.

Important point: **`permitAll()` does not mean the request bypasses Spring Security.** If the request still matches the `SecurityFilterChain`, the relevant filters can still execute, for example:

- Filters handling configured authentication mechanisms such as HTTP Basic, Bearer token, or form login.
- CSRF protection for requests matching the CSRF policy.
- Security response headers and other security integrations configured in the chain.
- Custom filters and method/business-layer checks if the application has them.

Therefore, the accurate statement is:

> **"The endpoint is allowed without requiring authentication at this HTTP authorization rule."**  
> Not "all security checks have been turned off for the endpoint."

### Conceptual Processing Flow

~~~text
GET /public/ping  -- no credentials sent
       |
       v
Select matching SecurityFilterChain
       |
       v
Security filters applied to the chain
       |  (authentication, headers, CSRF if applicable...)
       v
AuthorizationFilter
       |
       +-- request matches /public/ping -> permitAll -> GRANTED
       |
       v
Controller handles request
       |
       v
HTTP 200 + response body
~~~

If the controller throws an error, the path does not exist, the HTTP method is unsupported, or another filter rejects it, the client can still receive `4xx`/`5xx`. `permitAll` does not guarantee the final status is always `200 OK`.

## 3. Rule Types Within the Same `authorizeHttpRequests`

The following table describes common rules at the Servlet authorization layer:

| Rule | Meaning | Example |
| --- | --- | --- |
| `permitAll()` | Skips authentication/authority requirements at this rule; matching requests are granted access | Landing page, public health probe |
| `authenticated()` | Requires an identity recognized by Spring Security as authenticated | `/api/me` |
| `hasAuthority("report:read")` | Requires an authority matching the exact required string | Reading internal reports |
| `hasRole("ADMIN")` | By default requires the `ROLE_ADMIN` authority | Administrative endpoints |
| `anonymous()` | Allows only requests evaluated by Spring Security as anonymous | Certain guest-only pages |
| `denyAll()` | Always denies at the HTTP authorization step | Unpublished paths |

`authenticated()` does **not** mean the user is allowed to perform every operation. `permitAll()` is also not `anonymous()`: a logged-in user is still allowed to call a public endpoint unless another policy restricts them.

### Defining the Public Surface Explicitly

Suppose the application has:

~~~text
GET  /public/ping       -> public
POST /public/feedback   -> public at the authorization step
GET  /api/me            -> requires authentication
GET  /admin/reports     -> requires ROLE_ADMIN
all other requests      -> denied by default
~~~

An explicit configuration can be written as:

~~~java
// Excerpt inside SecurityFilterChain; imports are shown in the full example.
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/public/ping").permitAll()
    .requestMatchers(HttpMethod.POST, "/public/feedback").permitAll()
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll()
);
~~~

**Why include `HttpMethod.GET` and `HttpMethod.POST`?** A path can support multiple methods with different sensitivity levels. `requestMatchers("/public/**").permitAll()` is broader, applying to all HTTP methods matching the pattern. If you only want `GET /public/ping` to be public, a matcher with an HTTP method expresses the intent more accurately.

**Why use `anyRequest().denyAll()`?** So that endpoints added later are not accidentally exposed; developers must declare permissions before opening them. If the application design requires all remaining endpoints to be usable after login, `anyRequest().authenticated()` may be appropriate. Choose the default based on real policy, not habit.

## 4. Runnable Spring Boot 3.3 / Java 17+ Example

The following example uses Spring MVC on Servlet with Spring Security 6.x via Spring Boot 3.3.5. We create **two public endpoints** (`GET`, `POST`) and **one private endpoint**, keeping default CSRF enabled to clearly observe the scope of `permitAll`.

### 4.1. File Structure

~~~text
public-endpoints-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/
    │   ├── PublicEndpointsApplication.java
    │   ├── SecurityConfig.java
    │   └── PublicController.java
    └── test/java/demo/
        └── PublicEndpointSecurityTest.java
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'public-endpoints-demo'
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

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
~~~

**Explanation:** Starter Web creates HTTP controllers on the Servlet stack; Starter Security adds the filter chain; the Spring Security Test dependency provides utilities to simulate authentication and CSRF during testing. You do not need to declare the Spring Security version directly because the Spring Boot BOM manages compatible versions.

### 4.2. Application Startup

File `src/main/java/demo/PublicEndpointsApplication.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PublicEndpointsApplication {
    public static void main(String[] args) {
        SpringApplication.run(PublicEndpointsApplication.class, args);
    }
}
~~~

### 4.3. Declaring `SecurityFilterChain`

File `src/main/java/demo/SecurityConfig.java`:

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public/ping")
                    .permitAll()
                .requestMatchers(HttpMethod.POST, "/public/feedback")
                    .permitAll()
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo-password"))
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(alice);
    }
}
~~~

**Explanation of each decision:**

1. `GET /public/ping` and `POST /public/feedback` receive `permitAll`. These are **two authorization rules**, not configuration disabling the filter chain.
2. `/api/**` requires `authenticated()`, so `GET /api/me` cannot be called with only an anonymous session.
3. Undeclared URLs are handled by `denyAll()`. With this fallback, new endpoints must have a policy declared before use.
4. `httpBasic()` provides a simple authentication mechanism for testing with `curl -u`.
5. `InMemoryUserDetailsManager` and the password `demo-password` are for local demonstration only. Production requires an appropriate credential store, user management, and password policy.
6. **There is no** `csrf.disable()`. Spring Security keeps default CSRF protection on applicable requests; as a result, the public `POST` demonstrates a boundary separate from authorization.

### 4.4. Creating the Controller

File `src/main/java/demo/PublicController.java`:

~~~java
package demo;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PublicController {

    @GetMapping("/public/ping")
    public String ping() {
        return "pong";
    }

    @PostMapping("/public/feedback")
    public String feedback() {
        return "received";
    }

    @GetMapping("/api/me")
    public String me(Authentication authentication) {
        return "user=" + authentication.getName();
    }
}
~~~

`ping()` does not require an `Authentication`. `me()` can take an `Authentication` argument because the `/api/**.authenticated()` rule requires the request to be authenticated. In complex applications, business logic still must verify resource permissions/ownership when needed.

### 4.5. Running and Observing

From the project directory, using JDK 17+ and a Gradle 8.x version compatible with the Spring Boot 3.3 plugin:

~~~bash
gradle bootRun
~~~

Open another terminal and call:

~~~bash
curl -i http://localhost:8080/public/ping
~~~

Core result: **HTTP 200**, body:

~~~text
pong
~~~

Without sending `Authorization` or a session cookie, you still receive the body `pong`: the `permitAll` rule allowed this request.

~~~bash
curl -i http://localhost:8080/api/me
~~~

With the HTTP Basic configuration above, a request without valid credentials typically receives **HTTP 401** with a `WWW-Authenticate` header. This is the result of the `authenticated()` rule, unlike `permitAll()`.

~~~bash
curl -i -u alice:demo-password http://localhost:8080/api/me
~~~

Core result: **HTTP 200**, body:

~~~text
user=alice
~~~

To see that `permitAll` **does not bypass CSRF**, try:

~~~bash
curl -i -X POST http://localhost:8080/public/feedback
~~~

With default CSRF protection and no CSRF token sent, this POST request is rejected, typically with **HTTP 403**. The URL is configured with `permitAll`, yet the request still must pass the applicable security filters.

> The `curl` examples show only the primary status and body, without listing every response header or framework-generated error page. Tests in the next section demonstrate how to supply a valid CSRF token. If the application has customized CSRF, authentication entry point, filter chain, or error handling, HTTP results may differ.

## 5. Automated Testing to Prove the Rules

File `src/test/java/demo/PublicEndpointSecurityTest.java`:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PublicEndpointSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicGetWorksWithoutCredentials() throws Exception {
        mvc.perform(get("/public/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("pong"));
    }

    @Test
    void privateGetRequiresAuthentication() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedGetCanReadThePrincipal() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("alice", "demo-password")))
            .andExpect(status().isOk())
            .andExpect(content().string("user=alice"));
    }

    @Test
    void publicPostStillNeedsCsrfWhenCsrfIsEnabled()
            throws Exception {
        mvc.perform(post("/public/feedback"))
            .andExpect(status().isForbidden());

        mvc.perform(post("/public/feedback").with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("received"));
    }
}
~~~

**Explanation:** Wrapped static imports are still valid Java syntax because an `import static ...;` statement only ends at the semicolon. `httpBasic(...)` attaches HTTP Basic credentials to the request; `csrf()` generates a valid CSRF token in the MockMvc request; they do not alter the `permitAll` rule.

Run:

~~~bash
gradle test
~~~

Expected: **4 tests passed**. This is a standalone illustrative scenario to run in a project created following the guide; test statuses reflect the defaults/configuration noted above. Do not use this test as proof that other applications share the same CSRF, session, or entry point setup.

Four verified scenarios:

| Request | Credentials / CSRF | Expected |
| --- | --- | --- |
| `GET /public/ping` | No credentials | `200`, `pong` |
| `GET /api/me` | No credentials | `401` under HTTP Basic configuration |
| `GET /api/me` | Alice's HTTP Basic | `200`, `user=alice` |
| `POST /public/feedback` | No CSRF token | `403` |
| `POST /public/feedback` | Valid CSRF token in MockMvc | `200`, `received` |

**Important note:** `gradle test` is the verification command; the `4 tests passed` result is the expected outcome of the described fixture, not a log measured on your machine.

## 6. Matchers Must Be Specific and Properly Ordered

In `authorizeHttpRequests`, Spring Security evaluates declared rules in order and uses the **first rule that matches the request**. An overly broad matcher placed earlier can prevent stricter rules below it from ever being used.

**Wrong example:**

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/**").permitAll()
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated()
);
~~~

`/**` already matched `/admin/reports` first. The `hasRole("ADMIN")` rule never gets a chance to protect the corresponding request.

**Correct way to express intent:**

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/public/ping").permitAll()
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll()
);
~~~

Do not place `anyRequest()` before specific rules. If the application has many paths, reserve public access for clearly identifiable groups (`/public/**`, static resources, dedicated callbacks), avoiding a broad glob as a "quick fix" for 401/403 errors.

### Open Only the Intended HTTP Method

For example, on the same `/catalog` path:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/catalog").permitAll()
    .requestMatchers(HttpMethod.POST, "/catalog")
        .hasAuthority("catalog:write")
    .anyRequest().authenticated()
);
~~~

`GET` is treated as public; `POST` requires write authority. You should not replace both rules with `requestMatchers("/catalog").permitAll()` if the endpoint supports both read and data-creation actions.

### What Happens When No Controller Exists?

`permitAll` only decides **authorization**. It does not create HTTP mappings on its own:

~~~text
GET /public/does-not-exist
    -> If /public/** is permitAll, proceeds to the application
    -> No matching handler
    -> Typically 404, not 200
~~~

If the request uses an HTTP method not supported by the controller, it may receive `405 Method Not Allowed` or another error response after the filters. Do not treat every `4xx` on a public URL as evidence that `permitAll` failed.

## 7. How Does `permitAll` Differ from `web.ignoring()`?

This is one of the most error-prone distinctions when protecting endpoints and static resources.

| Configuration approach | Does the request go through the Spring Security filter chain? | Effect |
| --- | --- | --- |
| `requestMatchers("/css/**").permitAll()` inside a chain | **Yes**, if that chain matches the request | No authz required; can still receive security headers, CORS/CSRF, and relevant filters |
| `web.ignoring().requestMatchers("/css/**")` | **No**, bypasses the Spring Security chain for ignored paths | Spring Security does not apply security headers or its filters to that request |
| `http.securityMatcher("/api/**")` on a chain | Selects the **request scope** of that chain | Not a "permit" rule for endpoints inside the chain; another chain may handle it or no chain may match |

In Spring Security 6+, official documentation recommends preferring `permitAll` over ignoring the filter chain, even for static resources. One reason is that response security headers remain useful for CSS/JS/images. Evaluating `permitAll` authorization also does not need to retrieve `Authentication` from the session, avoiding the performance drawback of some older approaches.

**Do not use `web.ignoring()` just to let unauthenticated users download assets.** If you truly need to exclude a request from Spring Security, consider the consequences for all filters and security headers instead of treating it as shorthand for `permitAll`.

## 8. `requestMatchers` and `securityMatcher` Operate at Two Different Layers

When multiple `SecurityFilterChain` beans exist, Spring Security selects the matching chain for the request (according to the configured chain order). **Inside the selected chain**, the `authorizeHttpRequests` rules evaluate conditions.

~~~text
Request
   |
   v
Which SecurityFilterChain matches securityMatcher?
   |
   +-- Chain 1: /api/**   -> authorizeHttpRequests rules of Chain 1
   |
   +-- Chain 2: all remaining URLs -> rules of Chain 2
   |
   v
Only the selected chain applies
~~~

Conceptual example:

~~~java
// Illustrative configuration snippet; these are two @Bean methods in one @Configuration.
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public/**").permitAll()
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}

@Bean
@Order(2)
SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/**").permitAll()
            .anyRequest().denyAll()
        )
        .build();
}
~~~

Additional imports include `org.springframework.core.annotation.Order`. **This is an alternative configuration to understand the multi-chain mechanism; do not paste it verbatim into the example project in section 4.** When `/api/public/ping` is called, the request matches the API chain. Putting `/api/public/**.permitAll()` only in the fallback chain will not help, because that chain is not selected for `/api/**` URLs.

If a request does not match **any** `SecurityFilterChain`, it may fall outside Spring Security's protection. Always verify chain coverage and provide an appropriate fallback chain when configuring multiple chains.

## 9. Protection Layers That Still Apply to Public Endpoints

### 9.1. CSRF for State-Changing Actions

CSRF protects certain types of applications that use cookies/sessions automatically sent by browsers. By default, Spring Security Servlet requires a CSRF token for "unsafe" HTTP methods such as `POST`, `PUT`, `PATCH`, and `DELETE`.

~~~text
POST /public/feedback
  permitAll at authorization: Yes
  CSRF token required by config: Yes
  No CSRF token sent: 403 (with the example configuration)
~~~

Do not assume "a public POST means `csrf.disable()` is required." If it is a stateless API using only bearer tokens in the Authorization header and does not rely on ambient browser credentials, evaluate CSRF needs based on the actual threat model. When exceptions are needed, scope the CSRF matcher strictly to those endpoints and document why; do not disable CSRF for an entire session-based web app just to fix a test.

### 9.2. Authentication Filters Can Still React to Bad Credentials

For a public endpoint, clients do not need to send credentials. However, if a client **actively** sends an invalid Bearer token to an application configured as an OAuth2 Resource Server, the authentication filter can reject that token **before reaching the `permitAll` rule**. Similarly, a malformed HTTP Basic header can trigger an authentication failure response depending on the filter/entry point.

Do not promise that "`permitAll` always returns 200 even when the request contains invalid credentials." Test **no credentials** and **invalid credentials** separately according to the chain's actual authentication mechanism.

### 9.3. CORS Is a Separate Mechanism

A public API does not mean JavaScript on every origin can freely read responses. Browsers enforce the same-origin policy and CORS; Spring Security and Spring MVC/WebFlux must have CORS configured according to requirements. Preflight `OPTIONS` requests can be handled differently from actual requests; allowing public `GET` with `permitAll` **does not automatically generate CORS response headers**.

### 9.4. Method Security and Business Rules Remain Active

An endpoint can be `permitAll` at the HTTP layer while the handler calls a service annotated with `@PreAuthorize("hasRole('ADMIN')")` or performs resource-level authorization checks. When method security is enabled and the call passes through the security proxy, that policy can still deny access. Avoid contradictory configurations between public declarations and mandatory login logic underneath; if only a subset of data should be public, design a dedicated API for the public view.

### 9.5. Headers, Session, Logging

Security headers such as `X-Content-Type-Options` or `X-Frame-Options` can still be added by the chain. `permitAll` **does not prevent** the application from actively creating a session when needed, nor is it a directive to "store no cookies." Not reading `Authentication` from the session **for this specific authorization decision** does not mean no other filter or component ever accesses the session.

## 10. Practical Examples: Static Assets, Login Page, Health, and APIs

### Static Assets

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/css/**", "/js/**", "/images/**").permitAll()
    .anyRequest().authenticated()
);
~~~

This example fits when those paths actually serve public assets. With Spring Boot, you can use `PathRequest.toStaticResources().atCommonLocations()` where appropriate to express common static resource locations instead of listing them manually. Check the actual paths and where the application packages assets.

### Login Page and Supporting Resources

~~~java
// Illustrative application-level configuration snippet with form login.
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/login", "/css/**", "/js/**").permitAll()
    .anyRequest().authenticated()
).formLogin(Customizer.withDefaults());
~~~

Default form login provides the corresponding login page/processing mechanism. For a **custom login page**, you need to create the appropriate MVC controller/template and ensure the login endpoint, CSS/JS are accessible while unauthenticated to avoid redirect loops. `permitAll` at the HTTP authorization layer does not replace configuring login processing or CSRF.

### Health Probe

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/actuator/health").permitAll()
    .anyRequest().authenticated()
);
~~~

This is an example of an **access rule**, not automatically installing Actuator or enabling the endpoint. If using Spring Boot Actuator, you need the dependency, exposure configuration, and matching access rules. Avoid exposing all of `/actuator/**` by default just to make the health probe public; other management endpoints may leak sensitive information.

### API Serving Public Data with Private Endpoints

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/articles").permitAll()
    .requestMatchers(HttpMethod.GET, "/articles/*").permitAll()
    .requestMatchers(HttpMethod.POST, "/articles")
        .hasAuthority("article:write")
    .anyRequest().authenticated()
);
~~~

`requestMatchers` patterns follow the matcher semantics chosen by Spring Security for the actual stack/configuration. Always test exact URLs, methods, and edge cases; do not assume a wildcard matches every path depth in all matchers.

## 11. How Does WebFlux Use `permitAll`?

For Spring WebFlux, the corresponding configuration uses `SecurityWebFilterChain` and `ServerHttpSecurity.authorizeExchange(...)`:

~~~java
// Illustrative configuration snippet, placed in a Spring WebFlux application.
@Bean
SecurityWebFilterChain springSecurityFilterChain(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers(HttpMethod.GET, "/public/ping").permitAll()
            .pathMatchers("/api/**").authenticated()
            .anyExchange().denyAll()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

Relevant imports include `org.springframework.security.web.server.SecurityWebFilterChain`, `org.springframework.security.config.web.server.ServerHttpSecurity`, `org.springframework.security.config.Customizer`, `org.springframework.http.HttpMethod`, and `org.springframework.context.annotation.Bean`.

**Semantic similarity:** Public endpoints do not require authz at the specified rule, while other WebFilters/security integrations can still apply.

**API differences:** Servlet uses `SecurityFilterChain` + `authorizeHttpRequests` + `requestMatchers`; WebFlux uses `SecurityWebFilterChain` + `authorizeExchange` + `pathMatchers`. Do not mix both DSLs in the same configuration. In reactive code, authentication information is carried via Reactor Context and read through `ReactiveSecurityContextHolder` when needed; `permitAll` does not change this principle.

## 12. Checklist Before Opening a Public Endpoint

Before adding `permitAll`, answer four technical questions:

1. **URL/method scope:** Should only `GET /public/ping` be public, or `POST /public/**` as well? If they differ, separate matchers by method.
2. **Other protection layers:** Does the endpoint modify data, use cookies/sessions, accept Bearer tokens, or require CORS? Check CSRF/authentication filters/CORS as separate policies.
3. **Data and business logic:** Could the public endpoint return PII, internal content, cross-tenant data, or require rate limiting? Public authorization does not mean all data is safe to expose.
4. **Testing:** Test requests **with no credentials**, requests with valid/invalid credentials where applicable, disallowed HTTP methods, and the fallback rule.

If it is a third-party webhook endpoint, being public at the `authenticated()` level may be necessary, yet **does not mean accepting requests from any sender**. You must verify signatures/HMAC or the trust mechanism specified by the provider at the appropriate layer and handle replay according to policy. Do not turn a webhook into an unverified public endpoint just because it does not use session login.

## 13. Common Mistakes

| Mistake | Impact | Fix |
| --- | --- | --- |
| Putting `/**.permitAll()` before protected rules | Broad matcher lets internal endpoints through | Place specific matchers first, safe fallback last |
| Using `web.ignoring()` for assets just to load CSS before login | Bypasses security headers and Spring Security filters | Use `permitAll()` for assets that need public access |
| Thinking `permitAll()` disables CSRF | Public POST still returns `403` | Understand CSRF is an independent filter; configure per threat model |
| Thinking `permitAll()` always returns `200` | 404, 405, controller errors, invalid credentials can still happen | Check each request-processing layer |
| Placing a permit rule in the wrong `SecurityFilterChain` | Rule is never applied | Check `securityMatcher` and chain order |
| Using an overly broad pattern like `/actuator/**` | May expose management information | Expose only `/actuator/health` when needed |
| Testing only with a logged-in browser | Cannot verify whether the endpoint is truly public | Test anonymously with MockMvc/curl |
| Omitting the HTTP method | May expose POST/DELETE when only public GET was intended | Use matchers with `HttpMethod` |
| Public URL while service still requires `@PreAuthorize` | API returns 403 despite HTTP permit rule | Align policies across layers and test end-to-end |
| Believing `permitAll` creates the endpoint | URL can return 404/405 | Create the actual controller/handler/static mapping |

## 14. Self-Check Questions

**Question 1.** If `GET /public/ping` has `permitAll`, can an unauthenticated client call it?

**Answer:** It can pass the HTTP authorization step without logging in. The request still must pass the applicable filters and succeed in the controller.

**Question 2.** Why does `POST /public/feedback` have `permitAll` yet return `403`?

**Answer:** When CSRF protection applies, `POST` may require a CSRF token. `permitAll` only allows access at the authorization layer; it does not disable `CsrfFilter`.

**Question 3.** Is `permitAll` the same as `web.ignoring()`?

**Answer:** No. `permitAll` is a request authorization rule inside a security chain; `web.ignoring()` bypasses the entire Spring Security chain for the ignored URLs.

**Question 4.** Why is placing `requestMatchers("/**").permitAll()` before `requestMatchers("/admin/**").hasRole("ADMIN")` dangerous?

**Answer:** Because the `/**` matcher matches first, `/admin/**` is permitted by the broad rule; the admin rule placed afterward no longer takes effect for that request.

**Question 5.** When there are two `SecurityFilterChain` beans, why might `permitAll` in chain B not apply to `/api/public/ping`?

**Answer:** If chain A is selected first via `securityMatcher("/api/**")`, only the authorization rules in chain A apply to that request.

**Question 6.** Why should you avoid making `/actuator/**` public just to open the health probe?

**Answer:** That wildcard can include other management endpoints. Open only the specific endpoint allowed to be exposed, such as `GET /actuator/health`, and verify the actual Actuator configuration.

## 15. Summary and References

`permitAll()` **opens access at a specific authorization step**. It is the natural choice for public endpoints, pages, and resources because it keeps requests inside the Spring Security chain. To use it safely, choose matchers with exact URLs and methods, order rules specifically, maintain a protective fallback, and verify CSRF, authentication, CORS, method security, and relevant token-validation mechanisms.

Further reading from the official documentation:

- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Security Filters](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Security — Form Login](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html)
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
