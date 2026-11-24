# Replacing the Default Configuration with a SecurityFilterChain Bean in Spring Security

> **Context:** Spring Boot 3.x, Spring Security 6.x, Java 17+, and a **Servlet/Spring MVC** application. This topic is a key initialization milestone: moving from an application that merely added the Spring Security dependency to actively declaring which endpoints are public, which require login, which require specific privileges, and which authentication mechanisms to use. Spring Security WebFlux (reactive) APIs and configuration styles differ from Servlet.

## 1. Why Replace the Default Configuration?

When you add **spring-boot-starter-security** to a Spring Boot Servlet application without custom security configuration, Spring Boot/Spring Security provides a default web protection configuration. Typically, every request requires authentication; both **form login** and **HTTP Basic** are enabled, and Spring Boot may create an in-memory account with a random startup password (if no other authentication configuration causes that auto-configuration to back off).

Suppose an application has three endpoints:

- **GET /public**: public information page.
- **GET /me**: currently logged-in user's details.
- **GET /admin**: administrator functionality.

Without declared rules, the application by default does not know that **/public** should be open, **/admin** must require `ROLE_ADMIN`, or APIs should respond with HTTP Basic rather than a login redirect. All endpoints may simply require generic authentication. To express a policy matching business requirements, we define a **`SecurityFilterChain`** bean.

**Key point:** declaring a **`SecurityFilterChain`** bean stops Spring Boot from **creating its default web protection configuration**. Your new bean governs the corresponding filter chain. However, it **does not turn off Spring Security completely**, **does not create users/roles on its own**, **does not disable CSRF**, and **does not mean all authentication auto-configuration disappears**.

Spring Boot documentation distinguishes two things:
1. A **`SecurityFilterChain`** bean exists: Boot backs off from **default web application security settings**.
2. A **`UserDetailsService`**, **`AuthenticationProvider`**, or **`AuthenticationManager`** bean exists: Boot backs off from its default **`InMemoryUserDetailsManager`** user bean.

Therefore, if you only add a `SecurityFilterChain` without declaring any user/authentication source, in a simple Boot setup **the default generated user may still exist**. When building examples or real systems, declare an explicit identity source, then inspect bean states and startup logs.

## 2. What Is SecurityFilterChain and Where Does It Live?

A **`SecurityFilterChain`** is a chain of servlet filters protecting matched requests. You typically declare it as a bean by configuring **`HttpSecurity`** and calling **`http.build()`**. Spring Security uses **`FilterChainProxy`** to pick the matching chain and execute filters in the defined order.

~~~text
HTTP client
    |
    v
Servlet container
    |
    v
DelegatingFilterProxy ("springSecurityFilterChain")
    |
    v
FilterChainProxy
    |
    +--> Selects the first SecurityFilterChain matching the request
             |
             +--> Protection filters: headers, CSRF, context...
             +--> Authentication filters: Basic/form/Bearer... if enabled
             +--> ExceptionTranslationFilter
             +--> AuthorizationFilter
                         |
                         +--> ALLOW -> DispatcherServlet -> Controller
                         |
                         +--> DENY -> entry point / access denied handler
~~~

You do not manually create **`FilterChainProxy`** or register individual filters via Servlet APIs in a typical Spring Boot app. Spring Security/Boot handles servlet integration. Your application's job is building appropriate **`SecurityFilterChain` beans**.

A minimal bean looks like:

~~~java
@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
~~~

**This is an excerpt**, requiring imports for **`Configuration`**, **`Bean`**, **`HttpSecurity`**, **`SecurityFilterChain`**, **`Customizer`**, and a Spring Boot 3 project with the Spring Security dependency. It requires authentication for every request and enables Basic. Copying a rule without knowing which authentication/filters are enabled can cause clients to receive unexpected responses.

In Spring Security 6 Java configuration, **`SecurityFilterChain` + `HttpSecurity` + `authorizeHttpRequests`** is the standard declaration pattern. Older tutorials extending **`WebSecurityConfigurerAdapter`** are obsolete for Spring Security 6; write a `SecurityFilterChain` bean instead of extending that adapter.

## 3. Configuration Before and After: What Changes?

Compare two states of the same project.

**Before declaring SecurityFilterChain:**

~~~text
Spring Boot + spring-boot-starter-security
  |
  +--> Boot provides default web configuration
  |      - requires authenticated for normal requests
  |      - supports form login and HTTP Basic
  |
  +--> if no matching custom authentication source exists:
         creates default in-memory user and random password
~~~

**After declaring the application's SecurityFilterChain:**

~~~text
Spring Boot + spring-boot-starter-security
  |
  +--> finds application's SecurityFilterChain bean
  |      - Boot does not create default web SecurityFilterChain
  |      - rules and HTTP mechanisms are defined by the application
  |
  +--> authentication/user source is a separate config concern
         - generated user may still appear
         - or uses UserDetailsService / provider / OAuth2...
~~~

Example behavior changes:

| Request | With Typical Boot Default Config | After Adding Allow/Restrict Rules |
| --- | --- | --- |
| GET /public, unauthenticated | Usually requires auth or redirect/challenge | **200** when `permitAll` and controller succeeds |
| GET /me, unauthenticated | Requires authentication | **401** if app only enables HTTP Basic |
| GET /me, valid user | May proceed | **200** per `authenticated` rule |
| GET /admin, `ROLE_USER` | If only `authenticated` required, may proceed | **403** when `hasRole("ADMIN")` |
| GET /unknown, logged in | Access depends on config | Denied if fallback `anyRequest().denyAll()` |

**Important caveat:** this table compares **authorization policy** only. An endpoint without a controller can still return **404**, and authentication/CSRF/filter-chain errors can change the status. You cannot assert every request under default config always yields the same status because Spring Security adapts entry points to the client and configuration.

## 4. Reading HttpSecurity Syntax Layer by Layer

Common configuration:

~~~java
http
    .authorizeHttpRequests(auth -> auth
        .requestMatchers(HttpMethod.GET, "/public").permitAll()
        .requestMatchers(HttpMethod.GET, "/admin").hasRole("ADMIN")
        .requestMatchers(HttpMethod.GET, "/me").authenticated()
        .anyRequest().denyAll()
    )
    .httpBasic(Customizer.withDefaults());
~~~

This is a **snippet inside a `@Bean` method**, not a standalone Java class.

### 4.1. authorizeHttpRequests

**`authorizeHttpRequests(...)`** defines request-based authorization rules. **`AuthorizationFilter`** together with **`AuthorizationManager`** uses them to allow or deny. The **first matching** rule takes effect, so ordering must be intentional.

| Configuration | Meaning |
| --- | --- |
| **`permitAll()`** | Lets the request proceed without a logged-in principal; still traverses the chain and remaining filters |
| **`authenticated()`** | Requires an identity considered authenticated, not merely anonymous |
| **`hasRole("ADMIN")`** | Requires authority **`ROLE_ADMIN`** via default prefix |
| **`hasAuthority("report:read")`** | Requires the exact authority **`report:read`** |
| **`denyAll()`** | Denies requests matching that rule |
| **`anyRequest()`** | Matches all remaining requests **within the current `SecurityFilterChain`** |

**`hasRole("ADMIN")`** does not check the account username `"admin"`; it inspects the principal's **`GrantedAuthority`** list. If a user has authority **`ADMIN`** without **`ROLE_ADMIN`**, the default role check will not match.

### 4.2. requestMatchers Can Also Filter by HTTP Method

~~~java
.requestMatchers(HttpMethod.GET, "/api/items").permitAll()
.requestMatchers(HttpMethod.POST, "/api/items").hasRole("EDITOR")
~~~

Public GET does not imply public POST. Putting **`anyRequest().denyAll()`** at the end keeps undeclared endpoints or HTTP methods from opening automatically. Remember to design rules for error dispatches, static assets, health checks, and framework endpoints like login if your application uses them.

**Paths in matchers** must match how Spring Security receives requests in the servlet app. Do not guess paths when using a **context path**, custom servlet path, or reverse proxy. Always test actual routes.

### 4.3. httpBasic, formLogin, and Other Mechanisms

~~~java
.httpBasic(Customizer.withDefaults())
~~~

enables HTTP Basic so clients send **`Authorization: Basic ...`**. Depending on the request, missing valid credentials typically returns **401 + WWW-Authenticate**.

~~~java
.formLogin(Customizer.withDefaults())
~~~

enables form login, which can use Spring Security's generated login page and **`POST /login`**. When unauthenticated, browsers are normally **redirected** to the login page.

**Declaring a `SecurityFilterChain` does not automatically enable both login styles like Boot's default.** When authoring a new chain, explicitly declare the intended authentication mechanism for each request group. **`oauth2ResourceServer(...)`** is another option for Bearer tokens, requiring matching issuer/decoder/introspection configuration; JWTs are not automatically verified merely because an app has a `SecurityFilterChain` bean.

### 4.4. One Bean Is HTTP Configuration, Not Where Users Are Created

There are three configuration layers:
1. **`SecurityFilterChain`:** which requests are protected, with which filters, and which URLs require which permissions.
2. **Authentication:** how credentials are verified—which `UserDetailsService`/`AuthenticationProvider`/`PasswordEncoder`/JWT decoder runs.
3. **Session/CSRF/CORS and other policies:** how context is stored, how browsers send credentials, and how security response headers are built.

Do not blur responsibilities by calling **`loadUserByUsername`** manually in controllers or setting an arbitrary principal to bypass filters. When a valid user gets **403**, inspect authorization; when an unauthenticated client gets **401**, inspect authentication and the entry point.

## 5. Runnable Example with Spring Boot 3 + Java 17

The complete example below **replaces the default security configuration with a `SecurityFilterChain` bean** and declares a user source so results are deterministic without relying on generated passwords. It uses HTTP Basic across GET endpoints: public, authenticated, ADMIN-only, and an endpoint that has a controller yet is blocked by the final rule.

### 5.1. Preparing the Project

Create a **Spring Boot 3.x, Java 17+** project with **Spring Web**, **Spring Security**, **Spring Boot Test**, and **Spring Security Test**. In an existing Gradle project, the dependencies block is:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

The snippet above is the **dependencies section of an existing `build.gradle`**; the project must have matching plugins/BOM and Gradle Wrapper. The files below live in package **`com.example.customchain`**:

~~~text
src/main/java/com/example/customchain/
  CustomChainApplication.java
  SecurityConfig.java
  DemoController.java

src/test/java/com/example/customchain/
  SecurityChainTest.java
~~~

### 5.2. CustomChainApplication.java

~~~java
package com.example.customchain;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CustomChainApplication {
    public static void main(String[] args) {
        SpringApplication.run(CustomChainApplication.class, args);
    }
}
~~~

### 5.3. SecurityConfig.java — Bean Replacing the Default Configuration

~~~java
package com.example.customchain;

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
                .requestMatchers(HttpMethod.GET, "/me").authenticated()
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
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
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

**Line-by-line explanation:**

- **`@Configuration`** registers the configuration class; **`@Bean SecurityFilterChain`** supplies the app's HTTP policy to Spring. Boot no longer creates the default web security chain.
- **`HttpSecurity`** is passed into the method by Spring Security. **`http.build()`** builds the configured chain; never return null.
- **`GET /public` → `permitAll()`** is an intentional public exception.
- **`GET /me` → `authenticated()`** requires a logged-in principal.
- **`GET /admin` → `hasRole("ADMIN")`** requires authority **`ROLE_ADMIN`**. **`roles("ADMIN")`** in the builder prepends `ROLE_`.
- **`anyRequest().denyAll()`** denies requests without an explicit allow rule, even when a controller exists for that path.
- **`httpBasic(...)`** is the API authentication mechanism chosen for this example. **`formLogin(...)`** is not enabled in this chain.
- **`UserDetailsService`** and **`PasswordEncoder`** set up demo users; declaring a `UserDetailsService` bean also prevents Boot from creating its generated in-memory user in this case.
- **`BCryptPasswordEncoder`** hashes passwords for matching; sample passwords are strictly for local study. Never store plaintext passwords in production.

**CSRF remains enabled by Spring Security by default for unsafe HTTP methods** (such as POST) unless explicitly changed. Because this demo only uses GET endpoints, we do not disable CSRF casually. If you add POST endpoints, decide CSRF policy based on client types and how browsers attach credentials, and add corresponding tests.

Some older guides add **`.csrf(csrf -> csrf.disable())`** immediately whenever building a "REST API." That is not a mandatory consequence of HTTP Basic or `SecurityFilterChain`; understand CSRF risks and actual session/cookie/token behavior before changing it.

### 5.4. DemoController.java

~~~java
package com.example.customchain;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public String publicPage() {
        return "public";
    }

    @GetMapping("/me")
    public String me(Authentication authentication) {
        return "user:" + authentication.getName();
    }

    @GetMapping("/admin")
    public String adminPage() {
        return "admin-only";
    }

    @GetMapping("/unlisted")
    public String unlistedPage() {
        return "should-not-be-exposed";
    }
}
~~~

The **`/unlisted`** endpoint intentionally has a controller to verify deny-by-default: having a route **does not mean access is allowed**. Controller **`/me`** receives the verified `Authentication` rather than parsing the Basic header or re-checking passwords itself.

### 5.5. Running the Application and Sending Requests

In the directory containing the Gradle Wrapper:

~~~bash
./gradlew bootRun
# Windows (PowerShell or cmd):
gradlew.bat bootRun
~~~

In another terminal, send requests to **localhost**:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/me
curl -i -u alice:alice123 http://localhost:8080/me
curl -i -u alice:alice123 http://localhost:8080/admin
curl -i -u admin:admin123 http://localhost:8080/admin
curl -i -u admin:admin123 http://localhost:8080/unlisted
curl -i -u alice:wrong http://localhost:8080/me
~~~

Expected results for **this exact example**, assuming no other proxy or custom exception handler:

| Request | HTTP status | Result |
| --- | --- | --- |
| GET /public, anonymous | **200** | Body **public** |
| GET /me, anonymous | **401** | HTTP Basic challenge, typically with WWW-Authenticate |
| GET /me, alice valid password | **200** | Body **user:alice** |
| GET /admin, alice `ROLE_USER` | **403** | Authenticated but lacks `ROLE_ADMIN` |
| GET /admin, admin `ROLE_ADMIN` | **200** | Body **admin-only** |
| GET /unlisted, admin | **403** | Blocked by deny rule; controller never runs |
| GET /me, alice wrong password | **401** | Authentication failed |

With HTTP Basic, Base64 is merely encoding, **not security encryption**; always use **HTTPS** on real networks and avoid hardcoding or printing real credentials. **`curl -u user:password`** works for local demos yet can expose passwords in shell history or process lists. Error response bodies are not fixed in this example; verify status codes and `WWW-Authenticate`.

### 5.6. SecurityChainTest.java — Testing Behavior Through Filters

Create **`src/test/java/com/example/customchain/SecurityChainTest.java`**:

~~~java
package com.example.customchain;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityChainTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointIsAllowed() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void protectedEndpointRequiresAuthentication() throws Exception {
        mvc.perform(get("/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedUserCanReadProfile() throws Exception {
        mvc.perform(get("/me")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isOk())
            .andExpect(content().string("user:alice"));
    }

    @Test
    void roleRuleRejectsNonAdmin() throws Exception {
        mvc.perform(get("/admin")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanEnterAdminEndpoint() throws Exception {
        mvc.perform(get("/admin")
                .with(httpBasic("admin", "admin123")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin-only"));
    }

    @Test
    void unlistedControllerIsDeniedByFallbackRule() throws Exception {
        mvc.perform(get("/unlisted")
                .with(httpBasic("admin", "admin123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void invalidPasswordIsUnauthorized() throws Exception {
        mvc.perform(get("/me")
                .with(httpBasic("alice", "wrong")))
            .andExpect(status().isUnauthorized());
    }
}
~~~

Run:

~~~bash
./gradlew test
# Windows:
gradlew.bat test
~~~

These tests pass through Spring Security's filters via MockMvc; **`httpBasic(...)`** from Spring Security Test builds the Basic header rather than injecting a principal that bypasses authentication. They prove the `SecurityFilterChain` bean opened the right endpoint, rejected anonymous access, checked roles, and denied undeclared endpoints. Outcomes above are **expected per the code**; run Gradle in a properly configured project to verify live.

## 6. Why Can Adding Just a SecurityFilterChain Bean Cause Big Changes?

Once Boot stops generating the default web `SecurityFilterChain`, your application owns the protection policy. Several major effects follow:

### 6.1. Replacement Differs from Appending to Defaults

Spring Boot does not keep a "default security chain" and tack your rules onto the end. Once you register a `SecurityFilterChain`, **you are supplying the entire chain you built**. Creating a bean without complete rules/matchers can lead to unexpected behavior.

Example configuration you should avoid when sensitive endpoints exist:

~~~java
@Bean
SecurityFilterChain unsafeExample(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
        .anyRequest().permitAll()
    );

    return http.build();
}
~~~

**This snippet illustrates an overly permissive configuration**, not a deployment recommendation. It lets every request pass authorization, including future controllers handling sensitive data. When public endpoints are needed, allow only the exact URLs and HTTP methods required. Ending with **`anyRequest().denyAll()`** helps enforce a strict allowlist, while accounting for framework endpoints needed by the app.

### 6.2. Authentication and Authorization Are Two Separate Things

~~~java
.authorizeHttpRequests(auth -> auth
    .anyRequest().authenticated()
)
~~~

specifies the policy "requests require authentication." It **does not decide how credentials are collected**, **does not declare a user store**, and does not ensure form login or HTTP Basic is enabled.

A request can fail for distinct reasons:
- Missing or invalid credentials: **`AuthenticationEntryPoint`** is invoked, e.g., 401 Basic or 302 login.
- Authenticated yet lacking authority: typically **403** from **`AccessDeniedHandler`**.
- Missing/invalid CSRF token on a state-changing request when CSRF is enabled: can be blocked with **403** before the controller runs.
- Matches no chain: the request may go **unprotected by Spring Security**, a separate issue from 401/403.

Inspect the exact **chain**, **authentication filter**, and **rules** before modifying code.

### 6.3. A SecurityFilterChain Is Not Automatically Stateless

If an API should not read `HttpSession` for `SecurityContext`, configure:

~~~java
.sessionManagement(session -> session
    .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
~~~

This snippet requires importing **`SessionCreationPolicy`** inside `HttpSecurity` for the right chain. **`STATELESS`** controls whether Spring Security uses `HttpSession` for `SecurityContext`; it does not enable Bearer JWTs or guarantee everything on the server has zero state. For web apps using form login, sessions may be the right choice. Do not apply `STATELESS` to every chain merely because controllers return JSON.

### 6.4. Do Not Drop Security Headers and CSRF Arbitrarily

Filters such as **`HeaderWriterFilter`** and **`CsrfFilter`** normally remain configured with appropriate defaults when using `HttpSecurity`. Declaring your own `SecurityFilterChain` does not automatically disable those layers. Changing them requires a concrete reason, testing affected requests, and understanding how cookies/browser credentials are transmitted.

**`permitAll()` does not mean skipping the filter chain.** A public endpoint traversing the chain can still receive security headers and remain subject to other protections. Do not blindly put **`web.ignoring()`** on paths when **`permitAll()`** inside the chain already meets your needs.

## 7. Multiple SecurityFilterChains: /api and Web UI

An application may need different HTTP policies for APIs and browsers:

- **`/api/**`**: Basic or Bearer authentication, responses tailored to HTTP clients.
- **`/`**, **`/web/**`**, **`/login`**: form login, session cookies, and CSRF for browsers.

Declaring multiple **`SecurityFilterChain`** beans is supported, yet **`FilterChainProxy` selects only the first matching chain** in order. Chains **do not stack all their filters together** as independent layers for the same request.

Separate configuration example (this is a **snippet**; do not place it alongside the full `SecurityConfig` in section 5 without reconciling them):

~~~java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/ping").permitAll()
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults());

    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain webChain(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/", "/login").permitAll()
            .anyRequest().authenticated()
        )
        .formLogin(Customizer.withDefaults());

    return http.build();
}
~~~

Requires importing **`Bean`**, **`Order`**, **`HttpMethod`**, **`HttpSecurity`**, **`SecurityFilterChain`**, and **`Customizer`**. In this example:
1. **`apiChain`** uses **`securityMatcher("/api/**")`**, so it is chosen only for `/api` requests.
2. **`webChain`** specifies no `securityMatcher`, so its default matcher covers all remaining requests.
3. **`@Order(1)`** evaluates `/api` before the general chain.
4. API uses HTTP Basic while web uses form login. Adjust CSRF/session/CORS if your real architecture differs.
5. An **`anyRequest()`** rule in `apiChain` only governs requests **that already entered `apiChain`**, not requests outside `/api`.

### 7.1. securityMatcher vs. requestMatchers

| Element | Question | Example |
| --- | --- | --- |
| **`http.securityMatcher("/api/**")`** | Should this request enter the **API chain**? | `/api/items`: yes; `/login`: no |
| **`requestMatchers(HttpMethod.GET, "/api/ping")`** | Inside the selected chain, **which authorization rule** applies? | `GET /api/ping`: `permitAll` |
| **`anyRequest()`** | What about remaining requests **in this chain**? | require auth or `denyAll` |
| **`@Order`** | Which chain is evaluated first? | `/api` before web |

If you register only a **`securityMatcher("/api/**")`** chain with no catch-all fallback chain, **`/internal/debug`** could go unprotected by Spring Security. Most applications need a **fallback `SecurityFilterChain`** covering remaining URLs. To block unlisted URLs, use **`anyRequest().denyAll()`** in the general chain and open intentional exceptions.

### 7.2. Filter-Generated Endpoints Must Also Match the Matcher

Form login can serve **`GET /login`** and **`POST /login`** via its filters. If you configure **`formLogin`** inside a chain matching only **`/secured/**`**, then **`/login`** does not match that chain; filter-provided login endpoints may not exist as expected (often resulting in 404). Make sure login URLs fall within the chain's scope or have another chain handling them.

Likewise, for **`/logout`**, OAuth2 login callbacks, SAML endpoints, CSRF token endpoints, or other filter-generated endpoints, check **`securityMatcher`, endpoint URLs, and chain ordering** together. Never rely on paths copied from another example without testing.

### 7.3. Choosing Form Login vs. Basic/Bearer by Client

Browser apps using sessions and form login may need redirects and CSRF; API clients typically expect 401 with `WWW-Authenticate` or structured JSON errors. One application can legitimately have two chains. **Merely naming a controller "REST API" does not make Spring Security choose JWT or `SessionCreationPolicy.STATELESS` automatically.**

## 8. Static Resources, Error Dispatch, and Actuator

When replacing the default configuration, also check endpoints that are **not business controllers**:

- **Static assets**: CSS, JS, favicon, or asset folders needed by the login page; if the fallback rule is `denyAll` without allow rules, pages may render without styles or scripts.
- **`/error` and servlet dispatcher types**: when a controller fails, the servlet container may route to **`ERROR`/`FORWARD`** dispatches; if authorization runs and blocks that dispatch, error responses may differ from expectations. Consider explicit rules for appropriate dispatcher types.
- **Actuator**: health/info/metrics, possibly on a separate management port/path. Once you define a custom `SecurityFilterChain`, do not assume Boot's default Actuator policies still apply identically. Open only required health endpoints; protect metrics/env/beans and sensitive endpoints.
- **CORS preflight**: browsers may send **`OPTIONS`** before cross-origin requests carrying an `Authorization` header. Handle CORS properly before authorization and explicitly configure allowed origins, headers, and methods.
- **Login/logout endpoints**: if enabling `formLogin`/`logout`, verify the handled URLs and CSRF on POST.
- **OpenAPI/Swagger UI**: allow documentation only in appropriate environments; never expose internal API docs to the public internet by reflex.

Production configurations usually have to account for operational endpoints, not just three endpoints in a learning example. **Never open every URL or disable CSRF just to fix a 403**; first identify which filter or rule rejected the request.

## 9. Customizing AuthenticationEntryPoint and AccessDeniedHandler

Once `SecurityFilterChain` works, API clients sometimes require a specific error format.

**`AuthenticationEntryPoint`** initiates authentication when no valid identity exists; for Basic it is typically **401** with a challenge, while for form login it is typically **302** to login. **`AccessDeniedHandler`** handles insufficient privileges for an authenticated identity, typically **403**. **`ExceptionTranslationFilter`** bridges security exceptions to these handlers.

If an API needs JSON such as:

~~~json
{"error":"UNAUTHORIZED"}
~~~

you must define and test a custom handler/entry point; that is **not an immutable default body** across all Spring Security apps. When implementing one, avoid leaking credentials, tokens, or internal details in the response body. If the API uses HTTP Basic, consider keeping the challenge header for clients relying on standard HTTP authentication.

Do not write a controller **`@ExceptionHandler`** assuming it catches every **`AuthenticationException`/`AccessDeniedException`** thrown in servlet filters. Those errors can occur **before any controller is invoked**, making `exceptionHandling` inside the chain the proper place for many use cases.

## 10. Debugging When SecurityFilterChain Doesn't Behave as Expected

When adding the bean still produces "strange" responses, check in order:

| Observation | What to Check |
| --- | --- |
| Still seeing generated password | You only replaced the **web `SecurityFilterChain`**; did you declare a `UserDetailsService`/Provider/Manager to replace the default user source? |
| `GET /public` still asks for login | Did the request enter the right chain? Does `permitAll` match method/path? Is an earlier chain matching first? |
| POST returns 403 even when logged in | Could be CSRF or missing privilege; check CSRF token and method rules |
| `ROLE_USER` can access `/admin` | Is a broader `permitAll`/`authenticated` rule placed before `hasRole`? |
| Login returns 404 | Is `formLogin` enabled? Do `GET`/`POST /login` match the chain's `securityMatcher`? |
| `GET /unknown` is accessible | Is there an `anyRequest().permitAll` fallback or a request outside all chains? |
| API request gets 302 to `/login` | Did the web chain intercept the API request first? Does the API have the right entry point? |
| Sent Bearer yet got 401 Basic | Does the chain only enable `httpBasic` without configuring resource server Bearer tokens? |
| CORS rules do not work | Is `OPTIONS` preflight handled properly before authorization? |
| Role changed yet session keeps old roles | `Authentication` is cached in session/token; implement refresh/revalidation/revocation |

You can enable Spring Security logging in development:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

At startup, logs can list the filters inside each chain; at request time, logs help trace which chain, filter, and decision ran. **Never log raw `Authorization` headers, cookies, passwords, or access tokens**. With multiple chains, writing tests covering *exact* matchers and out-of-matcher paths is essential.

### 10.1. API and Version Pitfalls

- **Using `WebSecurityConfigurerAdapter`** from old guides in Spring Security 6: this API was removed; use a `SecurityFilterChain` bean.
- **Confusing Servlet with WebFlux**: WebFlux uses **`SecurityWebFilterChain`** and **`ServerHttpSecurity`**, not `HttpSecurity`/Servlet `SecurityFilterChain`.
- **Confusing your bean with `FilterChainProxy`**: your bean describes one filter chain, while the framework manages chain selection and execution.
- **Confusing `requestMatchers` with `securityMatcher`**: one defines authorization inside a chain, the other selects which chain runs.
- **Confusing `hasRole` and `hasAuthority`**: understand the default `ROLE_` prefix consistently.
- **Confusing `permitAll` with bypassing filters**: public requests still traverse the filter chain and can receive security headers.
- **Confusing 401/403/302**: responses depend on entry points and authentication state, not URL names alone.
- **Turning off protection layers to make tests pass**: diagnose the root cause of 403/CSRF/CORS/session issues and decide based on your threat model.

## 11. Process for Introducing SecurityFilterChain into an Existing Project

To transition safely from the default configuration:

1. **Inventory exact endpoints and HTTP methods**: public, authenticated, admin, audit, actuator, login, logout, static assets, callbacks.
2. **Choose authentication mechanisms**: form login/session, HTTP Basic, OAuth2/OIDC, JWT/opaque resource server, custom providers, or multiple chains.
3. **Define `SecurityFilterChain` beans**: use `HttpSecurity`, place specific rules first, add a deny fallback, and configure required filters.
4. **Declare identity sources**: `UserDetailsService`/`AuthenticationProvider`/`AuthenticationManager` or JWT decoder/introspector; do not leave the generated user in place inadvertently.
5. **Verify chain coverage**: with multiple chains, use `securityMatcher` and `@Order` so every protected URL matches at least one chain.
6. **Review CSRF, CORS, sessions, headers, and error dispatch**: tailor to client types and credential transport rather than copying a one-size-fits-all snippet.
7. **Test both allowed and denied cases**: anonymous, right/wrong password, right/wrong role, unlisted paths, other HTTP methods, callbacks/login/logout.
8. **Inspect logs and HTTP responses**: examine 401/403/302, challenges, session cookies, and active filters.
9. **Deploy with HTTPS and secret protection**: replace demo passwords, enforce least privilege, and design credential revocation.
10. **Maintain policy as features grow**: every new endpoint needs an explicit allow rule; sensitive business methods need resource/tenant checks beyond URL roles.

**Replacing the default configuration transfers security policy ownership to your application.** Make sure the new policy covers every important path; a "short" configuration is not automatically a safe one.

## 12. Self-Check Exercises

**Question 1.** Does adding only a `SecurityFilterChain` bean stop Spring Boot from creating the generated user?

**Answer:** Not necessarily. A `SecurityFilterChain` bean makes Boot back off from default web security configuration; the default user source is a separate auto-configuration. You need a `UserDetailsService`/`AuthenticationProvider`/`AuthenticationManager` bean to replace that authentication source.

**Question 2.** With **`requestMatchers("/public").permitAll()`**, does the request skip all Spring Security filters?

**Answer:** No. **`permitAll()`** is an authorization decision; the request still passes through the selected `SecurityFilterChain` and its remaining filters.

**Question 3.** If you put **`anyRequest().permitAll()`** before **`/admin` → `hasRole("ADMIN")`**, what happens?

**Answer:** Never write configuration that way; a catch-all rule can shadow specific rules, or the DSL may fail because rules cannot follow `anyRequest`, depending on phrasing and version. Put specific rules first and the fallback last.

**Question 4.** Suppose a chain has **`securityMatcher("/api/**")`** and **`anyRequest().denyAll()`**. Is `/internal/debug` guaranteed to be blocked by Spring Security?

**Answer:** No. If no other chain matches `/internal/debug`, the request may bypass Spring Security altogether. `denyAll()` inside the API chain does not apply to URLs that do not match that chain.

**Question 5.** You create a `SecurityFilterChain` calling only **`authorizeHttpRequests(...).anyRequest().authenticated()`**. Is HTTP Basic automatically enabled like in Boot's default?

**Answer:** Do not assume so. When defining your own chain, explicitly configure the intended mechanisms, such as **`httpBasic(Customizer.withDefaults())`** or **`formLogin(Customizer.withDefaults())`**.

**Question 6.** HTTP Basic user `alice` with `ROLE_USER` sends `GET /admin` requiring `ROLE_ADMIN`. Why does she get 403?

**Answer:** Authentication succeeds, yet her authorities do not satisfy the policy. That is an authorization denial.

**Question 7.** An API adds `POST /orders`, while GET on the same path uses `permitAll`. Does that mean POST is also public?

**Answer:** Not if the rule constrains HTTP methods. POST needs its own matching rule; CSRF may also apply if enabled.

**Question 8.** You enable **`formLogin`** in a chain matching only **`/secured/**`** while keeping the default login URL **`/login`**. Why can that return 404?

**Answer:** The filter chain handling login is not selected for `/login`, so the filter-provided endpoint is not reachable. Align login URLs, matchers, and chains consistently.

**Question 9.** Why might a REST controller return 302 when unauthenticated?

**Answer:** If the request enters a chain with form login enabled and a redirect entry point, Spring Security redirects to the login page. A REST controller does not choose the entry point itself.

**Question 10.** When a user's roles change, does `SecurityFilterChain` automatically update `Authentication` inside existing sessions or JWTs?

**Answer:** Not by default. You need a session invalidation, token expiration/revocation, or revalidation strategy and tests covering permission lifecycle changes.

## Official References

- Spring Boot 3.x — Security auto-configuration: https://docs.spring.io/spring-boot/3.4/reference/web/spring-security.html
- Spring Boot — How-to Security: https://docs.spring.io/spring-boot/3.4/how-to/security.html
- Spring Security 6.5 — Java Configuration / Multiple HttpSecurity: https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html
- Spring Security — Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- Spring Security — Servlet Architecture: https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html
- Spring Security — CSRF: https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html
- Spring Security — HTTP Basic: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/basic.html

**Takeaway:** declaring a **`@Bean SecurityFilterChain`** lets your application replace Boot's default web configuration with an explicit HTTP policy. Beyond that, you still must decide **how authentication works**, **the user/token source**, **authorization rules**, **CSRF/CORS/sessions**, and **chain coverage**. A sound configuration opens only what should be open, enforces exact privileges where protection is needed, and denies undeclared paths.
