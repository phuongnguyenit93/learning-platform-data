# Migrating `WebSecurityConfigurerAdapter` to Bean-Based Configuration in Spring Security

`WebSecurityConfigurerAdapter` used to be the familiar way to configure `HttpSecurity`, `AuthenticationManagerBuilder`, and `WebSecurity` by extending a class and overriding `configure(...)`. Spring Security **5.7** marked the adapter as deprecated; **Spring Security 6.0** removed it. The replacement is **bean-based configuration**: declaring `SecurityFilterChain`, `UserDetailsService`/`AuthenticationProvider`, `PasswordEncoder`, and any needed supporting beans. Newer versions move toward the **lambda DSL**; Spring Security 7 removed the legacy `.and()` and `authorizeRequests` configuration APIs.

This lesson targets **Servlet/Spring MVC**, Spring Security 6.x, Java 17+, with a Spring Boot 3.5.7 example and 12 HTTP tests using MockMvc. For WebFlux, the proper types are `SecurityWebFilterChain` and `ServerHttpSecurity`; do not apply servlet configuration verbatim to the reactive stack.

## 1. Migration Map: What Bean Does Each Part of the Adapter Become?

| Previously | Responsibility | After Migration |
| --- | --- | --- |
| `extends WebSecurityConfigurerAdapter` | Centralize all security configuration | Standard `@Configuration` class with clear `@Bean`s |
| `configure(HttpSecurity http)` | URL authorization, HTTP Basic/form login, CSRF, CORS, session, headers | `@Bean SecurityFilterChain securityFilterChain(HttpSecurity http)` |
| `configure(AuthenticationManagerBuilder auth)` | User source, providers, authentication mechanism | `UserDetailsService`, `AuthenticationProvider`, `PasswordEncoder`, or appropriate manager |
| `configure(WebSecurity web)` | Exclude URLs from Spring Security filters | `WebSecurityCustomizer` when truly needed; `permitAll` is usually preferred |
| `authenticationManagerBean()` | Expose manager for injection elsewhere | Optional `AuthenticationManager` bean |
| Multiple adapters with `@Order` | URL regions with separate filter policies | Multiple `SecurityFilterChain` beans with `@Order` and `securityMatcher` |
| `@EnableGlobalMethodSecurity` | Protect methods via annotations | `@EnableMethodSecurity` |

**You do not necessarily need to create every bean in this table.** If the app is an OAuth2 Resource Server accepting JWTs, you can use `SecurityFilterChain` + a JWT decoder/converter instead of a user/password store. If a web app needs database login, `UserDetailsService` and `PasswordEncoder` beans are typically needed, though that does not mean you must also expose a global `AuthenticationManager`.

You must preserve **before-and-after security behavior**: which endpoints are public, which require roles/scopes, which URLs are blocked, which HTTP methods are allowed, and how session/CSRF/CORS/login/logout behave. Fixing compilation errors alone does not prove a successful migration.

## 2. Before and After with a Simple `HttpSecurity`

### Legacy configuration (applies only to Spring Security 5.x)

~~~java
// Historical fragment: does not compile on Spring Security 6+.
@Configuration
@EnableWebSecurity
public class LegacySecurityConfig extends WebSecurityConfigurerAdapter {
    @Override
    protected void configure(HttpSecurity http) throws Exception {
        http.authorizeRequests()
            .antMatchers(HttpMethod.GET, "/public/ping").permitAll()
            .antMatchers("/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated()
            .and()
            .httpBasic();
    }
}
~~~

Note that the snippet above only expresses HTTP policy; it omits account sources and complete imports. If you move the old code verbatim into Spring Security 6, the first error is that the adapter class no longer exists, and `antMatchers`/`authorizeRequests` are no longer compatible.

### Bean-based configuration (Spring Security 6.x)

~~~java
// Fragment to place inside a @Configuration class.
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/public/ping").permitAll()
            .requestMatchers("/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults());
    return http.build();
}
~~~

Key imports:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
~~~

Step-by-step explanation:

1. Remove `extends WebSecurityConfigurerAdapter`; the configuration class typically uses `@Configuration` directly.
2. Change `protected void configure(HttpSecurity)` into a `@Bean` method **returning** `SecurityFilterChain`.
3. Replace `authorizeRequests().antMatchers(...)` with `authorizeHttpRequests(auth -> auth.requestMatchers(...))`.
4. Replace chained `.and().httpBasic()` with `.httpBasic(Customizer.withDefaults())`.
5. End with `return http.build();`. Without the expected filter chain, requests may be handled by another default chain or hit a configuration gap.
6. Preserve matcher order and protection levels; apply first-match rules inside `authorizeHttpRequests`.

Spring Boot may auto-create default web security when no custom `SecurityFilterChain` exists. Once you register your application's chain, **do not assume** prior defaults still apply. Explicitly write the `anyRequest()` rule and test URLs missing from your inventory.

## 3. Migrating Authentication Away from `AuthenticationManagerBuilder`

### 3.1. In-memory users

Old approach:

~~~java
// OLD — fragment inside configure(AuthenticationManagerBuilder auth).
auth.inMemoryAuthentication()
    .withUser("reader")
    .password("{noop}read123")
    .roles("USER");
~~~

New approach for demo/testing:

~~~java
// Fragment inside @Configuration, with corresponding dependencies and imports.
@Bean
PasswordEncoder passwordEncoder() {
    return new BCryptPasswordEncoder();
}

@Bean
UserDetailsService userDetailsService(PasswordEncoder encoder) {
    UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("read123"))
            .roles("USER")
            .build();
    return new InMemoryUserDetailsManager(reader);
}
~~~

Types to import:

~~~java
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
~~~

In production applications, never hardcode passwords in source or store `{noop}...` strings; use a protected user store and password hashing. `User.withDefaultPasswordEncoder()` appears in some older migration examples for brevity, but should not be used in production deployments.

If old code used `auth.jdbcAuthentication()`, consider `JdbcUserDetailsManager` with the appropriate `DataSource` and schema; if using LDAP, use the LDAP authentication factories/providers. If using OAuth2/OIDC/JWT or custom authentication, preserve the actual authentication mechanism instead of swapping in an in-memory user just to make the build pass.

### 3.2. Do you need an `AuthenticationManager` bean?

**Not every application needs one.** Spring Security can configure the manager for the filter chain automatically when `UserDetailsService`/providers are properly declared. If a service or custom controller needs to inject `AuthenticationManager` directly, you can opt in:

~~~java
// Optional fragment; add only when a global manager is truly needed.
@Bean
AuthenticationManager authenticationManager(
        AuthenticationConfiguration configuration) throws Exception {
    return configuration.getAuthenticationManager();
}
~~~

Imports:

~~~java
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.config.annotation.authentication.configuration.AuthenticationConfiguration;
~~~

If multiple providers are present or a custom manager is used for a chain, check provider order, bean wiring, and the specific authentication mechanism. `http.authenticationManager(customManager)` can configure a chain-specific manager; do not add both a global bean and a chain-local manager without understanding the authentication flow.

**Roles differ from authorities:** `User.roles("ADMIN")` creates `ROLE_ADMIN`, and `hasRole("ADMIN")` checks `ROLE_ADMIN`. `hasAuthority("ADMIN")` checks exact `ADMIN`, without adding a prefix. When migrating from JWT or a database, do not change `hasRole`/`hasAuthority` without tests confirming how claims/roles are mapped.

## 4. Migrating `configure(WebSecurity)`: `ignoring` or `permitAll`?

Legacy adapter code:

~~~java
// OLD: fragment inside configure(WebSecurity web).
web.ignoring().antMatchers("/assets/**");
~~~

The new bean can be:

~~~java
// @Bean fragment inside @Configuration.
@Bean
WebSecurityCustomizer webSecurityCustomizer() {
    return web -> web.ignoring().requestMatchers("/assets/**");
}
~~~

However, this is **not always the best choice**. `WebSecurityCustomizer` with `ignoring` makes requests **bypass the Spring Security filter chain entirely**. That also bypasses security headers and other filters managed by Spring Security. For public resources, Spring Security documentation recommends considering **`permitAll`**:

~~~java
// Fragment inside SecurityFilterChain bean.
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/assets/**", "/favicon.ico").permitAll()
    .anyRequest().authenticated()
);
~~~

`permitAll` allows public requests **past authorization** while keeping other filters active. If `/assets/**` contains a sensitive endpoint, that remains a design flaw; never open `/**` just to "make static files work." For standard Spring Boot resources, `PathRequest.toStaticResources().atCommonLocations()` can be used when appropriate, after confirming which locations the app actually serves.

## 5. Migrating Multiple Adapters to Multiple `SecurityFilterChain`s

When API and web areas require distinct policies, register multiple beans with explicit ordering. This is a **standalone fragment**, not combined with the runnable configuration in Section 6:

~~~java
// Fragment belonging to a @Configuration class; import @Order.
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults());
    return http.build();
}

@Bean
SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/public/ping").permitAll()
            .anyRequest().denyAll()
        )
        .httpBasic(Customizer.withDefaults());
    return http.build();
}
~~~

`@Order` imports `org.springframework.core.annotation.Order`. A request is routed by `FilterChainProxy` through the **first matching chain**; remaining chains do not apply. Within each chain, `authorizeHttpRequests` again picks the **first matching rule**. Thus there are two ordering levels:

- `http.securityMatcher("/api/**")` defines the scope **of the entire chain**.
- `auth.requestMatchers("/api/admin/**")` applies **inside the selected chain**.
- `anyRequest()` is the fallback **within the active chain**; it does not protect every URL if the chain already has a narrower `securityMatcher`.

If there is no fallback chain and a request falls outside every `securityMatcher`, Spring Security will not protect that request. If a chain only has `securityMatcher("/api/**")`, the default `/login` endpoint may fall outside the chain and fail to work as expected; test login/logout URLs if the app uses form login.

A serious bug:

~~~java
// WRONG: priority-1 chain covers /api/admin/** too.
@Bean
@Order(1)
SecurityFilterChain openEverything(HttpSecurity http) throws Exception {
    http.securityMatcher("/**")
        .authorizeHttpRequests(auth -> auth.anyRequest().permitAll());
    return http.build();
}
~~~

If an admin chain has `@Order(2)`, it is never selected for admin URLs because the first chain already matched. Likewise, within a single chain:

~~~java
// WRONG: broad rule comes first and shadows admin rule.
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").permitAll()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().denyAll()
);
~~~

Place sensitive matchers before broader ones, and verify both anonymous and under-privileged users are blocked.

## 6. Runnable Example: Spring Boot 3.5.7 + Java 17 + MockMvc

The demo includes **one** `SecurityFilterChain`, three BCrypt-hashed in-memory accounts, a public GET, an authenticated-user GET, an admin-only GET, and a POST requiring both an authority and CSRF. It illustrates beans replacing the adapter and realistic security tests without database dependencies.

### 6.1. Structure

~~~text
bean-security-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/migration/
    │   ├── DemoApplication.java
    │   ├── SecurityConfig.java
    │   └── DemoController.java
    └── test/java/com/example/migration/
        └── SecurityMigrationTest.java
~~~

### 6.2. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>bean-security-demo</artifactId>
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
~~~

### 6.3. `DemoApplication.java`

~~~java
package com.example.migration;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 6.4. `SecurityConfig.java`

~~~java
package com.example.migration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class SecurityConfig {
    @Bean
    public SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public/ping").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .requestMatchers(HttpMethod.GET, "/api/me").authenticated()
                .requestMatchers(HttpMethod.POST, "/api/notes")
                    .hasAuthority("NOTE_WRITE")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable);

        // Default CSRF remains enabled: POST requires a token.
        return http.build();
    }

    @Bean
    public PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    public UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
                .password(encoder.encode("read123"))
                .roles("USER")
                .build();

        UserDetails editor = User.withUsername("editor")
                .password(encoder.encode("edit123"))
                .authorities("ROLE_USER", "NOTE_WRITE")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin123"))
                .roles("ADMIN")
                .build();

        return new InMemoryUserDetailsManager(reader, editor, admin);
    }
}
~~~

`SecurityConfig` itself provides the three beans responsible for what the adapter previously handled. `@SpringBootApplication` scans the `com.example.migration` package, so there is no need to manually register `springSecurityFilterChain` as in raw Servlet configs.

### 6.5. `DemoController.java`

~~~java
package com.example.migration;

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
        return principal.getName();
    }

    @GetMapping("/admin/report")
    public String report() {
        return "admin-report";
    }

    @PostMapping("/api/notes")
    public String createNote() {
        return "created";
    }

    @GetMapping("/ops/hidden")
    public String hidden() {
        // Real handler exists; only the denyAll rule blocks access.
        return "should-not-be-seen";
    }
}
~~~

### 6.6. `SecurityMigrationTest.java`

~~~java
package com.example.migration;

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
class SecurityMigrationTest {
    @Autowired MockMvc mvc;

    @Test
    void anonymousCanReadPublicPing() throws Exception {
        mvc.perform(get("/public/ping"))
           .andExpect(status().isOk())
           .andExpect(content().string("pong"));
    }

    @Test
    void anonymousCannotReadMe() throws Exception {
        mvc.perform(get("/api/me"))
           .andExpect(status().isUnauthorized());
    }

    @Test
    void correctCredentialsCanReadMe() throws Exception {
        mvc.perform(get("/api/me").with(httpBasic("reader", "read123")))
           .andExpect(status().isOk())
           .andExpect(content().string("reader"));
    }

    @Test
    void invalidPasswordIsRejected() throws Exception {
        mvc.perform(get("/api/me").with(httpBasic("reader", "wrong")))
           .andExpect(status().isUnauthorized());
    }

    @Test
    void anonymousCannotReadAdmin() throws Exception {
        mvc.perform(get("/admin/report"))
           .andExpect(status().isUnauthorized());
    }

    @Test
    void readerCannotReadAdmin() throws Exception {
        mvc.perform(get("/admin/report")
                .with(httpBasic("reader", "read123")))
           .andExpect(status().isForbidden());
    }

    @Test
    void adminCanReadAdminReport() throws Exception {
        mvc.perform(get("/admin/report")
                .with(httpBasic("admin", "admin123")))
           .andExpect(status().isOk())
           .andExpect(content().string("admin-report"));
    }

    @Test
    void editorCannotPostWithoutCsrfToken() throws Exception {
        mvc.perform(post("/api/notes")
                .with(httpBasic("editor", "edit123")))
           .andExpect(status().isForbidden());
    }

    @Test
    void anonymousWithCsrfStillNeedsAuthentication() throws Exception {
        mvc.perform(post("/api/notes").with(csrf()))
           .andExpect(status().isUnauthorized());
    }

    @Test
    void readerWithCsrfStillLacksAuthority() throws Exception {
        mvc.perform(post("/api/notes")
                .with(httpBasic("reader", "read123"))
                .with(csrf()))
           .andExpect(status().isForbidden());
    }

    @Test
    void editorWithCsrfAndAuthorityCanPost() throws Exception {
        mvc.perform(post("/api/notes")
                .with(httpBasic("editor", "edit123"))
                .with(csrf()))
           .andExpect(status().isOk())
           .andExpect(content().string("created"));
    }

    @Test
    void unlistedEndpointIsDeniedEvenForAdmin() throws Exception {
        mvc.perform(get("/ops/hidden")
                .with(httpBasic("admin", "admin123")))
           .andExpect(status().isForbidden());
    }
}
~~~

Tests call HTTP Basic with credentials from the demo user store using `SecurityMockMvcRequestPostProcessors.httpBasic`; this exercises the real filters and authentication of the sample (unlike `@WithMockUser`, which only mocks an identity). Spring Security Test's `csrf()` supplies a valid CSRF token for POSTs in a test context.

Run from the project root with JDK 17+ and Maven:

~~~bash
mvn test
~~~

**Expected result:** all 12 JUnit `@Test` methods pass without assertion failures. Maven logs depend on the environment, so there is no fixed stdout string. After tests pass, you can run:

~~~bash
mvn spring-boot:run
~~~

In another terminal, test the GET endpoints of the demo application:

~~~bash
curl -i http://localhost:8080/public/ping
curl -i -u reader:read123 http://localhost:8080/api/me
curl -i -u reader:read123 http://localhost:8080/admin/report
curl -i -u admin:admin123 http://localhost:8080/admin/report
~~~

With this configuration, the expected HTTP statuses are **200, 200, 403, 200** respectively, and the bodies of the first two requests are `pong` and `reader`. Account data is strictly for local runs; never deploy a sample with hardcoded credentials to a public environment.

**Sample boundaries:** No database, JWT, OAuth2 login, session logout, custom CORS, or multiple concurrent chains are included yet. Those variants must be migrated and tested separately rather than inferred from the 12 demo tests passing.

## 7. Other Configurations to Migrate to the Lambda DSL

In a real application, removing the adapter can drop several security settings if you only copy `authorizeHttpRequests`. Example lambda configuration fragment:

~~~java
http
    .csrf(csrf -> csrf.ignoringRequestMatchers("/webhooks/signed/**"))
    .sessionManagement(session -> session
        .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED))
    .headers(headers -> headers
        .frameOptions(frame -> frame.sameOrigin()));
~~~

Import `org.springframework.security.config.http.SessionCreationPolicy`. This is **not a mandatory default pattern**. Only ignore CSRF for webhooks when webhook verification genuinely relies on signatures/secrets rather than login cookies. Only use `frameOptions.sameOrigin()` if there is a requirement to embed content in same-origin frames. For pure Bearer-token APIs not backed by cookies, CSRF policy may differ; assess the client/threat model before deciding.

Common changes accompanying an upgrade to Spring Boot 3/Spring Security 6:

- Spring Framework 6/Boot 3 requires **Java 17+**.
- Servlet APIs and related types use the `jakarta.*` namespace, such as `jakarta.servlet.Filter` instead of `javax.servlet.Filter`.
- `@EnableGlobalMethodSecurity(prePostEnabled = true)` is replaced by `@EnableMethodSecurity`. If using `@PreAuthorize`, still verify method security is enabled and Spring-managed beans are invoked via proxies.
- `antMatchers`/`mvcMatchers` must move to the appropriate `requestMatchers`. Do not assume differences between Ant matchers, MVC matchers, servlet paths, and context paths will leave real URLs unaffected.
- With Spring Security 7, use the lambda DSL and `authorizeHttpRequests`; do not keep `authorizeRequests` or `.and()` chaining.
- `hasRole("ADMIN")` is not equivalent to `hasAuthority("ADMIN")`; role/authority mappings can shift when changing providers or JWT converters.

**Note on `@PreAuthorize`:** migrating the HTTP chain does not guarantee method-level authorization runs. Methods requiring permissions must be called through Spring proxies (self-invocation on the same bean can bypass advice) and tested against the real bean.

## 8. Verifying Correct Behavior After Migration

Before editing configurations, build a behavior matrix. In the runnable example from Section 6:

| Request | Anonymous | Reader | Editor | Admin |
| --- | --- | --- | --- | --- |
| `GET /public/ping` | 200 | 200 | 200 | 200 |
| `GET /api/me` | 401 | 200 | 200 | 200 |
| `GET /admin/report` | 401 | 403 | 403 | 200 |
| `POST /api/notes` with valid CSRF token | 401 | 403 | 200 | 403 |
| `POST /api/notes` without CSRF token | 403 | 403 | 403 | 403 |
| `GET /ops/hidden` | 401 or denied per entry point | 403 | 403 | 403 |

The table reflects **HTTP Basic + default CSRF** in the sample. In form-login apps, anonymous callers may receive a **302 redirect**; JWT resource servers typically use different responses/headers; do not force every system onto a single status set during migration. What must be preserved is *who may access what* and each client type's HTTP contract.

Specifically distinguish two causes:

- `POST` gets **403 due to CSRF** when missing a token.
- `POST` with valid CSRF but lacking `NOTE_WRITE` gets **403 due to authorization**.

Testing only a `403` on a POST without a token can create a **false sense of security** because broken authorization rules remain undetected. Similarly, a 404 on a nonexistent URL does not prove the path is protected; the sample includes a real `/ops/hidden` handler to test `denyAll`.

For an application with multiple filter chains, add a "which chain was selected" column to the matrix: URLs under `/api/**`, URLs right on the prefix boundary, `/login`/`/logout` URLs, and URLs belonging to no chain. Test both GET/POST and look-alike paths like `/adminish` to avoid faulty matchers.

## 9. Execution Workflow in a Codebase

1. **Establish baseline:** list endpoints, HTTP methods, roles/authorities, login/logout, sessions, CSRF, CORS, custom filters, 401/403/302 responses, and security headers. Run existing tests if the project still builds.
2. **Extract each override:** `configure(HttpSecurity)` into `SecurityFilterChain`; `configure(AuthenticationManagerBuilder)` into user/provider/password beans; `configure(WebSecurity)` into `WebSecurityCustomizer` or explicitly evaluated `permitAll`.
3. **Update the DSL:** `authorizeRequests`/`antMatchers`/`.and()` into `authorizeHttpRequests`/`requestMatchers`/lambdas; review specific/broad matchers and HTTP methods.
4. **Preserve auth flow:** keep the right `PasswordEncoder`, datasource/LDAP/JWT setup, custom authentication providers, exception handlers, and remember-me if used. Avoid creating unnecessary managers or accidentally activating other default authentication mechanisms.
5. **Handle multi-chain:** configure `@Order`, `securityMatcher`, and fallbacks. Every request must enter its designed chain; never place a public `/**` chain at highest priority.
6. **Verify web and method security:** verify CSRF, sessions, CORS, headers, login/logout URLs, `@EnableMethodSecurity`, and proxy-based invocations.
7. **Run regression tests:** real users/bad credentials, anonymous callers, missing/valid roles, denied URLs, POST with/without CSRF, new URLs, and changed paths; if using JWT, also test claims mapping and expiration.
8. **Validate on staging:** confirm HTTP statuses, redirects, headers, and filter-chain selection in a realistic environment; verify 401/403 observability before rolling out to production.

Never register two `SecurityFilterChain` beans protecting `/**` with overlapping policies without explicit ordering. If a new variant "leaks" an admin URL, treat it as a migration bug even if the application runs.

## 10. Common Errors and Diagnostics

**(a) Creating `SecurityFilterChain` but forgetting `return http.build()`.** The bean method does not produce the expected chain; verify a clean build and check that the Spring context contains the expected bean.

**(b) Deleting the adapter and losing the user store.** `configure(AuthenticationManagerBuilder)` is gone, but no new `UserDetailsService`/provider exists yet. Endpoints all return 401, or startup falls back to unexpected default authentication. Test login with valid and invalid credentials instead of relying solely on `@WithMockUser`.

**(c) A `SecurityFilterChain` exists, yet sensitive URLs match no chain.** `securityMatcher("/api/**")` does not cover `/admin/**`. Add an appropriate fallback; remember `anyRequest` applies only inside the selected chain.

**(d) Overly broad `permitAll` or shadowed matchers.** `/api/**` before `/api/admin/**` makes admin public too. Check top-to-bottom; the first matching matcher decides.

**(e) Moving static resources to `WebSecurityCustomizer.ignoring` unthinkingly.** Ignored requests skip the entire security filter chain, including security headers. Prefer `permitAll` when you want public access while keeping protective filters.

**(f) Confusing `hasRole` and `hasAuthority`.** `ROLE_ADMIN` differs from `ADMIN`. When changing user stores/providers/JWT converters, role prefixes may change; write positive and negative tests for both.

**(g) POST receives 403 even though the user has sufficient permissions.** The CSRF token may be missing. In authorization tests, supply a valid `csrf()` token before asserting permissions; do not rush to disable CSRF app-wide.

**(h) Login path is no longer served by the chain.** If `securityMatcher` only covers `/api/**`, `/login` may fall outside its scope. For form login, configure login page/processing URLs inside the protected scope and test redirects/POSTs accurately.

**(i) Method security stops working.** `@EnableMethodSecurity` is missing, or methods are invoked via `new` or self-invocation so interceptors do not run. Test Spring beans directly with denied cases; do not infer from HTTP matchers that method-level policy is active.

**(j) Mixing Servlet/Reactive or Jakarta.** `HttpSecurity` differs from `ServerHttpSecurity`. Spring Boot 3 moves most Servlet APIs to `jakarta.*`; fix dependencies/imports properly instead of adding old Spring Security 5 artifacts to a new project.

**(k) Seeing an `AuthenticationManager` bean and assuming all chains use the same provider.** A chain may configure a dedicated manager or different JWT decoder; test each auth method and chain-selection path.

**(l) Relying on the wrong defaults.** A custom `SecurityFilterChain` can disable Spring Boot's default web-security chain. Define explicit URL policies, check unlisted URLs, and test HEAD/OPTIONS if required by the app.

## 11. Acceptance Checklist

- [ ] Compatible Spring Boot, Spring Framework, and Spring Security versions, Java 17+, no invalid javax/jakarta mixing.
- [ ] No remaining `WebSecurityConfigurerAdapter` inheritance in the new configuration.
- [ ] `@Bean SecurityFilterChain` present with `return http.build()` and lambda DSL.
- [ ] Specific matchers precede broad matchers; `/admin/**` and sensitive APIs are not exposed.
- [ ] Public, authenticated, role/authority, and fallback APIs match baseline behavior.
- [ ] With multiple chains, `@Order`, `securityMatcher`, and fallback cover all intended URLs.
- [ ] `UserDetailsService`/providers and `PasswordEncoder` match real account data; no plaintext passwords in production.
- [ ] No unnecessary `AuthenticationManager` exposed; if present, it is clear which providers are used.
- [ ] Distinguished `WebSecurityCustomizer.ignoring` from `permitAll` and verified security headers.
- [ ] CSRF/CORS/session/form login/logout/custom filters/error handling migrated and tested.
- [ ] If using `@PreAuthorize`, `@EnableMethodSecurity` is present and tests invoke Spring beans through proxies.
- [ ] Tests cover both valid/invalid credentials and sufficient/missing authorities; POSTs tested with valid CSRF.
- [ ] Unregistered URLs deny per policy; do not treat 404 as passing authorization.
- [ ] Build/tests run prior to release; 401/403/302 responses and filter chains reviewed on staging.

## 12. Official Documentation

- Spring Team — *Spring Security without the WebSecurityConfigurerAdapter*: https://spring.io/blog/2022/02/21/spring-security-without-the-websecurityconfigureradapter
- Spring Security 5.8 & 6.0 release, adapter removal: https://spring.io/blog/2022/11/21/spring-security-5-8-and-6-0-are-now-ga/
- Spring Security — Java Configuration/Multiple SecurityFilterChains: https://docs.spring.io/spring-security/reference/servlet/configuration/java.html
- Spring Security — Authorize HttpServletRequests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Authentication architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — MockMvc Integration: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/
- Spring Security 7 — What's New: https://docs.spring.io/spring-security/reference/7.0/whats-new.html

**Satisfactory when:** The new configuration uses `SecurityFilterChain` and appropriate authentication beans, and all URL/role/CSRF tests still reflect the exact policy. The migration must preserve actual access permissions, including on infrequently called or unlisted URLs.
