# permitAll Differs from Bypassing the Entire Security Chain

> **Scope:** Spring Security Servlet/Spring MVC, Java 17+, Spring Boot 3.x, and Spring Security 6.x. This lesson explains why **permitAll()** allows access to an endpoint while **keeping the request inside the SecurityFilterChain**, whereas **web.ignoring()** or a request matching no chain can cause Spring Security to **skip its protective filters**. The lesson includes Lambda DSL configurations, runnable examples, and tests proving differences in security headers, CSRF, authentication, and authorization.

## 1. One Sentence to Understand Before Configuring

When making **GET /public** public, these two approaches might appear to return the same **200 OK**:

~~~java
// Approach A: stays inside the SecurityFilterChain
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public").permitAll()
    .anyRequest().authenticated()
);
~~~

~~~java
// Approach B: bypasses Spring Security filters for matched requests
@Bean
WebSecurityCustomizer ignoringExample() {
    return web -> web.ignoring().requestMatchers("/public");
}
~~~

The two snippets above are **separate comparisons only**, not a recommended configuration to apply simultaneously to the same endpoint. They carry **different security semantics**:

- **permitAll():** an **authorization** rule stating that the matched request needs no granted authority to proceed. It **does not remove the request from the filter chain**. Other filters in the chain can still process the request.
- **web.ignoring():** a **WebSecurity**-level rule instructing Spring Security to bypass matching requests. Filters **inside the Spring Security chain** do not run for those requests; Spring Security does not add the security headers supplied by its filters.
- **Matching no SecurityFilterChain:** can also leave a request unprotected by Spring Security, though for a different reason than an authorization permitAll rule. This is a coverage bug that can appear when **securityMatcher(...)** is scoped too narrowly.

**Technical takeaway to verify:** "Public" does not mean "unprotected." An endpoint permitting anonymous callers may still need **security headers, CSRF protection, CORS integration, exception handling, request context**, and other protective filters according to configuration.

## 2. Three Questions That Determine an HTTP Request's Path

For **GET /public**, analyze across three layers:

1. **Does the request enter Spring Security?** The servlet layer passes requests through DelegatingFilterProxy and FilterChainProxy; if the request is matched by web.ignoring or no chain matches, Spring Security chain filters do not run.
2. **If it enters, which SecurityFilterChain does it belong to?** Each chain has a matcher; FilterChainProxy picks the first matching chain by priority order.
3. **Inside the selected chain, which authorization rule applies?** AuthorizationFilter queries AuthorizationManager. **permitAll()** decides only this step.

~~~text
Client request
    |
    v
Servlet container
    |
    v
DelegatingFilterProxy -> FilterChainProxy
    |
    +-- web.ignoring or no matching chain?
    |       |
    |       +--> Do not run Spring Security chain filters
    |             |
    |             +--> Servlet chain / DispatcherServlet / application
    |
    +-- Matching SecurityFilterChain found
            |
            +--> HeaderWriterFilter, SecurityContext, CSRF, ...
            +--> Authentication filter if mechanism is enabled
            +--> ExceptionTranslationFilter
            +--> AuthorizationFilter
                     |
                     +-- permitAll() rule
                     |       |
                     |       +--> No authorization required;
                     |             proceed to application
                     |
                     +-- authenticated()/hasRole(...) rule
                     |       |
                     |       +--> Verify Authentication and authorities
                     |
                     +-- denyAll() --> deny request
~~~

The diagram above illustrates **responsibilities and flow**, not a complete, fixed ordering of every filter. An actual chain contains only filters corresponding to its configuration. A filter may terminate the response early without invoking subsequent filters; **permitAll does not guarantee the controller will execute** if another filter blocks the request.

### 2.1. securityMatcher Differs from requestMatchers

**securityMatcher("/api/**")** selects the **SecurityFilterChain scope**. **requestMatchers("/api/ping").permitAll()** defines a **rule within that chain's scope**.

~~~java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/ping").permitAll()
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults());

    return http.build();
}
~~~

The snippet above is **illustrative only**, requiring a configuration class and imports. A request to **/web/account** does not match **securityMatcher("/api/**")**; apiChain's **anyRequest()** rule **does not apply** to it. If no other chain accepts /web/account, Spring Security does not protect that request.

For applications with multiple chains, a **fallback chain** is needed to cover all remaining URLs the application intends to protect. Do not use **anyRequest().denyAll()** in a restricted chain and assume it covers every URL in the system.

## 3. Accurately Comparing permitAll, ignoring, and Other Exceptions

| Mechanism | Configuration location | Authorization rule | Spring Security filters for matched request | Security headers added by Spring Security |
| --- | --- | --- | --- | --- |
| **permitAll()** | authorizeHttpRequests | Allows matched request | **Still run** per chain | **May be added** per headers config |
| **authenticated()** | authorizeHttpRequests | Requires valid Authentication | **Still run** | **May be added** |
| **denyAll()** | authorizeHttpRequests | Denies at authorization step | **Still traverses filters prior to denial** | **May be added** |
| **web.ignoring()** | WebSecurityCustomizer/WebSecurity | **Chain rules not evaluated** | **Bypassed** for matched requests | **Not added by Spring Security filters** |
| **No matching chain** | securityMatcher scope of chains | **No rule applies** | **Chain filters do not run** | **Not added by Spring Security filters** |
| **csrf.ignoringRequestMatchers(...)** | CsrfConfigurer inside HttpSecurity | **Does not alter authorization rules** | **Still runs chain**, skips only CSRF check for matched requests | **May still be added** |
| **requestMatchers(...).permitAll() in a specific chain** | authorizeHttpRequests of that chain | Public **within the selected chain** | **Still runs the selected chain** | Per that chain's configuration |

**Read the table within its exact scope:** "Spring Security does not add headers" does not mean every real-world response lacks security headers. A reverse proxy, API gateway, or a servlet filter **outside Spring Security** may still add headers. The table describes only what Spring Security itself does.

**csrf.ignoringRequestMatchers** and **web.ignoring** differ greatly despite both containing "ignoring":
- **csrf.ignoringRequestMatchers(...)** exempts only **one CSRF check** inside a chain that keeps all other filters.
- **web.ignoring()** bypasses the **entire Spring Security filter chain** for matched requests.

Do not treat the two mechanisms as interchangeable.

## 4. What Does permitAll() Actually Skip?

**permitAll** belongs to authorization configuration, for example:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/public").permitAll()
    .requestMatchers(HttpMethod.GET, "/admin").hasRole("ADMIN")
    .anyRequest().authenticated()
)
~~~

When GET /public reaches **AuthorizationFilter**, the rule allows it **without needing to read the user's authorities** to decide. Since Spring Security 6, for a **permitAll** rule, authorization **does not need to retrieve Authentication from HttpSession** solely to check permissions. This is also why Spring Security documentation recommends permitAll for static resources instead of trying to bypass filters for performance.

However, other components remain responsible:

- **HeaderWriterFilter** can add security headers such as **X-Content-Type-Options: nosniff** and **X-Frame-Options: DENY** according to defaults/configuration.
- **CsrfFilter** still checks requests using unsafe HTTP methods, such as POST, when CSRF protection is enabled.
- **BasicAuthenticationFilter** may process a sent Authorization Basic header even when the target URL has permitAll. Wrong credentials can be rejected **before** the request reaches AuthorizationFilter.
- **CorsFilter** or Spring Security CORS integration (if configured) can still handle CORS preflight/responses.
- **SecurityContextHolderFilter**, session/context strategies, and other protective filters continue operating per the chain.
- **ExceptionTranslationFilter** can translate AuthenticationException/AccessDeniedException from downstream steps into appropriate HTTP responses.
- **LogoutFilter, OAuth2 login callbacks**, or specialized endpoint filters still execute their behavior when requests match their URLs.

Therefore, saying **"permitAll disables authentication"** is inaccurate. It only states that **this authorization rule permits the request to proceed without requiring the principal to hold specific authorities**. An authentication mechanism may still be executed by an earlier filter or required by another component.

### 4.1. Public GET and Public POST Can Return Different Statuses

Suppose we declare:

~~~java
.requestMatchers(HttpMethod.GET, "/public").permitAll()
.requestMatchers(HttpMethod.POST, "/public/submit").permitAll()
~~~

With default Servlet CSRF protection:

- **GET /public** does not require a CSRF token; if the controller works it can return **200**.
- **POST /public/submit** without a valid CSRF token is typically rejected by **CsrfFilter with 403**, **even though** the authorization rule is **permitAll**.
- **POST /public/submit** with a valid CSRF token can reach the controller and return **200**.
- If a custom CSRF policy differs, outcomes may differ; never assume one fixed status across all applications.

This is the sharpest difference between **opening URL access** and **removing all protections**. CSRF is a request-protection mechanism, not a role permission.

### 4.2. Public Endpoint with Wrong Basic Header Can Still Be Rejected

When an app enables HTTP Basic, a **GET /public** request with no Authorization header can return 200. Yet if that request **carries wrong Basic credentials**, BasicAuthenticationFilter may intercept the credentials, attempt authentication, and return **401** via the authentication entry point. **permitAll does not guarantee that attached credentials will be ignored**.

There is no contradiction: a public URL does not require a user to log in, yet the application can still detect and reject an invalid authentication attempt in an earlier filter. Verify the specific behavior of your chain and authentication mechanism instead of treating permitAll as a switch disabling all filters.

## 5. Security Headers Are an Easy-to-Observe Example

Servlet Spring Security includes default security headers to mitigate common risks. HeaderWriterFilter is part of the chain managing them. Common headers include:

| Header | Meaning | Testing notes |
| --- | --- | --- |
| **X-Content-Type-Options: nosniff** | Discourages browsers from MIME-sniffing contrary to Content-Type | Usually present by default in Servlet Spring Security |
| **X-Frame-Options: DENY** | Restricts framing to mitigate clickjacking | Default is typically DENY; can be customized |
| **Cache-Control** and related headers | Helps limit caching of sensitive responses by default | May be overridden by application/proxy |
| **Strict-Transport-Security** | Instructs browsers to use HTTPS for the declared duration | Applies only over **HTTPS**; do not expect it on HTTP localhost |
| **Content-Security-Policy** | Restricts script/style/resource origins | Not automatically configured by Spring Security with an app-specific policy |
| **Referrer-Policy** | Controls referrer data sent outbound | Must be selected and configured per needs |

**Do not claim every header in the table appears by default.** Headers can be customized, disabled, or varied by version/infrastructure. When demonstrating the difference between permitAll and ignoring, check a concrete default header such as **X-Content-Type-Options: nosniff** in a demo app without proxies or custom header config.

With **web.ignoring()**, Spring Security does not run HeaderWriterFilter for ignored requests. Consequently, there is **no longer any guarantee** that Spring Security's headers are written to that response. A CSS/JS asset should also carry protective headers consistent with the application's policy.

### 5.1. Why Does Documentation Recommend permitAll for Static Resources?

Preferred configuration snippet:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/css/**", "/js/**", "/images/**").permitAll()
    .anyRequest().authenticated()
);
~~~

Static files are still served normally while retaining the chain's security filters/headers. In Spring Security 6, a permitAll decision **does not need to fetch Authentication from the session for the authorization step**, substantially reducing a historical performance motivation for ignoring.

**Do not use web.ignoring() merely because a CSS file is public.** Be especially careful if a static path contains user-uploaded files or dynamic content: beyond authentication, consider content type, CSP, caching, access control, and storage policies.

## 6. Runnable Example: permitAll Still Keeps Headers and CSRF

This example uses **Spring Boot 3.x, Spring Security 6.x, Java 17+, and Spring MVC**. The application includes:
- **GET /public**: allows anonymous access.
- **POST /public/submit**: also permitAll, yet still subject to **CSRF**.
- **GET /private**: requires authentication.
- **GET /admin**: requires **ROLE_ADMIN**.
- **GET /unlisted**: has a controller but no allow rule.
- **GET /css/site.css**: static asset with permitAll that still receives security headers.

Section 7 adds **a test-only configuration** to compare against web.ignoring; in normal runtime, the application intentionally leaves no endpoint outside Spring Security.

### 6.1. Dependencies and File Layout

Using a Spring Boot 3.x project with Gradle Wrapper/plugin and Java 17+, add to the existing **build.gradle**:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

This is a dependencies block, not a complete build.gradle. Create these files:

~~~text
src/main/java/com/example/permitdemo/
  PermitDemoApplication.java
  SecurityConfig.java
  DemoController.java

src/main/resources/static/css/
  site.css

src/test/java/com/example/permitdemo/
  PermitAllTest.java
  IgnoringExperimentTest.java
~~~

### 6.2. PermitDemoApplication.java

~~~java
package com.example.permitdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PermitDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(PermitDemoApplication.class, args);
    }
}
~~~

### 6.3. SecurityConfig.java

~~~java
package com.example.permitdemo;

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
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/css/**").permitAll()
                .requestMatchers(HttpMethod.POST, "/public/submit").permitAll()
                .requestMatchers(HttpMethod.GET, "/private").authenticated()
                .requestMatchers(HttpMethod.GET, "/admin").hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice123"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin123"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(alice, admin);
    }
}
~~~

**Notable points:**

1. No **WebSecurityCustomizer** is used in the normal running application configuration.
2. The three permitAll rules for public GET, static CSS, and public POST **open only the authorization step**; they remain inside the SecurityFilterChain.
3. **csrf.disable()** is not called; CsrfFilter continues protecting POST when a valid CSRF token is absent.
4. **httpBasic(...)** lets curl/tests send username/password to test protected endpoints.
5. **anyRequest().denyAll()** blocks undeclared endpoints, even if a controller mapping exists.
6. **PasswordEncoder** uses BCrypt. Demo passwords are for localhost only; real systems need proper account and secret management.

**We do not call .sessionManagement(STATELESS)** in this demo because the CSRF tests rely on the default mechanism and need to highlight the independence between authentication/authorization/CSRF. Whether an API uses sessions, Basic, or Bearer and what CSRF policy it adopts are separate architectural decisions; the word "API" does not mandate disabling CSRF.

### 6.4. DemoController.java

~~~java
package com.example.permitdemo;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public String publicPage() {
        return "public";
    }

    @PostMapping("/public/submit")
    public String publicSubmit() {
        return "submitted";
    }

    @GetMapping("/private")
    public String privatePage(Authentication authentication) {
        return "private:" + authentication.getName();
    }

    @GetMapping("/admin")
    public String adminPage() {
        return "admin";
    }

    @GetMapping("/unlisted")
    public String unlisted() {
        return "must-not-be-visible";
    }
}
~~~

The **/unlisted** endpoint exists from MVC's perspective yet is denied by fallback. The **/public/submit** endpoint mutates no real data, returning only a string to illustrate CSRF verification. In production, side-effecting endpoints need explicit policies and CSRF defenses suited to the client type.

### 6.5. site.css — Static Resource

File **src/main/resources/static/css/site.css**:

~~~css
body { font-family: sans-serif; }
~~~

Spring Boot MVC serves the static resource at **/css/site.css** when standard static resource handling is enabled. Because the path has **permitAll**, anonymous users can fetch the file; and because it still passes through the SecurityFilterChain, default security headers apply to the response.

### 6.6. Testing Manually with curl

From the project directory with the Gradle Wrapper:

~~~bash
./gradlew bootRun
# Windows PowerShell or cmd:
gradlew.bat bootRun
~~~

From another terminal, try:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/css/site.css
curl -i -X POST http://localhost:8080/public/submit
curl -i http://localhost:8080/private
curl -i -u alice:alice123 http://localhost:8080/private
curl -i -u alice:alice123 http://localhost:8080/admin
curl -i -u admin:admin123 http://localhost:8080/admin
curl -i -u admin:admin123 http://localhost:8080/unlisted
~~~

**Expected** results with the demo app and no reverse proxy or custom handlers:

| Request | HTTP | Body or meaning |
| --- | --- | --- |
| GET /public (anonymous) | **200** | **public**, with security headers |
| GET /css/site.css (anonymous) | **200** | CSS content, with security headers |
| POST /public/submit, no CSRF | **403** | CsrfFilter denies even though POST has permitAll |
| GET /private (anonymous) | **401** | HTTP Basic requests credentials |
| GET /private (alice) | **200** | **private:alice** |
| GET /admin (alice) | **403** | ROLE_USER is insufficient for ROLE_ADMIN |
| GET /admin (admin) | **200** | **admin** |
| GET /unlisted (admin) | **403** | Fallback denyAll blocks before MVC controller |

On GET /public, check the response for the **X-Content-Type-Options: nosniff** header. If testing behind a reverse proxy or an app with custom header settings, results may differ. Do not rely on 403/401 response body text as a fixed contract unless error handling is explicitly configured.

**Warning when running with real credentials:** Basic sends passwords in decodable Base64; use HTTPS over networks and avoid putting passwords into shell history/logs. Demo passwords are for local learning only.

## 7. Integration Tests Distinguishing permitAll and ignoring

The following tests do not call controllers directly to guess outcomes. They use **MockMvc** running through Spring Security's filters, proving that header writers, CSRF, and authorization actually executed.

### 7.1. PermitAllTest.java: Verifying the Securely Configured App

File **src/test/java/com/example/permitdemo/PermitAllTest.java**:

~~~java
package com.example.permitdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PermitAllTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointHasSecurityHeader() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"))
            .andExpect(header().string("X-Content-Type-Options", "nosniff"));
    }

    @Test
    void permittedStaticCssStillHasSecurityHeader() throws Exception {
        mvc.perform(get("/css/site.css"))
            .andExpect(status().isOk())
            .andExpect(header().string("X-Content-Type-Options", "nosniff"));
    }

    @Test
    void permittedPostStillRequiresCsrf() throws Exception {
        mvc.perform(post("/public/submit"))
            .andExpect(status().isForbidden());

        mvc.perform(post("/public/submit").with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("submitted"));
    }

    @Test
    void privateEndpointRequiresAuthentication() throws Exception {
        mvc.perform(get("/private"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/private")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isOk())
            .andExpect(content().string("private:alice"));
    }

    @Test
    void roleIsCheckedAfterAuthentication() throws Exception {
        mvc.perform(get("/admin")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/admin")
                .with(httpBasic("admin", "admin123")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin"));
    }

    @Test
    void unknownRouteWithControllerIsDenied() throws Exception {
        mvc.perform(get("/unlisted")
                .with(httpBasic("admin", "admin123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void invalidBasicCredentialsCanFailOnPublicRoute()
            throws Exception {
        mvc.perform(get("/public")
                .with(httpBasic("alice", "wrong")))
            .andExpect(status().isUnauthorized());
    }
}
~~~

How to interpret these tests:

- **publicEndpointHasSecurityHeader** shows permitAll does not skip HeaderWriterFilter.
- **permittedPostStillRequiresCsrf** proves that **public access does not disable CSRF**.
- **invalidBasicCredentialsCanFailOnPublicRoute** illustrates that an authentication filter can still process credentials sent to a public endpoint; when invalid, it can return 401.
- The **private/admin/unlisted** tests show opening public endpoints does not drop policies for the rest.
- **httpBasic(...)** in Spring Security Test creates an Authorization header; **csrf()** adds a valid CSRF token via MockMvc support. They are test request post-processors, not production data-handling logic.

### 7.2. IgnoringExperimentTest.java: Proving the Consequence of web.ignoring

To compare with the unrecommended approach, add **a configuration that exists only inside the test**. The main application configuration in Section 6 contains no web.ignoring, avoiding accidentally introducing a bypass into normal runtime.

File **src/test/java/com/example/permitdemo/IgnoringExperimentTest.java**:

~~~java
package com.example.permitdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.security.config.annotation.web.configuration.WebSecurityCustomizer;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@Import(IgnoringExperimentTest.IgnoreOnlyPublic.class)
class IgnoringExperimentTest {

    @Autowired
    MockMvc mvc;

    @TestConfiguration
    static class IgnoreOnlyPublic {

        @Bean
        WebSecurityCustomizer ignorePublicForExperiment() {
            return web -> web.ignoring().requestMatchers("/public");
        }
    }

    @Test
    void ignoredRouteDoesNotGetSpringSecurityHeaders()
            throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"))
            .andExpect(header().doesNotExist("X-Content-Type-Options"));
    }
}
~~~

**Why keep this configuration test-only?** This lesson wants to observe the effect of **web.ignoring** without placing a bypass in the main application. In this test:

1. Spring Boot builds a context with the extra **WebSecurityCustomizer**, ignoring only **/public**.
2. The controller still handles GET /public and returns **200**.
3. Spring Security's security header filter does not run for ignored requests, so the test asserts that **X-Content-Type-Options** is absent.
4. This conclusion holds for **a demo app with no proxy or other custom header filter**. If another component adds that header, distinguish its source.

That is why Spring Security docs prefer **permitAll** for static resources. This test intentionally uses an unrecommended approach to **observe the difference**, not as configuration to carry into production.

### 7.3. Running Tests

From the project root:

~~~bash
./gradlew test
# Windows:
gradlew.bat test
~~~

This is the **expected test suite for Spring Boot 3.x + Spring Security 6.x**, not results already executed in a learning environment. If using Spring Boot 4 or Spring Security 7, verify exact versions, test packages, and configuration APIs. Never assume a 200 status test alone proves an endpoint is properly protected; assert headers and negative cases as shown above.

## 8. How to Use web.ignoring When Truly Necessary

**WebSecurityCustomizer** is a WebSecurity-level configuration entry point (distinct from HttpSecurity). Basic syntax example:

~~~java
@Bean
WebSecurityCustomizer webSecurityCustomizer() {
    return web -> web.ignoring()
        .requestMatchers("/some-special-resource/**");
}
~~~

The snippet above only demonstrates the API; **copying it for normal resources is not recommended**. Placing a path in **web.ignoring** declares that **all Spring Security protective filters may be skipped** on that path, including:

- Authentication filters and chain SecurityContext loading/saving.
- Authorization rules such as **authenticated()**, **hasRole()**, **denyAll()**.
- The chain's **CsrfFilter**, if applicable.
- **HeaderWriterFilter** and security headers provided by Spring Security.
- CORS/exception handling/security behaviors tied to the chain.

**Exact scope to state:** "bypassing the entire security chain" here means **Spring Security's filter chain**, not turning off the Servlet container, Spring MVC, web server, CDN, reverse proxy, all application filters, or external infrastructure controls.

Therefore, if you have a specialized need to ignore requests, prove that disabling all those protective layers is intentional. In most web apps, **permitAll() is easier to maintain and safer**.

### 8.1. Static Resources

Prefer writing:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/assets/**").permitAll()
    .anyRequest().authenticated()
);
~~~

Instead of:

~~~java
// Comparison only; normally not preferred.
web.ignoring().requestMatchers("/assets/**");
~~~

The permitAll configuration still serves CSS/JS/image assets while keeping Spring Security's filters and headers intact.

### 8.2. Health Checks and Public Resources

A **GET /actuator/health** or **GET /healthz** endpoint may need anonymous access by a load balancer. If you choose to expose it, place an explicit path/method rule in the appropriate chain and preserve headers. Be careful with Actuator: health/info/metrics/env do not share the same sensitivity; never allow all of **/actuator/** just to expose a health check.

Similarly, **/login**, **/register**, **/forgot-password**, and **/csrf** may need pre-login access. **permitAll()** fits better than a broad bypass, because those flows are precisely where CSRF, headers, or other filters must operate.

### 8.3. CORS Preflight

A browser may send an **OPTIONS preflight** before calling an API with an Authorization header. Proper CORS configuration should usually be integrated so preflight requests are handled before authorization where appropriate:

~~~java
http.cors(Customizer.withDefaults());
~~~

This **snippet** requires an actual CORS policy, such as a CorsConfigurationSource or MVC configuration recognized by Spring Security. **Do not use web.ignoring("/api/**")** to work around a preflight error; that strips protection from the entire API. Define allowed origins, methods, headers, and credentials per client requirements.

**CORS does not replace authentication or authorization**. Even when browsers may read cross-origin responses, the backend must still verify principals and data permissions.

## 9. CSRF: Three Commonly Confused Configurations

Suppose an application has **POST /public/submit** and browsers use sessions/cookies.

**Approach 1 — permitAll in authorization:**

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.POST, "/public/submit").permitAll()
    .anyRequest().authenticated()
)
~~~

Requests still pass through CsrfFilter and need a token if CSRF configuration requires one.

**Approach 2 — exempt only the CSRF check for one path:**

~~~java
.csrf(csrf -> csrf
    .ignoringRequestMatchers("/webhook/external")
)
~~~

Requests still traverse the Spring Security chain and remain subject to authentication/authorization/headers. Use this only when the endpoint has proper authentication and replay defenses, such as a securely verified HMAC-signed webhook; it is not a blanket default for every REST API.

**Approach 3 — bypass the Spring Security filter chain:**

~~~java
@Bean
WebSecurityCustomizer ignoring() {
    return web -> web.ignoring().requestMatchers("/webhook/external");
}
~~~

Approach 3 skips far more mechanisms than needed. If you only want a CSRF exception, never substitute web.ignoring.

**Security reminder:** CSRF matters primarily when browsers can attach credentials automatically (cookies/sessions and certain HTTP authentication). For APIs authenticating strictly via Bearer tokens explicitly placed in Authorization headers by the client, CSRF design differs; however, tokens stored in auto-sent cookies still require evaluation. Never disable CSRF automatically just because an endpoint returns JSON or is called "REST."

## 10. HTTP Status Alone Does Not Tell Which Filters Ran

| Scenario | Typical response | Proof that the request bypassed the chain? |
| --- | --- | --- |
| Anonymous GET /public with permitAll | **200** | **No**; chain still ran |
| Anonymous GET /public with web.ignoring | **200** if controller succeeds | Possibly ignored; inspect chain/logs, not just status |
| Anonymous GET /private with Basic | **401** | Protected request; entry point demanded credentials |
| Logged-in USER GET /admin needing ADMIN | **403** | Authenticated, but lacking authority |
| Anonymous POST /public/submit permitAll, no CSRF | **403** | CsrfFilter can still block |
| GET /missing permitAll with no controller/resource | **404** | Allowing access does not create an endpoint |
| Request matching no chain, controller exists | Possibly **200** | Unprotected by Spring Security if no chain matched |
| Request with wrong HTTP method | Possibly **403**, **404**, or **405** | Depends on authorization, CSRF, and MVC mappings |

When debugging, trace causes layer by layer: **chain RequestMatcher -> authentication filter -> CSRF/CORS -> authorization rule -> controller/service**. A 200 status does not prove security is right, and a 403 does not necessarily mean a role rule (it could be CSRF).

### 10.1. permitAll with Error/Forward Dispatches

Servlets can produce **ERROR** or **FORWARD** dispatches when handling errors or views. In modern Spring Security versions, authorization can apply to dispatcher types as configured. If you want to allow **ERROR/FORWARD** strictly as needed, you can configure:

~~~java
.authorizeHttpRequests(auth -> auth
    .dispatcherTypeMatchers(DispatcherType.ERROR, DispatcherType.FORWARD)
        .permitAll()
    .requestMatchers("/public").permitAll()
    .anyRequest().authenticated()
)
~~~

This is a **snippet** requiring **jakarta.servlet.DispatcherType** and careful evaluation of app needs. Permitting a dispatcher type at the authorization step **does not mean bypassing all filters**; nor should displaying error pages ever justify opening business endpoints.

## 11. Why You Should Not Optimize by Ignoring Broadly

Historical reasons people ignored static resources commonly included:

- Worrying each static request would load the session/principal from a database.
- Wanting to avoid SecurityFilterChain overhead.
- Wanting one configuration for all public CSS/JS/images.

In Spring Security 6, **permitAll/denyAll authorization does not need to fetch Authentication from the session solely to decide**, so the performance argument for ignoring is usually much weaker than before. Filter and infrastructure costs still exist, yet you cannot conclude "ignoring is always faster so it is equally safe."

To evaluate performance properly:

1. Profile real request paths to see which filters/DB/caches actually cost time.
2. Use **permitAll** for static assets and measure performance.
3. Optimize static resource caching, CDN, compression, and servlet handling sensibly.
4. Verify security headers and cache policies remain intact.
5. Change chain-bypassing behavior only with a measured justification tested against real behavior.

**Performance optimization must never silently shift security boundaries.**

## 12. Multiple SecurityFilterChains: Avoiding Unmatched-Chain Gaps

Suppose an application has a chain solely for **/api/**:

~~~java
@Bean
@Order(1)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/ping").permitAll()
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults());
    return http.build();
}
~~~

If this is the only chain, requests outside **/api/** are not protected by this chain. To add a fallback, add another chain:

~~~java
@Bean
@Order(2)
SecurityFilterChain fallback(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().denyAll()
        );
    return http.build();
}
~~~

These two snippets are for **multi-chain architecture**, not additions to paste into the Section 6 demo. They require imports for **Bean**, **Order**, **HttpSecurity**, **SecurityFilterChain**, and **Customizer**. If a denyAll fallback is used, add intentional exceptions for static assets, login, error dispatches, Actuator, CORS, and framework endpoints that genuinely must be served.

Key distinctions:
- **permitAll:** request stays in the selected chain and passes through its filters.
- **web.ignoring:** skips Spring Security filters for ignored requests.
- **Request matching no chain:** request goes unprotected due to missing coverage, even if denyAll is set inside other chains.

Large projects must test URLs **inside and outside** every matcher, as well as verify **@Order** precedence.

## 13. Common Mistakes

### 13.1. Thinking permitAll Means "Does Not Go Through Spring Security"

False. permitAll is an authorization decision. Filters before or separate from authorization can still execute. A permitAll POST can still be blocked by CSRF; security headers can still be written.

### 13.2. Using web.ignoring for CSS/JS Without Considering Headers

When Spring Security skips HeaderWriterFilter, it adds no headers to ignored responses. Use permitAll for static resources unless you have a clear reason to skip the entire chain.

### 13.3. Setting permitAll on All /api/** to Fix 401 Errors

This can expose private endpoints. Identify the broken authentication mechanism, credentials, or authorization rule; open only exact public resources, scoped by HTTP method if needed.

### 13.4. Disabling CSRF Because a permitAll POST Returns 403

**CsrfFilter** defends against forged requests independently of permitAll rules. Before changing policy, verify whether browsers auto-attach session cookies/Basic credentials and what side effects the endpoint has.

### 13.5. Confusing csrf.ignoringRequestMatchers with web.ignoring

One skips only CSRF validation; the other skips Spring Security filters. Use only CSRF exemptions justified by the threat model and thoroughly test remaining authentication/authorization.

### 13.6. Putting anyRequest().permitAll at the End Without Classifying Endpoints

This easily exposes new routes unintentionally. For APIs with sensitive data, prefer an explicit allowlist and an authenticated/denyAll fallback per policy.

### 13.7. Setting securityMatcher Too Narrowly and Thinking denyAll Protects the Whole App

One chain's denyAll does not cover URLs outside its matcher. Add a fallback chain matching all remaining requests if you want the entire servlet application protected.

### 13.8. Thinking permitAll Ignores Invalid Credentials

When HTTP Basic is enabled, invalid credentials can be rejected by the authentication filter before reaching authorization. If you need public requests with differing or invalid credentials handled differently, understand the filter mechanism and design intentionally.

### 13.9. Thinking Every 200/401/403 Has the Same Root Cause

A 200 only means the controller or infrastructure returned success, not that a chain ran; 401 usually means authentication; 403 usually means authorization or CSRF; 404 may mean no mapping exists. Check logs and layer-by-layer tests.

### 13.10. Serving Raw User-Uploaded Files on a Public Static Path

Even when a route has permitAll, evaluate object read permissions, MIME sniffing, executable content, caching, CSP, malware scanning, and path handling. Calling a file "static" does not make it safe when public.

### 13.11. Not Testing Spring Security Headers

Checking only that CSS/HTML bodies return 200 easily misses that the whole chain was bypassed. When changing config, test at least one critical protective header on public endpoints alongside response headers on sensitive endpoints.

### 13.12. Test Configuration Differing Unknowingly from Production

If tests use WebSecurityCustomizer to turn off the chain, security header/CSRF assertions may not reflect real runtime behavior. This lesson deliberately separates **IgnoringExperimentTest** as a clearly labeled experiment; production configuration still uses permitAll.

## 14. Checklist When Making an Endpoint Public

When exposing a public endpoint, answer:

1. **Does the endpoint really need to be public?** Open only the required path and HTTP method.
2. **Which SecurityFilterChain owns the request?** Could securityMatcher or @Order route it to another chain?
3. **Use permitAll or bypass the chain?** Default to **permitAll**.
4. **Are security headers still written?** Verify X-Content-Type-Options and headers the app genuinely needs.
5. **Does the endpoint have side effects?** POST/PUT/DELETE need CSRF and dedicated permission reviews, even when anonymous.
6. **Can an authentication filter process credentials?** Never assume permitAll disables Basic/Bearer processing.
7. **Is CORS preflight involved?** Handle origin/method/headers cleanly without stripping API protection.
8. **Is there a denyAll/authenticated rule for the rest?** Opening one public endpoint must not open others.
9. **Are error dispatches, Actuator, or static login assets affected?** Design narrow rules for necessary framework behavior.
10. **Are there negative tests?** Test anonymous, wrong credentials, missing roles, wrong HTTP methods, and undeclared endpoints.

### 14.1. Minimum Test Suite to Have

| What to prove | Request/test |
| --- | --- |
| Public endpoint stays in chain | GET /public returns 200 **and has X-Content-Type-Options** |
| Static asset still has headers | GET /css/site.css returns 200 and has security header |
| CSRF is not skipped by permitAll | POST /public/submit without CSRF returns 403 |
| Valid CSRF is processed | POST /public/submit with csrf() returns 200 |
| Private endpoint is protected | Anonymous GET /private returns 401 in Basic chain |
| Roles remain enforced | ROLE_USER calling GET /admin returns 403 |
| Fallback deny remains enforced | GET /unlisted even as ADMIN returns 403 |
| Ignoring has distinct consequence | In test-only ignore of /public, Spring Security's header is absent |

**The difference must be verified through filter behavior**, not merely asking "does the public URL return 200?"

## 15. Self-Check Questions

**Question 1.** Does setting **requestMatchers("/public").permitAll()** make the request bypass SecurityFilterChain?

**Answer:** No. It only allows it at the authorization step; security filters can still run.

**Question 2.** Why should **GET /css/site.css** use permitAll rather than web.ignoring?

**Answer:** The static file stays public while still receiving Spring Security's security headers. With ignoring, HeaderWriterFilter does not run for ignored requests.

**Question 3.** A POST endpoint has permitAll yet lacks a CSRF token and receives 403. Is that a contradiction?

**Answer:** No. permitAll is an authorization rule; CsrfFilter independently can still block unsafe methods.

**Question 4.** Can a public GET with a wrong Basic header receive 401?

**Answer:** Yes. If BasicAuthenticationFilter processes the sent credentials and authentication fails before AuthorizationFilter, the entry point can return 401.

**Question 5.** Does **csrf.ignoringRequestMatchers("/webhook")** remove security headers and authentication for /webhook?

**Answer:** No. It only exempts matching requests in the chain from CSRF validation; other filters and rules still apply.

**Question 6.** Only a **securityMatcher("/api/**")** chain exists, with anyRequest().denyAll(). Is /admin guaranteed to be blocked?

**Answer:** No. If /admin lies outside the chain and there is no fallback, it may not be protected by Spring Security.

**Question 7.** Two endpoints both return 200; does that prove they are protected equivalently?

**Answer:** No. One request might return 200 after passing through a permitAll chain, while the other returned 200 because it was ignored or matched no chain. Check filters/headers/logs.

**Question 8.** Does web.ignoring disable all Servlet container and proxy filters?

**Answer:** No. It skips Spring Security's protective filters for matched requests, not the entire HTTP infrastructure.

**Question 9.** What changed regarding session lookups when using permitAll in Spring Security 6?

**Answer:** Specifically the authorization step of permitAll does not need to fetch Authentication from the session just to allow access. Other filters/mechanisms may still use sessions depending on configuration and request.

**Question 10.** What is the right way to expose a health check publicly while keeping security headers?

**Answer:** Allow the exact health check URL/method via **permitAll** inside the right chain; keep sensitive actuator endpoints protected and verify real health responses.

## Official Documentation

- Spring Security 6.5 — **Authorize HttpServletRequests**, section **Favor permitAll over ignoring**: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- Spring Security — **Java Configuration / Choosing securityMatcher or requestMatchers**: https://docs.spring.io/spring-security/reference/servlet/configuration/java.html
- Spring Security — **Servlet Architecture / FilterChainProxy**: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security — **Security HTTP Response Headers**: https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html
- Spring Security — **Cross Site Request Forgery (CSRF)**: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Security — **HTTP Basic Authentication**: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html
- Spring Security — **Web Security Customizer API**: https://docs.spring.io/spring-security/site/docs/6.5.0/api/org/springframework/security/config/annotation/web/configuration/WebSecurityCustomizer.html

**Final takeaway:** **permitAll = permitted at the authorization step inside a SecurityFilterChain; web.ignoring = skipping Spring Security filters for matched requests**. Therefore, for normal public endpoints and static assets, **keep the chain and use permitAll**, while testing security headers, CSRF, authentication, and policies for remaining endpoints.
