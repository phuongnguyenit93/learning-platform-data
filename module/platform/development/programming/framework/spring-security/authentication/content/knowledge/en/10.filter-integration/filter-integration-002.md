# SecurityFilterChain, securityMatcher, and Login Endpoint Scope

> **Topic:** Spring Security — authentication. **Group:** Filter Integration. This lesson focuses on how Spring Security selects a security chain for an HTTP request, the practical meaning of `HttpSecurity.securityMatcher(...)`, how it differs from `authorizeHttpRequests().requestMatchers(...)`, and why `GET /login` or `POST /login` can disappear when chain scope is misconfigured. The sample code uses **Java 17**, **Spring Boot 3.5.16**, Spring Security 6.5.x, and MockMvc tests.

## 1. Objectives

After this lesson, you will be able to:

1. Describe `DelegatingFilterProxy`, `FilterChainProxy`, `SecurityFilterChain`, `HttpSecurity`, and their relationship to Servlet Filters.
2. Predict which chain is selected for a URL when an application has multiple `SecurityFilterChain` beans and `@Order`.
3. Distinguish chain-level `securityMatcher` from authorization-level `requestMatchers`; understand why `anyRequest()` only covers the scope already accepted by the chain.
4. Explain why a `formLogin()` configuration still fails to provide a working `/login` endpoint if `/login` falls outside the matcher.
5. Properly design `loginPage`, `loginProcessingUrl`, logout, custom components, and default pages.
6. Write two separate chains for a stateless HTTP Basic REST API and a form-login/session web app, with a safe final chain.
7. Run integration tests covering GET/POST login, CSRF, Basic 401/200, role-based 403, and session crossover.
8. Diagnose 404/401/403/302, redirect loops, shadowed matchers, error dispatches, and paths behind a reverse proxy.
9. Avoid confusing `permitAll` with bypassing the filter chain, and prevent newly added endpoints from remaining unprotected.

## 2. How Does a Request Enter Spring Security?

In a Servlet application, a request typically passes through `DelegatingFilterProxy`, which forwards it to the Spring bean named `springSecurityFilterChain`. That bean is a `FilterChainProxy`: it holds **a list of SecurityFilterChains** and evaluates each chain's `RequestMatcher` in order.

~~~mermaid
flowchart TD
    A["HTTP request"] --> B["DelegatingFilterProxy"]
    B --> P["FilterChainProxy"]
    P --> M1{"Chain @Order(1) match?"}
    M1 -->|Yes| F1["Run chain 1 filters"]
    M1 -->|No| M2{"Chain @Order(2) match?"}
    M2 -->|Yes| F2["Run chain 2 filters"]
    M2 -->|No| M3{"Catch-all chain match?"}
    M3 -->|Yes| F3["Run fallback filters"]
    M3 -->|No| X["Not protected by any Spring Security chain"]
    F1 --> END["Response or pass to Servlet"]
    F2 --> END
    F3 --> END
    X --> END
~~~

Core rule: **the first matching chain is selected, and subsequent chains are not executed**. Authorization rules, CSRF, authentication filters, and session policies of one chain are not automatically merged with another chain.

If **no chain matches**, Spring Security does not protect the request with the configured security filters. That **does not mean it is always 403 or 404**: if MVC has a matching handler, the handler may be invoked; if there is no handler, the result depends on the application. Leaving URLs outside every chain is a risk worth examining.

### Components in the Pipeline

| Component | Responsibility | What does it NOT do? |
| --- | --- | --- |
| `DelegatingFilterProxy` | Connects the Servlet container to the Spring-managed filter | Does not select roles itself |
| `FilterChainProxy` | Selects the first `SecurityFilterChain` with a matching matcher | Does not run all chains |
| `SecurityFilterChain` | Defines the scope matcher and list of filters | Does not generate MVC controllers |
| `HttpSecurity` | Builder that creates a chain and configures authentication, authorization, CSRF, etc. | Does not protect URLs outside its matcher |
| `UsernamePasswordAuthenticationFilter` | Handles POST form login at the configured processing URL | Does not render a custom GET login page |
| `DefaultLoginPageGeneratingFilter` | Generates the default GET login page when enabled by config | Does not generate arbitrary custom pages |
| `BasicAuthenticationFilter` | Checks HTTP Basic headers if configured on the chain | Does not create POST /api/login |
| `AuthorizationFilter` | Makes access decisions for requests that entered the chain | Does not select the first chain |

## 3. How Does securityMatcher Differ from requestMatchers?

### securityMatcher — the Gate to the Entire Chain

~~~java
http.securityMatcher("/api/**");
~~~

The chain is only considered for requests matching `/api/**`. If the request is `/login`, `/dashboard`, or any non-API path, this chain does not handle it; `FilterChainProxy` tries the next chain.

`securityMatcher` does not create endpoints, does not add authentication filters, and does not specify who is allowed. It defines the **scope of applicability** for the mechanisms configured below it.

### requestMatchers — Authorization Rules Inside the Chain

~~~java
http
    .securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .requestMatchers("/api/public/**").permitAll()
        .anyRequest().authenticated()
    );
~~~

In the snippet above, `requestMatchers("/api/admin/**")` is only applied **after the `/api/**` chain has been selected**. `anyRequest()` also only covers requests that matched the chain's `securityMatcher`. It does **not** mean every URL in the entire application requires authentication.

| Question | `securityMatcher(...)` | `authorizeHttpRequests().requestMatchers(...)` |
| --- | --- | --- |
| Configuration level | Entire `SecurityFilterChain` | Authorization rules within the chain |
| Effect | Is this chain selected? | What permission does the request need? |
| Affects login/basic/bearer filters? | Yes, because filters only run inside the chain | Does not create or move filters |
| When path does not match | Try the next chain | Try the next authorization rule |
| What does `anyRequest()` cover? | Not applicable | Remaining requests **inside this chain** |
| Automatically creates a controller? | No | No |
| Expands chain scope when `permitAll`? | No | No |

**Analogy:** `securityMatcher` is the building's entrance gate. `requestMatchers` are the room-entry rules once you are already inside the gate.

### Anti-pattern: permitAll on a URL Outside the Chain

~~~java
http
    .securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/login").permitAll()
        .anyRequest().authenticated()
    )
    .formLogin(Customizer.withDefaults());
~~~

Even with `requestMatchers("/login").permitAll()`, `/login` still **does not belong to `/api/**`**. Login GET/POST requests are never received by this chain. `permitAll` cannot fix the scope of `securityMatcher`.

## 4. @Order and the First-Match-Wins Rule

Suppose we have:

~~~text
@Order(1)  /api/admin/**  -> HTTP Basic + role ADMIN
@Order(2)  /api/**        -> HTTP Basic + authenticated
@Order(3)  no matcher     -> form login + catch-all
~~~

| Request | Selected chain | Reason |
| --- | --- | --- |
| GET `/api/admin/users` | 1 | Matches admin immediately |
| GET `/api/orders` | 2 | Not admin, but belongs to API |
| GET `/login` | 3 | Only catch-all matches |
| POST `/login` | 3 | Form login handled in chain 3 |
| GET `/portal` | 3 | Protected by catch-all |
| GET `/unmapped` | 3 | Still passes security, then MVC may 404 |

If the catch-all is placed at `@Order(1)`, it will **swallow every request**, preventing the subsequent API chains from ever being selected. There is no such thing as the first chain using `httpBasic` from a later chain or two chains combining permissions.

### How to Check Whether a Chain Is Shadowed?

1. List each chain along with its matcher/`@Order`.
2. Write out real request URLs and HTTP methods.
3. Scan from the smallest order to the largest.
4. Stop at the first matcher that returns true.
5. Inspect the inventory of filters and authorization rules **of that exact chain**.

For overlapping or nested patterns, place specialized chains before the catch-all. Use integration tests to avoid relying on accidental bean ordering.

### Why Should There Be a Catch-All?

~~~java
@Bean
@Order(99)
SecurityFilterChain fallback(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().denyAll())
        .build();
}
~~~

This is an **integration snippet** illustrating a fallback that closes all remaining paths. When the fallback needs web form login, use `authenticated()` and `formLogin(...)` per policy instead of `denyAll()`. The key point is **omitting `securityMatcher`** when you want to catch every URL not handled by earlier chains.

The Spring Security documentation recommends a chain without a narrow matcher to avoid accidentally leaving URLs unprotected.

## 5. Login Endpoints Can Belong to Filters, Not Controllers

A Servlet form-login configuration typically provides:

- `GET /login`: the default HTML page rendered by `DefaultLoginPageGeneratingFilter` when the default page is enabled.
- `POST /login`: `UsernamePasswordAuthenticationFilter` processes username/password at the default `loginProcessingUrl`.
- Redirect to `/login` when a web page requires authentication without an active session.
- Success/failure handling according to configured handlers.
- Logout via `LogoutFilter`, usually requiring POST and a CSRF token when CSRF is enabled.

**Critical condition:** the filter owning the endpoint must **reside in the chain selected for that URL**. Configuring `formLogin()` does not make a URL get handled outside the chain's matcher.

### 5.1. Default Form Login

~~~java
@Bean
SecurityFilterChain web(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .formLogin(Customizer.withDefaults());

    return http.build();
}
~~~

With no narrow `securityMatcher`, `GET/POST /login` falls inside the chain. In a typical setup, the login page is generated automatically. If your custom `SecurityFilterChain` does not call `formLogin`, do not assume form login remains enabled as in the earlier default auto-configuration.

### 5.2. GET and POST URLs Are Two Separate Jobs

| HTTP request | Handler | Requirements |
| --- | --- | --- |
| Default `GET /login` | `DefaultLoginPageGeneratingFilter` | Default form login and matching chain |
| Default `POST /login` | `UsernamePasswordAuthenticationFilter` | Matching chain, POST, `username`/`password`, CSRF |
| Custom `GET /account/sign-in` | MVC controller + HTML template | Developer builds the GET page |
| Custom `POST /account/sign-in` | `UsernamePasswordAuthenticationFilter` if processing URL is set accordingly | Form action, method, fields, CSRF |
| Basic `GET /api/report` | `BasicAuthenticationFilter` checks Authorization header | No `POST /api/login` route needed |
| `POST /logout` | `LogoutFilter` | Appropriate chain, URL, CSRF/method, policy |

Do not create a `@PostMapping("/login")` controller when you intend to use the default form login filter: the filter can intercept the request **before** the controller, making the controller appear as if it "never runs".

### 5.3. Common Mistake When a Chain Only Protects /secured/**

~~~java
@Bean
SecurityFilterChain restricted(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/secured/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .formLogin(Customizer.withDefaults())
        .build();
}
~~~

Suppose only this chain exists:

1. `GET /secured/report` enters the chain and is redirected to `/login`.
2. The browser calls `GET /login`.
3. `/login` **does not match `/secured/**`**, so the login-page generating filter in that chain does not run.
4. If no controller or other chain serves `/login`, the result can be **404**.

Spring Security's Java Configuration documentation highlights this exact surprising pitfall. If another chain matches `/login`, the response depends on that chain: it could be 302, 401, 403, or 404 depending on configuration, rather than "always 404".

## 6. Three Ways to Fix a Mis-Scoped Login Endpoint

### 6.1. Approach A: Dedicated Chain for API, Catch-All Chain for Web

~~~java
@Bean
@Order(1)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}

@Bean
@Order(2)
SecurityFilterChain web(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .formLogin(Customizer.withDefaults())
        .build();
}
~~~

`GET/POST /login` enters the web chain and can be handled by the form login filters. API paths enter the API chain and do not get redirected to a web form if the Basic entry point handles them properly. This is a clean architecture for understanding first-match.

### 6.2. Approach B: Put Login Inside the Protected Prefix

~~~java
http
    .securityMatcher("/secured/**")
    .authorizeHttpRequests(auth -> auth
        .anyRequest().authenticated())
    .formLogin(form -> form
        .loginPage("/secured/login")
        .loginProcessingUrl("/secured/login")
        .permitAll()
    );
~~~

Here `/secured/login` is inside the matcher. However, because **a custom `loginPage` is configured**, the developer **must create `GET /secured/login` themselves** via a controller/template; Spring Security will not auto-generate that custom page. POST to the same path is handled by the authentication filter, with matching form fields and CSRF.

Logout should also live under the right prefix if that chain manages logout:

~~~java
http.logout(logout -> logout
    .logoutUrl("/secured/logout")
    .logoutSuccessUrl("/secured/login?logout")
    .permitAll());
~~~

Do not treat a GET logout link as a valid logout request when CSRF is enabled; a POST with a token is typically required.

### 6.3. Approach C: Intentionally Match Multiple Paths

You can have a chain accept `/secured/**` **and** `/login`, `/logout` using appropriate overloads/`RequestMatcher`. However, with multiple chains, it must be clear **which chain owns each URL**. Never casually mix a custom login page in chain A with a POST processing filter in chain B.

With every approach, test **GET page, POST processing, success/failure redirects, logout, and assets** separately; one working URL does not prove the others are wired correctly.

## 7. Hands-on Spring Boot Example: Basic API and Web Form Login

The application has two chains:

- API chain `@Order(1)`: `securityMatcher("/api/**")`, `httpBasic`, `SessionCreationPolicy.STATELESS`, admin URLs require `ROLE_ADMIN`.
- Web chain `@Order(2)`: **no `securityMatcher`** so it acts as a catch-all, default form login, session, logout, and public pages.
- Demo user `lan` with `ROLE_USER` and a BCrypt password. This is local test data only.

Expected requests:
- `GET /public/ping` returns 200.
- `GET /app/dashboard` unauthenticated redirects to `/login`.
- `GET /login` returns the generated form page.
- `POST /login` without CSRF returns 403.
- `POST /login` with valid credentials and CSRF creates a session.
- `GET /api/report` without Basic returns 401; with valid Basic returns 200.
- `GET /api/admin/report` with `lan`'s valid credentials but missing role returns 403.
- A web session does not substitute for Basic credentials when calling the stateless API.

### 7.1. Project Structure

~~~text
chain-scope-lab/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/chainscope/
    │   ├── ChainScopeApplication.java
    │   ├── SecurityConfig.java
    │   └── DemoController.java
    └── test/java/example/chainscope/
        └── ChainScopeSecurityTests.java
~~~

### 7.2. settings.gradle

~~~groovy
rootProject.name = 'chain-scope-lab'
~~~

### 7.3. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Spring Boot 3.5 belongs to the Spring Security 6.5 line and supports Java 17. Fixed versions are for reproducing the lab; production must follow supported BOM/patch releases. Do not mix a newer Spring Security module with incompatible older modules.

### 7.4. ChainScopeApplication.java

~~~java
package example.chainscope;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ChainScopeApplication {
    public static void main(String[] args) {
        SpringApplication.run(ChainScopeApplication.class, args);
    }
}
~~~

### 7.5. SecurityConfig.java

~~~java
package example.chainscope;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("lan")
                    .password(encoder.encode("demo123"))
                    .roles("USER")
                    .build());
    }

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .httpBasic(Customizer.withDefaults());

        // API only has GET in this demo; keep default CSRF.
        // Do not disable CSRF for HTTP Basic without proper evaluation.
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/public/**", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .logout(Customizer.withDefaults());

        // No securityMatcher: this chain handles all URLs not matched by API.
        return http.build();
    }
}
~~~

Because the web chain catches all remaining paths, `GET /login` and `POST /login` fall into the chain with form login. `requestMatchers("/", "/public/**", "/error").permitAll()` only sets permissions for public endpoints; default `formLogin` permits the corresponding login page/processing paths.

### 7.6. DemoController.java

~~~java
package example.chainscope;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {
    @GetMapping("/")
    public String index() {
        return "index";
    }

    @GetMapping("/public/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/app/dashboard")
    public String dashboard(Authentication authentication) {
        return "dashboard:" + authentication.getName();
    }

    @GetMapping("/api/report")
    public String api(Authentication authentication) {
        return "api:" + authentication.getName();
    }

    @GetMapping("/api/admin/report")
    public String admin(Authentication authentication) {
        return "admin:" + authentication.getName();
    }
}
~~~

There are no `GET /login` or `POST /login` controllers in the application: they are provided by **Spring Security's form login filters** under the default configuration.

### 7.7. ChainScopeSecurityTests.java

~~~java
package example.chainscope;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.hamcrest.Matchers.containsString;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrlPattern;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ChainScopeSecurityTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointWorks() throws Exception {
        mvc.perform(get("/public/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("pong"));
    }

    @Test
    void unauthenticatedWebRedirectsToLogin() throws Exception {
        mvc.perform(get("/app/dashboard"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrlPattern("**/login"));
    }

    @Test
    void generatedLoginPageExists() throws Exception {
        mvc.perform(get("/login"))
            .andExpect(status().isOk())
            .andExpect(content().string(containsString("name=\"username\"")));
    }

    @Test
    void formLoginWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/login")
                .param("username", "lan")
                .param("password", "demo123"))
            .andExpect(status().isForbidden());
    }

    @Test
    void formLoginSessionDoesNotAuthenticateStatelessApi() throws Exception {
        MvcResult login = mvc.perform(post("/login")
                    .with(csrf())
                    .param("username", "lan")
                    .param("password", "demo123"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/app/dashboard").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("dashboard:lan"));

        mvc.perform(get("/api/report").session(session))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void apiWithoutBasicReturns401() throws Exception {
        mvc.perform(get("/api/report"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void apiWithBasicReturnsReport() throws Exception {
        mvc.perform(get("/api/report")
                .with(httpBasic("lan", "demo123")))
            .andExpect(status().isOk())
            .andExpect(content().string("api:lan"));
    }

    @Test
    void apiWithWrongBasicPasswordReturns401() throws Exception {
        mvc.perform(get("/api/report")
                .with(httpBasic("lan", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void apiAdminRoleCannotBeBypassed() throws Exception {
        mvc.perform(get("/api/admin/report")
                .with(httpBasic("lan", "demo123")))
            .andExpect(status().isForbidden());
    }
}
~~~

This is a **complete test class** with 9 test methods. It sends real requests through Spring Security's filters in `MockMvc`, unlike `@WithMockUser` which can bypass the very authentication step being tested.

### 7.8. Running and Observing

From the `chain-scope-lab` directory, using JDK 17+ and a compatible Gradle version:

~~~bash
gradle test
gradle bootRun
~~~

Or with the Gradle Wrapper:

~~~bash
./gradlew test
./gradlew bootRun
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat test
.\gradlew.bat bootRun
~~~

Local curl test commands:

~~~bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/login
curl -i http://localhost:8080/app/dashboard
curl -i http://localhost:8080/api/report
curl -i -u lan:demo123 http://localhost:8080/api/report
curl -i -u lan:demo123 http://localhost:8080/api/admin/report
~~~

Expected results per configuration:

| Request | Result | Why |
| --- | --- | --- |
| GET `/public/ping` | 200, `pong` | Permitted by catch-all |
| GET `/login` | 200, HTML login | Catch-all has formLogin |
| GET `/app/dashboard` no session | 302 to login | Web chain requires authenticated |
| GET `/api/report` no Basic | 401 | API chain uses Basic |
| GET `/api/report` valid Basic | 200, `api:lan` | Provider authenticates validly |
| GET `/api/admin/report` Basic `lan` | 403 | `ROLE_USER` lacks `ROLE_ADMIN` |
| POST `/login` no CSRF | 403 | CSRF is enabled on web chain |
| POST `/login` valid password+CSRF | Redirect + session | Form filter processes it |
| GET API with only web session | 401 | Stateless API chain does not use web session |

**Do not use real credentials in the terminal:** `curl -u lan:demo123` is strictly fake local data. On real systems, use HTTPS and avoid exposing passwords in shell history, process lists, or logs. Gradle/Boot output includes runtime-dependent logs; there is no fixed stdout beyond API responses and test assertions.

### 7.9. Why Is the API Set to STATELESS?

The session policy applies **to the API chain**, so a web session does not serve as credentials accepted by the Basic API chain. `SecurityContext` still exists while processing a valid Basic request, but it is not saved for subsequent requests to reuse like form login.

`STATELESS` does not mean no request in the JVM has a session: the web chain has its own session. Nor does it mean CSRF is always useless; HTTP Basic in a browser can cause browsers to auto-send credentials, so it must be evaluated for mutating methods.

## 8. Configuring a Custom Login Page in a Prefixed Chain

Suppose the application UI lives under `/portal/**` and you want all login/logout under the same prefix:

~~~java
@Bean
@Order(1)
SecurityFilterChain portal(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/portal/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/portal/login", "/portal/assets/**")
                .permitAll()
            .anyRequest().authenticated()
        )
        .formLogin(form -> form
            .loginPage("/portal/login")
            .loginProcessingUrl("/portal/login")
            .failureUrl("/portal/login?error")
            .defaultSuccessUrl("/portal/home")
            .permitAll()
        )
        .logout(logout -> logout
            .logoutUrl("/portal/logout")
            .logoutSuccessUrl("/portal/login?logout")
            .permitAll()
        )
        .build();
}
~~~

This is an **integration snippet**, not a complete second application. You still need:
- An MVC handler `GET /portal/login` and a view/template rendering the form;
- Form action `POST /portal/login`, `username`/`password` fields, and a valid CSRF token;
- A handler `GET /portal/home` for the success redirect;
- A policy for URLs outside `/portal/**`, such as a deny-all fallback;
- Logout method/CSRF matching config, assets, and error routes.

Because a custom `loginPage(...)` is configured, **Spring Security will not auto-generate that GET page**. However, `loginProcessingUrl(...)` makes the filter handle POST at that URL, as long as the request enters the same chain.

### Illustrative HTML Skeleton for a Custom Page

~~~html
<form method="post" action="/portal/login">
  <label>User <input name="username" /></label>
  <label>Password <input type="password" name="password" /></label>
  <!-- Server/template engine must render the hidden CSRF field/token. -->
  <button type="submit">Sign in</button>
</form>
~~~

This is an **explanatory skeleton** without an actual hidden CSRF field, so it is insufficient when CSRF is enabled. When using Thymeleaf/JSP or a separate frontend, pass the token per Spring Security's contract. Never hardcode a token or disable CSRF globally just to make a form work.

## 9. Comparing Error Scenarios and Root Causes

| Symptom | Cause category to inspect | Direction to fix |
| --- | --- | --- |
| GET `/login` returns 404 | Login page filter in narrow chain didn't match; no custom GET | Check chain matching and GET controller |
| POST `/login` returns 404 | No `UsernamePasswordAuthenticationFilter` in selected chain; wrong path | Check `loginProcessingUrl` and chain |
| POST `/login` returns 403 | Missing/invalid CSRF, or another policy denied it | Check token, cookie/session, filter chain |
| POST login goes to `?error` | Wrong credentials/account status or failure handler | Check `UserDetailsService`/`PasswordEncoder` |
| API returns 302 `/login` | Request hit web chain or API chain enabled form login | Check `@Order`/matcher/entry point |
| API returns 401 | Missing or invalid Basic/Bearer credentials | Check Authorization header |
| API returns 403 after valid Basic | Principal authenticated validly but lacks authority | Check roles/permissions |
| GET login loops in redirects | Page not permitted or target URL triggers auth requirement | Add `permitAll` in the right chain |
| Public page still gets 403 on POST | `CsrfFilter` runs despite `permitAll` | Clarify CSRF policy |
| Protected GET endpoint returns 200 without login | Outside all chains or overly broad `permitAll` | Add catch-all and tighten policy |
| Success redirect lands on 404 | Target endpoint has no MVC handler or wrong matcher | Check `successUrl` and routes |

**Do not jump to conclusions:** 404 does not mean wrong password or that Spring Security has no filters; 302 does not mean authentication succeeded; 401 does not mean the username does not exist. HTTP status is the outcome of multiple layers: matching, authentication, authorization, exception handling, and MVC routing.

## 10. Differences Between permitAll and web.ignoring

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public/**").permitAll()
    .anyRequest().authenticated());
~~~

`permitAll` only removes the authentication/authorization requirement for matching paths, while security filters still get to run: CSRF, security headers, context, and custom filters.

By contrast, `web.ignoring().requestMatchers(...)` configures Spring Security to skip the entire filter chain for the request. For authentication endpoints, this **can disable the filter needed to process POST login**, logout, or critical headers/context. Never use `ignoring("/login")` as a workaround for a broken `securityMatcher`.

If you only want public assets, `permitAll` is generally preferable to ignoring so that security headers are preserved. Special static-resource cases that require ignoring must be based on specific evaluation and testing.

## 11. CSRF, HTTP Methods, and Form Login

Spring Security Servlet normally enables CSRF by default. When a client POSTs a login form, a valid token is required. Spring Security's default generated login page includes the corresponding token mechanism, while an application-rendered custom page must include the CSRF field/header properly.

### Why Does Login Return 403 Even With the Correct Password?

- POST enters a chain with `CsrfFilter`.
- Request is missing or has an invalid CSRF token.
- `CsrfFilter` rejects the request before `UsernamePasswordAuthenticationFilter` authenticates it.
- Login does not proceed; it has nothing to do with bcrypt, `UserDetailsService`, or whether the password was right or wrong.

Test CSRF via integration tests as shown above. Do not rush to disable CSRF across the app to "fix login".

### Does HTTP Basic in an API Need CSRF?

Evaluate based on **how credentials are automatically sent**:
- Browsers can cache and auto-send HTTP Basic credentials, so state-changing requests can be vulnerable to CSRF.
- Bearer tokens actively attached in headers by clients follow a different model.
- JWTs stored in cookies still face CSRF risks even though the JWT is signed.
- CSRF configuration is per-chain, not "if `/api/**`, definitely disable it".

In the demo, the API only exposes GET, so default CSRF is kept. When adding POST/PUT/DELETE endpoints to an API, determine the client model, credential transport, and actual CSRF policy.

### GET and POST Login Differ

Having `/login` matched by `securityMatcher` is not enough: the authentication filter also has a method matcher. `UsernamePasswordAuthenticationFilter` normally handles **POST**. GET renders the page. If a custom form submits via GET or points to the wrong action URL, the filter will not execute.

## 12. Context Path, Servlet Path, and Reverse Proxies

Matchers inspect requests according to the Servlet/framework environment. A browser might visit `https://example.com/shop/api/report` while the app runs with a context path or proxy prefix, making the path seen by Spring Security matchers differ from the external URL.

Verify:
1. `server.servlet.context-path` and servlet mappings (`DispatcherServlet` may be mapped under a base path).
2. The `RequestMatcher` type in use, MVC/`PathPattern` behavior, and Spring Security version configuration.
3. Cases requiring matchers with a specific servlet path or base path.
4. HTTP method, trailing slashes, URL encoding, and path normalization.
5. Trusted reverse proxy forwarding headers; never derive policy from untrusted headers.
6. Multiple `DispatcherServlet` instances or separate Spring contexts.
7. GET login page, POST processing, redirects, OAuth callbacks, and static assets behind the proxy.

Do not blindly prepend prefixes to matchers based on browser URLs; inspect the **actual request path arriving at the server** in controlled tests/logs.

## 13. Other Authentication Mechanisms Are Also Subject to Chain Scope

| Mechanism | Filters/URLs to watch | Consequence if URL is outside the chain |
| --- | --- | --- |
| Form login | Generated GET login, POST processing | Corresponding endpoints do not exist |
| HTTP Basic | `BasicAuthenticationFilter` reading header | API does not issue intended Basic challenge |
| Bearer Resource Server | `BearerTokenAuthenticationFilter` | API may fall into form redirect or fail to verify tokens |
| OAuth2/OIDC Login | Authorization redirect and callback URL | Login flow/callback never reaches the filter |
| SAML2 Login | Authentication request and response endpoints | SAML callback is not processed |
| Logout | `LogoutFilter` and success page | Logout does not run or success URL is invalid |

Calling `httpBasic()` **does not automatically create** a `POST /api/login` endpoint to issue JWTs. HTTP Basic authenticates credentials directly on each HTTP request. If an application builds its own token-issuance endpoint, that is a separate API authentication design requiring checks on method/path/filter, credentials, token signing, rate limiting, and security policies.

OAuth2/SAML URLs depend on registrations and configurers; always verify that **filter-owned endpoints** fall within the corresponding chain's `securityMatcher`.

## 14. How to Debug Effectively with FilterChainProxy

In development, enable just enough logging:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Then for each request, determine:
1. Actual HTTP method/path/servlet mapping.
2. Which chain did `FilterChainProxy` select?
3. Does the chain contain the needed filter (`UsernamePasswordAuthenticationFilter`, Basic, Bearer, etc.)?
4. Do GET and POST route into the same designed authentication architecture?
5. Are `loginProcessingUrl`, form action, parameter names, and CSRF correct?
6. What is the authorization rule (`permitAll`/authenticated/role) inside that chain?
7. Where do authentication success/failure redirects go?
8. Are fallback URLs protected?

**Do not enable DEBUG indiscriminately in production:** limit duration and log access, and avoid exposing Authorization headers, cookies, session IDs, passwords, JWTs, Principals, or full `SecurityContext`s.

### URL Owner Table to Write Before Implementation

| URL | Method | Owner | Correct chain | Policy |
| --- | --- | --- | --- | --- |
| `/login` | GET | `DefaultLoginPageGeneratingFilter` | web | public |
| `/login` | POST | `UsernamePasswordAuthenticationFilter` | web | public + CSRF |
| `/app/dashboard` | GET | MVC controller | web | authenticated |
| `/public/ping` | GET | MVC controller | web | permitAll |
| `/api/report` | GET | MVC controller | API | Basic authenticated |
| `/api/admin/report` | GET | MVC controller | API | Basic + ADMIN |
| `/logout` | POST | `LogoutFilter` | web | CSRF/logout policy |

This table clarifies **the right chain** before editing `requestMatchers`. When a URL matches multiple chain matchers, the higher-priority chain is the actual owner.

## 15. Testing Scope Protection: Beyond the Happy Path

A recommended test checklist:

| Case | What to assert |
| --- | --- |
| API without credentials | 401/challenge, no web redirect |
| API Basic wrong password | 401, no authenticated result |
| API Basic valid | Expected principal and endpoint body |
| API missing role | 403, cannot bypass ADMIN |
| Web unauthenticated | Redirect to login page |
| GET default login | 200 and contains form fields |
| POST login missing CSRF | 403 and no authenticated session |
| POST login valid + CSRF | Auth succeeds, web session created |
| Web session calling stateless API | Does not substitute for Basic credentials |
| Catch-all security | Non-API endpoints do not accidentally bypass |
| Custom login URL | Valid GET page, POST processing, failure/success redirects |
| Shadowed chain | `@Order` prevents generic chain from swallowing API |
| Logout | Valid POST method/CSRF/session invalidation |
| 404 after auth | MVC path missing, not confused with missing filter |
| Reverse proxy/context path | Matchers and production redirects align |
| New controller | Not accidentally public due to missing chain |
| Error dispatch | No redirect loops or stack trace exposure |

`@WithMockUser` is useful for authorization tests, but **cannot replace** testing the form processing URL or HTTP Basic filters. This lab uses MockMvc requests with `httpBasic` and real form POSTs because that proves the matchers and filters actually work.

### Testing an Endpoint Outside Any Chain

If the application only defines:

~~~java
http.securityMatcher("/api/**");
~~~

and has a controller `GET /admin/secret` outside `/api/**`, that Spring Security chain does not protect the controller. Tests asserting authenticated/denied access must catch this, rather than only testing the API. Add a catch-all chain with safe rules to reduce this risk.

## 16. Two Error Layers: URL in Chain vs. URL in Route

Easily confused scenario:

~~~text
GET /some-page
 -> matches a SecurityFilterChain
 -> user is authenticated
 -> controller has no mapping for /some-page
 -> DispatcherServlet 404
~~~

This is **not** evidence of a missing chain. Conversely:

~~~text
GET /login
 -> no chain matches
 -> DefaultLoginPageGeneratingFilter never gets a chance to run
 -> no MVC controller for /login
 -> 404
~~~

Both produce the same HTTP status but have different root causes. When debugging, determine chain selection **before** looking at handler mappings, and only then examine authentication/authorization and MVC 404s.

With custom login, `loginPage("/portal/login")` **does not create an MVC GET handler**, whereas `loginProcessingUrl("/portal/login")` configures POST filter processing. Test both paths/methods separately.

## 17. Anti-patterns to Avoid

1. Writing `requestMatchers("/login").permitAll()` when `securityMatcher` excludes `/login`.
2. Having only an `/api/**` chain and assuming all other endpoints are also protected.
3. Putting the catch-all at `@Order(1)` and shadowing specialized chains.
4. Assuming all chains execute for the same request.
5. Using default `formLogin` inside a `/secured/**` chain while forgetting `/login`.
6. Configuring a custom `loginPage` without a GET controller.
7. Form action differing from `loginProcessingUrl` or using GET instead of POST.
8. Disabling CSRF to "fix" 403 on login without a security review.
9. Using `web.ignoring("/login")`, preventing the processing filter from running.
10. Assuming `permitAll` skips all filters.
11. Assuming Basic creates a POST endpoint that issues JWTs.
12. Assuming `anyRequest()` protects URLs outside the chain.
13. Confusing an MVC 404 with a missing login filter.
14. Seeing HTTP 302 and assuming login succeeded without checking the redirect target.
15. Relying on a web session for an API configured as stateless.
16. Failing to verify logout URL/method/CSRF.
17. Putting the `ADMIN` role requirement in the authorization rules of a chain that is never selected.
18. Lacking regression tests for GET and POST login.
19. Using `@WithMockUser` as proof that password authentication works.
20. Neglecting context path/servlet mapping when deploying behind a proxy.
21. Missing a fallback chain and accidentally exposing new controllers publicly.
22. Creating a Basic API whose URLs fall into a form redirect.
23. Stripping security headers from public pages via unnecessary ignoring.
24. Failing to distinguish 401 (missing/invalid credentials) from 403 (insufficient permissions).
25. Enabling logs containing tokens/passwords to debug matchers.
26. Defining multiple overlapping chains without specifying order.
27. Keeping the login page in chain A and the processing filter in chain B without verifying the security flow.
28. Not realizing `/error` and dispatcher types may be subject to separate authorization policies.

## 18. Self-Check Questions

**1. Does `securityMatcher("/api/**")` mean all other URLs return 403?**  
No. URLs not matching this chain try the next chain; if no chain matches, Spring Security does not protect those URLs via a chain.

**2. Does `requestMatchers("/login").permitAll()` expand the scope of the `/api/**` chain?**  
No. It is only an authorization rule inside the already-selected chain.

**3. Why can `formLogin` be enabled yet `GET /login` returns 404?**  
The GET login page may be outside `securityMatcher` or a custom page may lack a GET MVC handler; determine which chain receives the URL.

**4. If catch-all has `@Order(1)` and the API chain has `@Order(2)`, where does `GET /api/report` go?**  
The catch-all is selected first; the API chain does not run.

**5. Does `anyRequest().authenticated()` in a `/secured/**` chain protect `/admin/**`?**  
No, because `/admin/**` does not match that chain's matcher.

**6. Does a custom `loginPage("/portal/login")` need a GET controller?**  
Yes. Spring Security does not generate custom GET pages; the filter can handle POST if the processing URL matches.

**7. POST login returns 403 even with the right password: what to check first?**  
CSRF token, chain matching, form action/method, and filters; do not rush to change `PasswordEncoder`.

**8. Does HTTP Basic automatically expose `POST /api/login`?**  
No. It authenticates the Basic header directly on each request.

**9. What does a Basic API request with a valid password but missing `ROLE_ADMIN` usually return?**  
403 Forbidden, distinct from 401 unauthenticated.

**10. Does `permitAll` bypass `CsrfFilter`?**  
No. It is an authorization decision, not a removal of the CSRF filter.

**11. Is a web form login session automatically valid on a stateless Basic API?**  
Not under the lab configuration; the API does not use sessions to restore `SecurityContext`.

**12. Why should you have a catch-all chain?**  
So that new or uncategorized URLs not covered by specialized chains still fall under a security policy.

**13. Does `GET /login` returning 200 guarantee `POST /login` is handled properly?**  
No. You must test POST with credentials, CSRF, and the right processing matcher.

**14. Why shouldn't `redirectedUrl` be treated as a controller route created by Spring Security?**  
A redirect only specifies a target URL; that URL still needs an appropriate filter or handler.

**15. Can CSRF be disabled just because an API is stateless and stores a JWT in a cookie?**  
No; cookies can be sent automatically by browsers and are subject to CSRF. Evaluate based on actual credential transport.

**16. If an authenticated request receives 404, must it be due to a missing `SecurityFilterChain`?**  
No. MVC may simply have no matching handler even though the request passed through the chain.

## 19. Production Checklist

- [ ] Inventory all `SecurityFilterChain` beans, their matchers, and `@Order`.
- [ ] Verify which requests enter which chain, including error dispatches and new URLs.
- [ ] Have a safe catch-all chain.
- [ ] Ensure each chain contains the right authentication mechanism (form, basic, bearer, oauth2, etc.).
- [ ] Ensure both GET login page and POST processing URL belong to the right chain.
- [ ] Custom login page has an MVC GET handler, template, form action, fields, and CSRF.
- [ ] Success/failure redirects and logout URLs have valid routes, chains, and policies.
- [ ] Never use `permitAll` to try to bypass `securityMatcher`.
- [ ] Never use `web.ignoring` for login processing endpoints.
- [ ] API chains return appropriate Basic/Bearer responses instead of unintended form redirects.
- [ ] Distinguish authentication (401/redirect) from authorization (403).
- [ ] Verify CSRF based on cookie/Basic/Bearer transport and HTTP methods.
- [ ] Ensure session policies are right for stateless APIs and session-based web apps.
- [ ] Test context path, servlet path, and reverse proxy behavior.
- [ ] Include tests for GET/POST login, CSRF failure, role 403, API 401/200, logout, and catch-all.
- [ ] Do not rely solely on `@WithMockUser` to test auth filters.
- [ ] Do not log secrets when debugging `FilterChainProxy`.
- [ ] Re-run integration tests after every change to matchers, order, or login URLs.

**Key takeaway:** A `SecurityFilterChain` is the set of filters applied to a request; `securityMatcher` is the boundary for **selecting the chain**, while `requestMatchers` sets permissions **inside the selected chain**. Login endpoints provided by security filters only work when the URL actually enters the chain containing those filters. Setting proper order and scope, keeping a safe catch-all, testing both GET and POST login, and using request-based integration tests prevents most "configured yet nonexistent" login bugs.

### Official References

- Spring Security — Java Configuration / Multiple HttpSecurity / SecurityFilterChain Endpoints: https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html
- Spring Security — Authorize HttpServletRequests / Security Matchers: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- Spring Security — Form Login: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html
- Spring Security — HTTP Basic: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/basic.html
- Spring Security — Servlet Authentication Architecture: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html
- Spring Security — CSRF: https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html
- Spring Security — SecurityFilterChain API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/SecurityFilterChain.html
- Spring Boot 3.5 — System Requirements: https://docs.spring.io/spring-boot/3.5/system-requirements.html
