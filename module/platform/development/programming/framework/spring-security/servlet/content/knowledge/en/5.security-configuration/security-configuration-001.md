# HttpSecurity, Lambda DSL, and Building a SecurityFilterChain

When configuring security for **Spring MVC on the Servlet stack**, one of the most important pieces of code is the bean that returns a `SecurityFilterChain`, built using `HttpSecurity` and the **Lambda DSL**. Understanding this code answers very practical questions: which requests get which policy, why a caller is allowed in or blocked, what happens when `build()` is called, and why a rule looks right yet the endpoint still returns 401/403.

This lesson uses Java 17+, Spring Boot 3.3.x, and Spring Security 6.x as the context for its examples. The principles of Servlet configuration, matchers, authentication, and authorization must be clearly distinguished before learning other features such as OAuth2, JWT, or method security.

**Lesson objectives:**

- Know that `HttpSecurity` is a **configuration builder** for a security filter chain, not an object that directly handles each HTTP request.
- Read and write the Lambda DSL, understanding the role of the lambda parameter, `Customizer.withDefaults()`, and `build()`.
- Distinguish the condition for **selecting a SecurityFilterChain** from the **authorization rules inside the chain**.
- Explain the order of bean initialization at startup and the order of processing a request at runtime.
- Create a runnable configuration, test public, authenticated, authority/role, and CSRF branches, and diagnose common errors.

## 1. The big picture: from HTTP request to SecurityFilterChain

A Servlet application receives HTTP requests through a Servlet container (for example, Tomcat). Before `DispatcherServlet` and Spring MVC controllers run, the request passes through a chain of `Filter`s. Spring Security integrates at this layer: `DelegatingFilterProxy` delegates processing to the `springSecurityFilterChain` bean, typically `FilterChainProxy`. That component selects a `SecurityFilterChain` matching the request and invokes the security filters in the order built by the framework.

~~~text
Client -> Servlet container
       -> DelegatingFilterProxy
       -> FilterChainProxy
          -> select SecurityFilterChain matching the request
          -> security filters (context, authentication, CSRF, authorization, ...)
       -> DispatcherServlet -> Controller -> Response
~~~

If a security filter rejects the request, the controller may **not run**. A 401, 403, or redirect result depends on the authentication mechanism, entry point, and configured policy. The same URL can return 200 with valid credentials, 401 when credentials are missing, and 403 when already signed in but lacking permission.

**Two distinct phases to separate:**

1. **Startup/configuration:** Spring creates the `SecurityFilterChain` bean; the bean method uses `HttpSecurity` to **configure and build a filter chain**.
2. **Runtime/request:** `FilterChainProxy` selects the matching chain, and only then do the filters built at startup actually process the request.

Each request **does not re-run** `http.authorizeHttpRequests(...).httpBasic(...).build()`. Do not put request-specific logic directly inside the bean builder method as if that method were a controller.

### Components with distinct responsibilities

| Component | Role | What not to confuse it with |
| --- | --- | --- |
| `HttpSecurity` | Servlet web security configuration builder; wires configurers/filters and shared objects | Not a filter that directly receives HTTP requests |
| `SecurityFilterChain` | A set of security filters and a matcher condition for requests | Not merely a sequence of authorization rules |
| `FilterChainProxy` | Selects a chain and applies its filters to a request | Not created per request |
| `authorizeHttpRequests` | Configures HTTP authorization conditions | Does not itself decide which chain is selected |
| `securityMatcher` | Restricts the request scope of an `HttpSecurity`/chain | Different from `requestMatchers` inside authorization |
| `Authentication` | Current identity and authorities | Does not automatically imply sufficient permissions |
| `AuthorizationFilter` | Enforces the access policy produced by configuration | Does not directly verify passwords |

With standard Spring Boot Servlet applications, adding `spring-boot-starter-security` and declaring a `SecurityFilterChain` bean is how you explicitly define web security policy. If the application does not declare a suitable bean, Boot can provide a default chain; when you declare your own `SecurityFilterChain` bean, that default web security policy usually gives way to your application's configuration. Do not assume every project has the same chains/filters, because dependencies and configurations can differ.

## 2. What does `HttpSecurity` actually configure?

In Spring Security Servlet, `HttpSecurity` is a builder provided by Spring Security to define the policy for one chain. It combines **configurers** to create the filters and components used during request processing.

Short example (this is an **illustrative configuration snippet**; it must be placed in a `@Configuration` class with appropriate imports):

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/public/**").permitAll()
            .requestMatchers("/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

Read it by meaning, not only by syntax:

1. `http` is the builder provided by the framework when creating the bean.
2. `authorizeHttpRequests(...)` adds **URL authorization** configuration.
3. The lambda `authorize -> ...` receives the configurer object to register matchers and corresponding decisions.
4. `requestMatchers("/public/**").permitAll()` specifies that requests matching the matcher are allowed to proceed under this policy.
5. `requestMatchers("/admin/**").hasRole("ADMIN")` requires the `ROLE_ADMIN` authority under the default convention.
6. `anyRequest().authenticated()` is the fallback rule for requests that did not match preceding rules.
7. `httpBasic(Customizer.withDefaults())` enables HTTP Basic with the default settings applicable in this context.
8. `build()` finalizes the builder and returns the `SecurityFilterChain`. This bean is then used by the security infrastructure; `build()` does not call controllers itself.

**A `SecurityFilterChain` bean can include many kinds of configuration:** HTTP Basic/form login/resource server authentication, authorization, CSRF, session, exception handling, headers, CORS, and additional filters. Only configure what fits the application's security model; do not treat every configurer as required in every bean.

## 3. Lambda DSL: how to read it properly

The Lambda DSL is a configuration style that uses callbacks to group options by responsibility. This style makes rule placement clear and avoids relying on legacy `.and()` call chains.

~~~java
http
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/public").permitAll()
        .anyRequest().authenticated())
    .httpBasic(Customizer.withDefaults());
~~~

In `authorizeHttpRequests(auth -> auth...)`, the parameter `auth` **is not the current Authentication**. It is the builder/configurer object used to declare authorization. The author can name it `authorize`, `rules`, or `requests` as desired; it is just a lambda variable.

Some common patterns:

~~~java
// Pass specific options into the lambda:
http.csrf(csrf -> csrf.disable());

// Accept the configurer's default configuration:
http.httpBasic(Customizer.withDefaults());

// Define rules and evaluation order:
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/health").permitAll()
    .anyRequest().authenticated());
~~~

These three snippets **only illustrate syntax**; they are not a recommendation to disable CSRF by default. `csrf(csrf -> csrf.disable())` disables CSRF protection in the associated chain; you must evaluate the authentication/cookie/session mechanism and threat model before using it in a real environment.

### Distinguishing three styles

| Written in project | Meaning | Notes |
| --- | --- | --- |
| `http.httpBasic(Customizer.withDefaults())` | Enable the Basic configurer with default settings | Concise form when no customization is needed |
| `http.httpBasic(basic -> basic.realmName("demo"))` | Pass a callback to customize HTTP Basic | Can be used alongside other configurers |
| `http.authorizeHttpRequests(auth -> auth...)` | Declare multiple authorization rules | Rules are evaluated in order |
| `http.build()` | Produce a chain from the current configuration | Called at the end of the bean method |
| Legacy style using `.and()`/`antMatchers()` | Common in Spring Security 5 documentation | Do not copy verbatim into Spring Security 6 |

When migrating to Spring Security 6, you typically must replace `authorizeRequests/antMatchers` with `authorizeHttpRequests/requestMatchers` as appropriate. At the same time, many configurations require or encourage the lambda style in newer versions; check the API for the exact version your project uses. Do not automatically replace all matchers with plain path strings when the project requires HTTP methods, servlet paths, or custom matchers.

## 4. Three different kinds of "matching": securityMatcher, requestMatchers, controller

A very common source of bugs is seeing the word "matcher" and assuming they all do the same thing.

### 4.1. `securityMatcher(...)`: selects the scope of a security chain

Example:

~~~java
http
    .securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .anyRequest().authenticated())
    .httpBasic(Customizer.withDefaults());
~~~

`securityMatcher("/api/**")` means the chain being built only applies to requests matching `/api/**`. If a request does not match this matcher, `FilterChainProxy` checks the next chain (if any). Do not assume `anyRequest()` inside this chain protects the entire application: `anyRequest()` only covers requests **that have been selected into this chain**.

If a project declares only a chain restricted to `/api/**` and **has no matching chain for other URLs**, the remaining requests may not be protected by Spring Security at all. Therefore, when there are multiple chains, you must check all matchers and the fallback chain.

### 4.2. `requestMatchers(...)` in `authorizeHttpRequests`: selects a rule inside a chain

Example:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/reports").hasAuthority("REPORT_READ")
    .requestMatchers("/api/admin").hasRole("ADMIN")
    .anyRequest().authenticated());
~~~

Notice the explicit method distinction: `GET /api/reports` requires `REPORT_READ`, whereas a `POST` to the same URL does not automatically use this `GET` rule and may fall through to a later rule. Both authorization and CSRF (if applicable) can affect the outcome. When policies restrict by method, test the other methods as well to avoid gaps.

Rules are applied in **declaration order**; placing a broad matcher earlier can prevent later rules from ever being reached. `anyRequest()` should be at the end of the rule list.

### 4.3. Controller mappings are a step after the request passes security

A controller may define:

~~~java
@GetMapping("/api/reports")
String reports() {
    return "report";
}
~~~

The controller mapping determines which MVC handler runs, **not a security rule**. When the controller has no mapping for a request, 404 or 405 can appear after security has already allowed the request through. Conversely, a URL without a handler yet can still be rejected earlier by security.

### Quick comparison table

| Question | Where to check |
| --- | --- |
| Does the request enter chain A or chain B? | `securityMatcher`, `@Order`, and chain ordering |
| Within that chain, is it allowed or denied? | `authorizeHttpRequests` and authorities |
| How are credentials processed? | `httpBasic`, `formLogin`, resource server, or custom filter |
| Why did a POST return 403? | Authorization **and** CSRF configuration |
| Which controller handles the request? | MVC mapping; check after the security step |

## 5. The `build()` step: from DSL to SecurityFilterChain

The bean creation process can be understood in the following steps:

~~~text
Application creates the Spring ApplicationContext
    |
    v
Spring Security provides the HttpSecurity builder
    |
    v
@Configuration/@Bean executes
    |
    +--> calls configurers: authorizeHttpRequests, httpBasic, csrf...
    +--> records matchers, shared objects, and filter configurations
    |
    v
http.build()
    |
    v
SecurityFilterChain (matcher + created/assembled filters)
    |
    v
SecurityFilterChain is collected by Spring Security infrastructure
    |
    v
FilterChainProxy selects the chain at runtime for each request
~~~

More precisely, `HttpSecurity` implements Spring Security's builder mechanism. When `build()` is called, the framework runs internal initialization and configuration steps, then constructs a `DefaultSecurityFilterChain`. The detailed structure and exact filters depend on the version and active configurers.

**What is decided at build time:** chain-level matcher, which filters exist, the `AuthorizationManager` policy, authentication mechanisms, and exception handling.

**What is decided at request time:** which matcher the current request hits, concrete credentials, the established `Authentication`, authorities, CSRF token, authorization evaluation result, and response.

Calling `http.build()` twice on the same builder **is not how you create two independent chains**. For two chain beans, each bean method normally receives its own builder provided by the framework and builds once. Do not store an `HttpSecurity` singleton to share and mutate its configuration concurrently at runtime.

### When should you declare a `SecurityFilterChain` bean?

With Spring Boot Servlet, declare a bean to:

- Explicitly describe which endpoints are public, require login, or require permissions.
- Choose the appropriate authentication mechanism instead of accidentally relying on defaults.
- Specify behavior for CSRF/session/logout/exception handling as needed.
- Separate multiple policies by request group using multiple chains if required.

Once you have a custom bean, verify you include everything you need: Boot does not automatically inject all `permitAll/authenticated` rules or `httpBasic/formLogin` from its default configuration into every application-defined bean.

## 6. Runnable example: a chain with HTTP Basic and Lambda DSL

This example uses **Java 17, Spring Boot 3.3.5, Gradle, Spring MVC, and Spring Security**. It includes a public endpoint, an endpoint requiring authentication, an endpoint requiring an authority, an endpoint requiring a role, and a POST protected by CSRF. No database is needed; three in-memory accounts are for learning purposes only.

### 6.1. Project structure

~~~text
http-security-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   └── java/demo/security/
    │       ├── HttpSecurityDemoApplication.java
    │       ├── SecurityConfiguration.java
    │       └── DemoController.java
    └── test/
        └── java/demo/security/
            └── SecurityConfigurationTests.java
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'http-security-demo'
~~~

File `build.gradle`:

~~~groovy
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
~~~

The Spring Boot BOM manages Spring Security versions; do not pin separate versions for `spring-security-web` or `spring-security-config` without a compatibility reason. In real projects, you can use an existing Gradle wrapper and version catalog rather than creating a new project.

### 6.2. Application entry point

File `src/main/java/demo/security/HttpSecurityDemoApplication.java`:

~~~java
package demo.security;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpSecurityDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(HttpSecurityDemoApplication.class, args);
    }
}
~~~

### 6.3. Configuring SecurityFilterChain with lambdas

File `src/main/java/demo/security/SecurityConfiguration.java`:

~~~java
package demo.security;

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
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public/ping").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/reports")
                    .hasAuthority("REPORT_READ")
                .requestMatchers(HttpMethod.GET, "/api/admin")
                    .hasRole("ADMIN")
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-pass"))
            .roles("READER")
            .build();

        UserDetails analyst = User.withUsername("analyst")
            .password(encoder.encode("analyst-pass"))
            .authorities("REPORT_READ")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-pass"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(reader, analyst, admin);
    }
}
~~~

Read each decision of the builder:

1. **No `HttpSecurity`-level `securityMatcher`:** this chain applies by default to requests within the normal security scope of the application.
2. **GET `/public/ping`:** any caller is allowed; the `permitAll()` rule does not bypass the entire filter chain.
3. **GET `/api/reports`:** requires the exact authority `REPORT_READ`. User `analyst` has this authority.
4. **GET `/api/admin`:** requires `ROLE_ADMIN` via `hasRole("ADMIN")`. User `admin` has that role.
5. **Remaining requests:** require `authenticated()`, including `GET /api/me` and `POST /api/notes`.
6. **HTTP Basic:** credentials are read using HTTP Basic. `UserDetailsService` and `PasswordEncoder` provide username/password verification.
7. **CSRF:** the example does not call `csrf(...disable...)`, so it keeps default CSRF protection for requests that require checking. In particular, `POST /api/notes` needs a valid token in a test context.
8. **`build()`:** returns the configured `SecurityFilterChain` bean. The framework manages the bean to use when processing requests.

**Distinguishing role and authority:** `roles("ADMIN")` creates the authority `ROLE_ADMIN`. `hasRole("ADMIN")` looks up the authority with the default role prefix. `hasAuthority("REPORT_READ")` checks the exact string `REPORT_READ`; it does not prepend `ROLE_`.

### 6.4. Controller

File `src/main/java/demo/security/DemoController.java`:

~~~java
package demo.security;

import java.security.Principal;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/api/me")
    public String me(Principal principal) {
        return "hello " + principal.getName();
    }

    @GetMapping("/api/reports")
    public String reports() {
        return "quarterly report";
    }

    @GetMapping("/api/admin")
    public String admin() {
        return "admin console";
    }

    @PostMapping("/api/notes")
    public String createNote() {
        return "created";
    }
}
~~~

The controllers **do not declare permissions themselves**; URL protection comes from the web security configuration above. Elsewhere in a system, method security can be added via `@EnableMethodSecurity` and `@PreAuthorize`; that is a second mechanism to evaluate separately, not inferred solely from existing HTTP rules.

### 6.5. Using MockMvc to verify each rule

File `src/test/java/demo/security/SecurityConfigurationTests.java`:

~~~java
package demo.security;

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
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityConfigurationTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void publicPingDoesNotRequireLogin() throws Exception {
        mockMvc.perform(get("/public/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("pong"));
    }

    @Test
    void privateMeRequiresAuthentication() throws Exception {
        mockMvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongPasswordIsRejected() throws Exception {
        mockMvc.perform(get("/api/me").with(httpBasic("reader", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void correctBasicCredentialsReachController() throws Exception {
        mockMvc.perform(get("/api/me")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("hello reader"));
    }

    @Test
    void readerCannotReadReports() throws Exception {
        mockMvc.perform(get("/api/reports")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void analystHasReportAuthority() throws Exception {
        mockMvc.perform(get("/api/reports")
                .with(httpBasic("analyst", "analyst-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("quarterly report"));
    }

    @Test
    void readerIsNotAnAdmin() throws Exception {
        mockMvc.perform(get("/api/admin")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminHasRequiredRole() throws Exception {
        mockMvc.perform(get("/api/admin")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin console"));
    }

    @Test
    void postWithoutCsrfTokenIsRejected() throws Exception {
        mockMvc.perform(post("/api/notes")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void postWithAuthenticationAndCsrfTokenPasses() throws Exception {
        mockMvc.perform(post("/api/notes")
                .with(httpBasic("reader", "reader-pass"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("created"));
    }
}
~~~

`@SpringBootTest` loads the real ApplicationContext, and `@AutoConfigureMockMvc` configures MockMvc with the web layer and security filters. `httpBasic(...)` generates a Basic Authorization header to pass through the authentication flow; this test differs from using `@WithMockUser` or `user("...")` to mock a user. `csrf()` is a test post-processor that sends a valid token, not a replacement for the framework's real CSRF mechanism.

**Reading test results:** on the same `/api/reports`, `reader` is authenticated but lacks `REPORT_READ`, hence 403; `analyst` has `REPORT_READ`, hence 200. On `/api/me`, missing credentials give 401; valid Basic gives 200. For POST, even valid credentials must satisfy the CSRF requirement when enabled. Tests keep existing security policies rather than disabling them for convenience.

### 6.6. Running the application and observing HTTP

With a compatible Gradle installed and the file layout above:

~~~bash
gradle test
gradle bootRun
~~~

If the project has a Gradle wrapper, prefer `./gradlew test` and `./gradlew bootRun` (Windows: `gradlew.bat test`, `gradlew.bat bootRun`). This is an application using Spring libraries, so plain `javac`/`java` commands are insufficient without manually configuring the classpath. Java source, package, and file paths must match the example.

On the default port `localhost:8080`, you can use:

~~~bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/api/me
curl -i -u reader:reader-pass http://localhost:8080/api/me
curl -i -u reader:reader-pass http://localhost:8080/api/reports
curl -i -u analyst:analyst-pass http://localhost:8080/api/reports
curl -i -u admin:admin-pass http://localhost:8080/api/admin
curl -i -u reader:reader-pass -X POST http://localhost:8080/api/notes
~~~

Expected results with the configuration above (headers and error bodies may vary by version/settings):

| Request | HTTP status | Body when 200 | Primary reason |
| --- | --- | --- | --- |
| GET `/public/ping` without credentials | 200 | `pong` | `permitAll()` |
| GET `/api/me` without credentials | 401 | — | `authenticated()` + HTTP Basic challenge |
| GET `/api/me`, reader valid password | 200 | `hello reader` | Authentication succeeded |
| GET `/api/reports`, reader | 403 | — | Missing `REPORT_READ` |
| GET `/api/reports`, analyst | 200 | `quarterly report` | Sufficient authority |
| GET `/api/admin`, admin | 200 | `admin console` | Has `ROLE_ADMIN` |
| POST `/api/notes`, reader + Basic, missing CSRF token | 403 | — | CSRF checks state-changing requests |

**Why does the POST command have no 200 curl example?** The application does not expose an endpoint to issue CSRF tokens to clients. The example proves the POST branch succeeds via MockMvc `with(csrf())`, so there is no need to show a fake curl command with a nonexistent token. When building a real API, choose a strategy for issuing/attaching CSRF tokens or a CSRF policy fitting the session/cookie model.

## 7. Multiple SecurityFilterChains: ordering and fallback

When a project has multiple URL groups using different authentication mechanisms, you can declare **multiple `SecurityFilterChain` beans**. Spring Security infrastructure picks the **first chain that matches the request**; after selecting the chain, that chain's authorization rules are applied.

The following configuration example is a **standalone variant to explain chain selection**. If you want to apply it in the sample project, **replace the single previous `SecurityFilterChain` bean** with these two beans; do not add it verbatim as a third bean alongside the sample configuration.

~~~java
// Place in a @Configuration class with imports for HttpSecurity,
// Customizer, SecurityFilterChain, Order, Bean, and HttpMethod.

@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/public").permitAll()
            .anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}

@Bean
SecurityFilterChain remainingChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().denyAll())
        .build();
}
~~~

Chain selection table:

| Request | Selected chain | Rule |
| --- | --- | --- |
| GET `/api/public` | `apiChain`, `@Order(1)` | `permitAll()` |
| GET `/api/me` | `apiChain` | `authenticated()` |
| GET `/health` | `remainingChain` | `denyAll()` |
| GET `/` | `remainingChain` | `denyAll()` |

In this variant, `apiChain` **does not** inherit the `hasRole("ADMIN")` rule from the earlier example because the bean was replaced. Nor does it serve `/api/public` if the project lacks a corresponding controller: security may let it pass and then Spring MVC returns 404. This is the difference between **being allowed at the security layer** and **finding a handler**.

**Critical mistake:** writing a single chain with `securityMatcher("/api/**")` and thinking `anyRequest().authenticated()` protects `/login`, `/admin`, and endpoints outside `/api/**`. Without a fallback chain, requests outside scope may bypass Spring Security. Always verify the full list of chains, matchers, ordering, and actual protection scope.

When multiple chains are needed, each chain can choose its own mechanism (for example HTTP Basic for APIs, form login for UI), session management, and CSRF handling. This is an architectural decision that must be tested per endpoint group; do not randomly mix mechanisms just to make 401s go away.

## 8. Commonly misunderstood configurations

### 8.1. `authenticated()` does not itself define how to log in

`authenticated()` is an authorization condition: the request must carry an identity considered authenticated. It **does not create a user database**, does not parse JWTs, and does not enable a login page. The mechanism that establishes identity must come from the corresponding filter/provider such as HTTP Basic, form login, or bearer token authentication.

### 8.2. `permitAll()` differs from excluding a request from security

`permitAll()` allows a request under an authorization rule. Security filters can still run and other mechanisms may take effect (depending on configuration, request type, CSRF). Bypassing the Spring Security filter chain completely is a different decision and should not be done for an endpoint merely because it is public.

### 8.3. `httpBasic` does not by itself prove the system is stateless

HTTP Basic carries credentials on the request, but **session creation/storage policy, `SecurityContextRepository`, and other authentication mechanisms** are independent concerns. If you need a stateless API, you must explicitly configure the session policy and evaluate interactions with other filters. Do not infer a project is stateless merely by finding `httpBasic(Customizer.withDefaults())`.

### 8.4. Do not disable CSRF just because you see 403

CSRF is especially relevant for browser clients that automatically send authentication cookies. For POST/PUT/PATCH/DELETE requests, CSRF may reject before the controller runs; a 403 here does not prove the user lacks a role. Check request method, CSRF token, session/cookie, and filter logs before changing configuration.

### 8.5. `build()` does not mark someone as "logged in"

`build()` runs at bean creation time to assemble security filters; it **does not authenticate a specific user**. `AuthenticationManager` or authentication filters handle credentials at request/runtime. Seeing the bean method execute at startup and not on endpoint calls is normally the expected behavior.

### 8.6. Adding `@EnableWebSecurity` does not replace concrete configuration

In Spring Boot Servlet with the security starter, web security infrastructure is typically activated via auto-configuration. The annotation may be needed in self-configured Spring Framework apps or specific cases, but it **does not replace** the `SecurityFilterChain` bean, matchers, filters, and authentication logic you actually need.

### 8.7. A broad matcher before a specific matcher breaks policy

Compare:

~~~java
// Problematic: the broad rule already matches GET /api/admin
.requestMatchers("/api/**").authenticated()
.requestMatchers("/api/admin").hasRole("ADMIN")
~~~

with:

~~~java
// Specific rule first, fallback after
.requestMatchers("/api/admin").hasRole("ADMIN")
.requestMatchers("/api/**").authenticated()
~~~

Within the same chain, authorization matchers are normally evaluated in order; organize them from specific to general so important conditions are not shadowed. Do not look at a single `hasRole` line and conclude the URL is properly protected.

## 9. Observing the build and request processing

### 9.1. Observing at startup

Place a breakpoint or log in the bean method:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    System.out.println("Configuring SecurityFilterChain");
    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

This is a **separate illustrative configuration snippet**. When the bean method is initialized once in a normal context, the message may be printed **once** at startup. Do not treat the print count as an absolute contract if the `ApplicationContext` is recreated in tests/hot reload; the main point is that builder code runs on the **bean lifecycle**, not on every HTTP request.

At startup, Spring Security normally logs the filters protecting requests. The filter list and log level depend on the version. You can enable DEBUG in a learning environment:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Then correlate chain creation, protected requests, and statuses. Avoid enabling overly broad TRACE/DEBUG in production because logs can be verbose and contain sensitive data.

### 9.2. Observing at runtime

For GET `/api/reports`, compare two requests:

~~~text
GET /api/reports   Basic reader:reader-pass
  -> Authentication: reader, authorities=[ROLE_READER]
  -> authorization: requires REPORT_READ
  -> denied -> 403

GET /api/reports   Basic analyst:analyst-pass
  -> Authentication: analyst, authorities=[REPORT_READ]
  -> authorization: requires REPORT_READ
  -> granted -> controller -> 200 "quarterly report"
~~~

This is a **logical outcome diagram**, not literal Spring Security log output. When analyzing a real project, do not rely on a fixed filter name or fixed log string: versions, multiple chains, and configurers can change which components appear.

An orderly debugging workflow:

1. Identify the HTTP method, path, headers, and cookies of the failing request.
2. Check which `SecurityFilterChain` bean and `securityMatcher` apply, especially when `@Order` is used.
3. Check which `authorizeHttpRequests` rule matches; pay attention to ordering and `anyRequest`.
4. If identity is missing, inspect the authentication mechanism, credentials, and provider.
5. If identity is present but denied, inspect authorities and role prefix; for unsafe methods, inspect CSRF.
6. Once security allows it, inspect the MVC handler and business logic.

### 9.3. Distinguishing common HTTP statuses

| Status | Reasonable interpretation | What to check |
| --- | --- | --- |
| 200 | Security passed and handler succeeded | Is it the expected handler and response? |
| 401 | With Basic, usually missing/invalid credentials | `Authorization` header, user store, password encoder |
| 403 | Denied permission or another mechanism like CSRF | Authorities, matcher, CSRF token |
| 302 | Possibly a redirect to form login | Is the entry point and form login enabled? |
| 404/405 | Handler missing/method unsupported after security | Controller mapping, method, and path |

Do not fix every error with `anyRequest().permitAll()` or `csrf(csrf -> csrf.disable())`. Identify the true cause across chain selection, authentication, authorization, CSRF, or MVC routing.

## 10. Knowledge check and practice exercises

1. Explain why `HttpSecurity` is called a builder and `SecurityFilterChain` is the output. When does `build()` run, and when does `AuthorizationFilter` run?
2. In the main example, replace `.requestMatchers(HttpMethod.GET, "/api/reports")` with a method-unrestricted matcher. Predict which rule `POST /api/reports` hits, then analyze CSRF requirements and handler existence.
3. Swap the order of `anyRequest().authenticated()` and the `hasRole("ADMIN")` rule (if the DSL rejects that order, explain the meaning of ordering and the `anyRequest` contract). Why should broad matchers come last?
4. Call the same `GET /api/reports` with `reader` and `analyst`. Trace **request → authentication → authority → authorization → response**; which steps differ?
5. Try `POST /api/notes` with valid Basic credentials and no CSRF token. From this 403, can you conclude the user lacks a role? What evidence is needed?
6. Split the configuration into two chains with `@Order(1)` and `securityMatcher("/api/**")`. Write a table for three URLs inside/outside the prefix and state what the fallback chain will do.
7. If the application only has `securityMatcher("/api/**")`, which chain will `GET /internal/secret` match? Why must you test requests that **do not** match the chain?
8. Given a Spring Security 5.x project still using `WebSecurityConfigurerAdapter` and `antMatchers`, describe how to migrate the mental model to a `SecurityFilterChain` bean and Spring Security 6 Lambda DSL.
9. If a MockMvc test returns 200 while curl returns 401, check whether the test applied security filters first, and only then analyze the rules.
10. Try explaining why `@WithMockUser` can pass an `authenticated()` rule without checking a password. When you want to test the real authentication path of HTTP Basic, what tool should you use?

**Checklist after configuring successfully on your own:** each URL group matches its intended chain; every chain has a clear fallback rule; authentication mechanisms are intentionally enabled; roles/authorities are compared correctly; CSRF/session are decided based on client and threat model; the code calls `build()` when creating the bean; tests prove both **allowed** and **denied** paths.

If you can fully explain the flow "**`HttpSecurity` declares configuration → build `SecurityFilterChain` at startup → `FilterChainProxy` selects chain at request time → authentication and authorization filters → controller or rejection response**", you have a solid foundation for reading more complex Servlet Security configurations.
