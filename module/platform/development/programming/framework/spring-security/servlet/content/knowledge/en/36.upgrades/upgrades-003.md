# From WebSecurityConfigurerAdapter to Configuration Beans

**Module:** Spring Security – Servlet  
**Parent topic:** Upgrades

## 1. Why must we migrate?

In older Spring Security Servlet projects, security configuration was commonly gathered into a single class extending `WebSecurityConfigurerAdapter`. That class overrode `configure(HttpSecurity)`, `configure(WebSecurity)`, and `configure(AuthenticationManagerBuilder)`. While once popular, this approach coupled distinct responsibilities into one class with opaque lifecycle and ordering behavior.

Starting in **Spring Security 5.7**, `WebSecurityConfigurerAdapter` was deprecated; in **Spring Security 6** it was removed. Spring Boot 3 uses Spring Security 6 and the Jakarta EE ecosystem, so any project upgrading from Boot 2/Security 5 must move to **component-based configuration beans**.

This is not merely renaming a class. The upgrade must preserve actual behavior:

- Which paths are public, and which require authentication and specific authorities?
- Does the API use HTTP Basic, Bearer tokens, or another mechanism? Does the web browser use form login or OAuth2 Login?
- Is CSRF still enforced on state-changing requests per the threat model?
- Where are users and passwords verified from? Is `PasswordEncoder` compatible with existing hashes?
- Does `AuthenticationProvider`/`AuthenticationManager` have custom logic that needs migration?
- Do `web.ignoring()`, login/logout URLs, request cache, CORS, headers, sessions, or exception handling change semantics?
- Does method security (`@PreAuthorize`) still work after changing configuration annotations?
- If there are multiple filter chains, do `@Order` and `securityMatcher` cover every endpoint?

**Lesson goal:** migrate legacy configuration to `SecurityFilterChain`, `UserDetailsService`, `PasswordEncoder`, `AuthenticationProvider`/`AuthenticationManager`, and (only when genuinely needed) `WebSecurityCustomizer` beans; understand the API differences; and write **HTTP and method security tests** proving that permissions are not loosened and login is not broken.

> Scope: Spring Security **Servlet** with `HttpSecurity` and `SecurityFilterChain`, not WebFlux `ServerHttpSecurity` and `SecurityWebFilterChain`.

## 2. Migration map: inheritance style to composition style

| Legacy config | New config | Meaning |
| --- | --- | --- |
| `extends WebSecurityConfigurerAdapter` | One or more `@Bean SecurityFilterChain` | Each bean describes one security filter chain and policy. |
| Override `configure(HttpSecurity http)` | `SecurityFilterChain filterChain(HttpSecurity http)` + `return http.build()` | Defines HTTP security via composition. |
| `http.authorizeRequests()` | `http.authorizeHttpRequests(auth -> ...)` | Modern authorization DSL backed by `AuthorizationManager`. |
| Legacy `antMatchers(...)`, `mvcMatchers(...)` | `requestMatchers(...)` and appropriate matchers | Specifies path/method; consider actual MVC/servlet mappings. |
| `antMatchers(...).hasRole("ADMIN")` | `requestMatchers(...).hasRole("ADMIN")` | Role contract still requires checking the `ROLE_` prefix. |
| Override `configure(AuthenticationManagerBuilder)` | `UserDetailsService`, `PasswordEncoder`, `AuthenticationProvider`, or `AuthenticationManager` beans | Authentication is a separate responsibility, not an adapter override. |
| Override `configure(WebSecurity web)` | `WebSecurityCustomizer` bean only if bypass is truly required | `web.ignoring()` skips the filter chain; `permitAll()` is usually preferred. |
| `@EnableGlobalMethodSecurity(prePostEnabled = true)` | `@EnableMethodSecurity` | Enables `@PreAuthorize`/`@PostAuthorize` using the new API. |
| `WebSecurityConfigurerAdapter#authenticationManagerBean()` | Only when needed: `AuthenticationConfiguration#getAuthenticationManager()` or a dedicated manager bean | Do not expose a global manager out of habit. |
| `javax.servlet.*` in Boot 2 code | `jakarta.servlet.*` in Boot 3 | Migrate Servlet API namespace; avoid incompatible legacy adapters. |
| Chained `http.and().formLogin().and()` style | Lambda DSL `http.formLogin(Customizer.withDefaults())` | Clearer grouping, easier to read and upgrade. |
| `@Order` on multiple adapters | `@Order` on `SecurityFilterChain` beans | Prioritize specialized chains before general catch-all chains. |

**This is not a mechanical 1:1 substitution.** Legacy configs may have relied on default behaviors, custom filters, or providers hidden behind the adapter. Review your application's threat model, write out an endpoint/role/method matrix, and verify it with tests after upgrading.

## 3. Legacy configuration example — for recognition only, does not run on Spring Security 6

Below is the **legacy Spring Security 5 style**. Do not copy this into a Boot 3 application; APIs such as `WebSecurityConfigurerAdapter` and `antMatchers` are no longer valid configuration mechanisms in Spring Security 6.

~~~java
// LEGACY: illustrates old syntax, NOT part of the runnable project below.
@Configuration
@EnableWebSecurity
public class LegacySecurityConfig extends WebSecurityConfigurerAdapter {

    @Override
    protected void configure(HttpSecurity http) throws Exception {
        http
            .authorizeRequests()
                .antMatchers("/", "/public").permitAll()
                .antMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            .and()
            .formLogin()
            .and()
            .httpBasic();
    }

    @Override
    protected void configure(AuthenticationManagerBuilder auth)
            throws Exception {
        auth.inMemoryAuthentication()
            .withUser("alice")
            .password("{noop}training-only")
            .roles("USER");
    }

    @Override
    public void configure(WebSecurity web) {
        web.ignoring().antMatchers("/assets/**");
    }
}
~~~

Responsibilities are intertwined: HTTP authorization + authentication source + filter bypass. The modern approach separates them into beans that can be injected and tested independently.

**Never carry `{noop}` passwords into production.** That is a non-hashing encoder for historical demos; real systems need proper hashing, tested legacy hash migration, and secret management. Use `PasswordEncoderFactories.createDelegatingPasswordEncoder()` in new examples so encoding is not bypassed.

### 3.1. Why was the adapter replaced?

Bean composition enables:

- Creating **multiple clearly scoped chains**, each with its own `securityMatcher`, `@Order`, and policy.
- Separating user stores, hashing mechanisms, providers, and security filter configuration.
- Simplifying testing by injecting `SecurityFilterChain`, `AuthenticationManager`/providers, or services instead of relying on inheritance hooks.
- Better alignment with `authorizeHttpRequests`, method security, and the lambda DSL.
- Reducing configuration split between overrides and auto-configuration with hard-to-trace precedence.

However, creating beans does not automatically make an app secure. If you forget a fallback chain, make `permitAll` overly broad, or disable CSRF out of habit, vulnerabilities remain.

## 4. SecurityFilterChain bean replacing configure(HttpSecurity)

A minimal example with **Java 17 / Spring Security 6**:

~~~java
// Snippet inside @Configuration; requires an appropriate UserDetailsService/provider.
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/", "/health").permitAll()
            .requestMatchers("/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated()
        )
        .formLogin(Customizer.withDefaults());

    return http.build();
}
~~~

This is a **snippet explaining the API**, not a complete project. Spring passes `HttpSecurity` into the `@Bean` method; after configuring it, call `http.build()` to produce the `SecurityFilterChain`. Never instantiate `new HttpSecurity(...)` manually.

### 4.1. authorizeHttpRequests and rule ordering

Within a single chain, matchers are evaluated in **declaration order**, and the first matching rule decides the policy. You should:

1. Place specific public endpoints first.
2. Place paths requiring specific roles/scopes next.
3. Place a catch-all `anyRequest().authenticated()` or `anyRequest().denyAll()` at the end per your approved policy.

Example:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/reports").hasAuthority("REPORT_READ")
    .requestMatchers(HttpMethod.POST, "/reports").hasAuthority("REPORT_WRITE")
    .anyRequest().denyAll()
)
~~~

If only GET is allowed and POST has no rule yet, `denyAll` prevents POST from **being granted access accidentally**. Never change a legacy `anyRequest().authenticated()` to `permitAll()` just to reduce test failures: that is a major security downgrade.

### 4.2. securityMatcher and requestMatchers are not the same

With multiple chains:

~~~java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public").permitAll()
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults());
    return http.build();
}
~~~

- `securityMatcher("/api/**")` defines the **scope of the chain**.
- `requestMatchers("/api/public")` defines **rules inside the selected chain**.
- `anyRequest()` also applies only to requests **that entered that chain**.

If there is no other chain, `/web/private` does not match `/api/**` and may pass through the application **unprotected by Spring Security filters**. With multiple chains, place specialized chains first and include a **catch-all chain** last.

### 4.3. Do not disable CSRF by default when migrating

Many older tutorials write:

~~~java
// Anti-pattern if used for forms/sessions without evaluation.
http.csrf(csrf -> csrf.disable());
~~~

If the application uses a browser + session cookies, CSRF protection is necessary for state-changing requests. When migrating to new beans, **keep existing CSRF protection intact or adjust it based on the real threat model**. An API that only accepts bearer tokens in the `Authorization` header and does not rely on browser-auto-sent credentials may warrant a different assessment; **HTTP Basic** can actually be sent automatically by browsers, so do not disable CSRF merely because an endpoint path includes "API".

## 5. Authentication: separating UserDetailsService and PasswordEncoder

In the new configuration style, the clearest setup for username/password apps is registering beans:

~~~java
@Bean
PasswordEncoder passwordEncoder() {
    return PasswordEncoderFactories.createDelegatingPasswordEncoder();
}

@Bean
UserDetailsService userDetailsService(PasswordEncoder encoder) {
    return new InMemoryUserDetailsManager(
        User.withUsername("alice")
            .password(encoder.encode("training-only"))
            .authorities("ROLE_USER")
            .build()
    );
}
~~~

This is a **snippet**, not a production user store. Given an appropriate `UserDetailsService`/provider, Spring Security wires authentication using the registered beans. If the application uses multiple providers or a custom manager, verify how `AuthenticationManager` is built and ordered rather than assuming one `UserDetailsService` bean overrides other security logic.

### 5.1. PasswordEncoder and hash migration

- `PasswordEncoder#encode` produces the stored representation.
- `matches(raw, encoded)` verifies passwords; never compare raw strings manually.
- `DelegatingPasswordEncoder` supports an identifier prefix in the encoded value, such as `{bcrypt}...`.
- If a legacy database stores hashes without a prefix or with an older algorithm, the upgrade needs a tested **compatibility/rehash plan**, not prepending `{noop}` to all passwords.
- Never log raw passwords, encoded hashes from real users, or credentials in requests.

**Common bug:** after migration every login returns 401 or redirects to `/login?error` because the `PasswordEncoder` bean does not match the legacy hash format. Fix the encoder and encoded data instead of opening public endpoints.

### 5.2. Authorities and the role prefix

| Configuration | Expected authority under default convention |
| --- | --- |
| `hasRole("ADMIN")` | `ROLE_ADMIN` |
| `hasAuthority("ROLE_ADMIN")` | `ROLE_ADMIN` |
| `hasAuthority("REPORT_READ")` | `REPORT_READ` |
| `hasAuthority("SCOPE_orders.read")` | `SCOPE_orders.read` |

If a user is created with `.authorities("ADMIN")`, `hasRole("ADMIN")` can return 403 due to the missing `ROLE_` prefix. Do not switch the rule to `permitAll`; align the authority mapper or use `hasAuthority` to match the contract.

**Note:** on `User.UserBuilder`, do not assume calling `.roles(...)` after `.authorities(...)` accumulates both lists without checking the API. The complete example below declares **all required authorities** in a single `.authorities(...)` call.

## 6. When do you need an AuthenticationProvider or AuthenticationManager bean?

Not every project removing `WebSecurityConfigurerAdapter` needs to declare an `AuthenticationManager` bean manually.

### 6.1. When UserDetailsService + PasswordEncoder are enough

If using form login/HTTP Basic with the `DaoAuthenticationProvider` configured by Spring Security, registering `UserDetailsService` and `PasswordEncoder` beans is usually sufficient. Filters obtain `AuthenticationManager` through Security infrastructure instead of controllers checking passwords manually.

**Do not** write a REST controller that accepts a password and compares it against a DB string just to replace `configure(AuthenticationManagerBuilder)`.

### 6.2. Custom providers / LDAP / external systems

When the system has custom authentication (such as verifying against an external backend via an `AuthenticationProvider`), declare the provider and wire it explicitly into Spring Security:

~~~java
// ILLUSTRATIVE snippet only for Spring Security 6.x with matching API;
// do not add to the demo project below.
@Bean
AuthenticationProvider daoAuthenticationProvider(
        UserDetailsService users, PasswordEncoder encoder) {
    DaoAuthenticationProvider provider = new DaoAuthenticationProvider();
    provider.setUserDetailsService(users);
    provider.setPasswordEncoder(encoder);
    return provider;
}
~~~

Constructors and setters on `DaoAuthenticationProvider` can change or be deprecated in newer releases; check the JavaDoc of **the exact version you deploy** before copying. Custom providers must return a properly authenticated `Authentication` with trustworthy authorities, throw `AuthenticationException` on bad credentials, and never fail open.

Do not register redundant providers just to “make sure login works.” Provider ordering/selection and `supports` determine behavior; test success, failure, disabled/locked users, wrong passwords, and backend unavailability.

### 6.3. Expose AuthenticationManager only when injection is required

If an application component **genuinely** needs to inject the global manager, you can use:

~~~java
// Optional snippet: do not add to the demo below unless needed.
@Bean
AuthenticationManager authenticationManager(
        AuthenticationConfiguration configuration) throws Exception {
    return configuration.getAuthenticationManager();
}
~~~

Import `org.springframework.security.config.annotation.authentication.configuration.AuthenticationConfiguration` and `org.springframework.security.authentication.AuthenticationManager`.

**Do not treat this pattern as guaranteeing every project has the right manager:** valid providers/config must exist, and you must consider multiple chains, custom providers, and per-chain managers. Most standard form-login apps never need to inject `AuthenticationManager` into a controller.

### 6.4. When to use http.authenticationProvider

If a provider is meant for a single security chain, attach it on that `HttpSecurity` configuration:

~~~java
// Snippet inside configuring a single HttpSecurity instance.
http.authenticationProvider(customProvider);
~~~

This is not equivalent to registering a global manager for all chains. Verify where the provider is active and test each authentication mechanism.

## 7. WebSecurityCustomizer: do not confuse ignoring with permitAll

Legacy configs often contain:

~~~java
@Override
public void configure(WebSecurity web) {
    web.ignoring().antMatchers("/css/**", "/js/**");
}
~~~

To express bypasses in bean-based configuration, the corresponding API looks like:

~~~java
// Illustrative snippet; NOT recommended by default.
@Bean
WebSecurityCustomizer webSecurityCustomizer() {
    return web -> web.ignoring().requestMatchers("/legacy-static/**");
}
~~~

However, **`web.ignoring()` prevents requests from passing through the Spring Security filter chain**, losing security headers, security context handling, audit/security filters, and protections enforced by the chain.

For public application assets, usually prefer:

~~~java
// Inside authorizeHttpRequests of the chain covering the path:
.requestMatchers("/css/**", "/js/**", "/images/**").permitAll()
~~~

That way, requests still traverse Spring Security filters without requiring authentication per the rule.

**Key differences:**

| Aspect | `permitAll()` | `web.ignoring()` |
| --- | --- | --- |
| Does the request pass through Spring Security's `FilterChainProxy`? | Yes | No, for ignored matchers |
| Does authorization require login? | No, under the permit rule | Skips Spring Security |
| Do security headers and other filters get a chance to run? | Yes, depending on the chain | No Spring Security filters run for ignored requests |
| Safe for dynamic/sensitive endpoints? | Only if genuinely public | Avoid; can create severe bypasses |
| Good default for static assets? | Usually recommended | Only for evaluated exceptions |

**Never use** `web.ignoring().requestMatchers("/api/**")` as a workaround for 401/403 on APIs. It can strip Spring Security from the entire API.

## 8. Upgrading method security

In legacy code:

~~~java
// Legacy annotation.
@EnableGlobalMethodSecurity(prePostEnabled = true)
~~~

In Spring Security 6, typically use:

~~~java
// On @Configuration or application configuration.
@EnableMethodSecurity
~~~

`@EnableMethodSecurity` enables annotations such as `@PreAuthorize` and `@PostAuthorize` with sensible defaults. However, **methods must be called through the Spring-managed bean/proxy**; if a test uses `new SomeService()`, `@PreAuthorize` is not intercepted by Spring. Self-invocation within the same bean also bypasses proxy-based method security.

Example:

~~~java
@Service
public class AdminReportService {
    @PreAuthorize("hasRole('ADMIN')")
    public String internalReport() {
        return "admin-report";
    }
}
~~~

Above is a **separate class example needing its imports**; the complete project in Section 9 turns this into a full file.

**Do not treat URL authorization as a substitute for method/resource authorization**. If a service fetches objects by tenant, enforce ownership/tenant checks too; `hasRole` only checks authorities, not record-level access.

## 9. Runnable project: Spring Boot 3.3.5 + Java 17 + bean-based config

To compare a system with both API and form-login routes, we implement **two SecurityFilterChain beans**:

- `@Order(1)` for `/api/**`: HTTP Basic, public API or requiring `REPORT_READ`/`REPORT_WRITE` authorities.
- `@Order(2)` for the rest: form login, user profile, admin page, POST web notes requiring `ROLE_USER`, fallback `denyAll`.
- Spring Security's **default CSRF remains enabled** for POST. This intentionally keeps browser/cookie safety intact and demonstrates that migration does not drop CSRF for convenience.

In-memory users and tiny responses are for demo purposes only. Never hardcode accounts/passwords in production; use an appropriate user repository/IdP and secret management.

### 9.1. Structure

~~~text
bean-security-migration/
├── pom.xml
└── src/
    ├── main/
    │   └── java/demo/
    │       ├── MigrationApplication.java
    │       ├── SecurityConfig.java
    │       ├── MigrationController.java
    │       └── AdminReportService.java
    └── test/
        └── java/demo/
            ├── MigrationHttpSecurityTests.java
            └── MigrationMethodSecurityTests.java
~~~

### 9.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>bean-security-migration</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
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

Use `spring-boot-starter-security` with the Boot BOM to manage Spring Security module versions. `spring-security-test` is required for MockMvc `csrf()`, `httpBasic()`, `user()`, and `@WithMockUser`.

### 9.3. src/main/java/demo/MigrationApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MigrationApplication {
    public static void main(String[] args) {
        SpringApplication.run(MigrationApplication.class, args);
    }
}
~~~

### 9.4. src/main/java/demo/SecurityConfig.java

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        // DEMO ONLY: never ship hardcoded passwords to production.
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("demo-only"))
                .authorities("ROLE_USER", "REPORT_READ")
                .build(),
            User.withUsername("writer")
                .password(encoder.encode("demo-only"))
                .authorities("REPORT_WRITE")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("demo-only"))
                .authorities(
                    "ROLE_USER", "ROLE_ADMIN", "REPORT_READ")
                .build(),
            User.withUsername("limited")
                .password(encoder.encode("demo-only"))
                .authorities("ROLE_USER")
                .build()
        );
    }

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/reports")
                    .hasAuthority("REPORT_READ")
                .requestMatchers(HttpMethod.POST, "/api/reports")
                    .hasAuthority("REPORT_WRITE")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        // Example intentionally keeps CSRF for HTTP Basic POST.
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webAndFallback(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/", "/health", "/error")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/web/profile")
                    .authenticated()
                .requestMatchers(HttpMethod.GET, "/web/admin")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.POST, "/web/notes")
                    .hasRole("USER")
                .anyRequest().denyAll()
            )
            .formLogin(form -> form
                .defaultSuccessUrl("/web/profile", true)
                .permitAll()
            )
            .logout(logout -> logout.permitAll());

        // This chain has no securityMatcher => catch-all.
        return http.build();
    }
}
~~~

**Migration explanation for this file:**

- No longer extends `WebSecurityConfigurerAdapter` or overrides `configure`.
- API and web security are built from **two `SecurityFilterChain` beans**, distinguished by `@Order` and `securityMatcher`.
- `apiChain` is evaluated first, so `/api/reports` does not fall into the web form-login chain. Anonymous API calls receive an **HTTP Basic challenge** rather than a redirect to `/login`.
- The web chain has no matcher restriction, acting as a catch-all for remaining URLs. `anyRequest().denyAll()` ensures undeclared endpoints are not accidentally public.
- `UserDetailsService` provides four demo users; `PasswordEncoder` handles password hashing.
- `@EnableMethodSecurity` replaces the legacy annotation and activates `@PreAuthorize` on services.
- `hasRole("ADMIN")` requires `ROLE_ADMIN`; user `admin` has that authority assigned.
- For form login, `.permitAll()` inside `formLogin` opens the framework-generated login endpoints, not `anyRequest().permitAll()`.
- With CSRF enabled, POST `/web/notes` and `/api/reports` require a CSRF token. Real API policies may differ when using stateless bearer tokens; evaluate each chain individually.

### 9.5. src/main/java/demo/AdminReportService.java

~~~java
package demo;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class AdminReportService {

    @PreAuthorize("hasRole('ADMIN')")
    public String adminLabel() {
        return "admin-only";
    }
}
~~~

Method security is an additional layer of control. `@EnableMethodSecurity` ensures this method is enforced when invoked through the Spring-managed bean/proxy.

### 9.6. src/main/java/demo/MigrationController.java

~~~java
package demo;

import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class MigrationController {

    private final AdminReportService adminService;

    public MigrationController(AdminReportService adminService) {
        this.adminService = adminService;
    }

    @GetMapping("/")
    Map<String, String> home() {
        return Map.of("message", "public-home");
    }

    @GetMapping("/health")
    Map<String, String> health() {
        return Map.of("status", "up");
    }

    @GetMapping("/api/public")
    Map<String, String> publicApi() {
        return Map.of("message", "public-api");
    }

    @GetMapping("/api/reports")
    Map<String, String> reports() {
        return Map.of("report", "read");
    }

    @PostMapping("/api/reports")
    Map<String, String> createReport() {
        return Map.of("report", "created");
    }

    @GetMapping("/web/profile")
    Map<String, String> profile(Authentication authentication) {
        return Map.of("user", authentication.getName());
    }

    @GetMapping("/web/admin")
    Map<String, String> admin() {
        return Map.of("message", adminService.adminLabel());
    }

    @PostMapping("/web/notes")
    Map<String, String> notes() {
        return Map.of("message", "saved");
    }

    // Controller exists, but is not in the catch-all allowlist.
    @GetMapping("/shadow")
    Map<String, String> shadow() {
        return Map.of("secret", "never-public");
    }
}
~~~

The demo controller persists no data. In production, `POST` endpoints must include DTOs/validation, mass-assignment protection, and object/tenant-level authorization. `@PreAuthorize` on `adminLabel()` does not replace business ownership checks.

### 9.7. Running the application

Inside the directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Test public endpoints:

~~~bash
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/health
~~~

Expected: HTTP 200 with the corresponding JSON.

Test the authenticated API:

~~~bash
curl -i http://localhost:8080/api/reports

curl -i -u alice:demo-only \
  http://localhost:8080/api/reports

curl -i -u writer:demo-only \
  http://localhost:8080/api/reports
~~~

Expected: **401**, **200**, **403** respectively. Basic credentials are for localhost practice only; production must use HTTPS and avoid passing real passwords in commands recorded in shell history.

Test the form-login web route:

~~~bash
curl -i http://localhost:8080/web/profile
~~~

Expected: 302 response with `Location` pointing to `/login`. Do not pass `curl -L` when inspecting the initial redirect. In a browser, visit `http://localhost:8080/login`, sign in with demo credentials, and access the profile.

### 9.8. Why is WebSecurityCustomizer omitted from the runnable files?

The goal of the demo is to keep Spring Security filters active even on public endpoints. With `permitAll()`, requests still traverse the chain. An unnecessary `WebSecurityCustomizer` belongs as an **optional snippet** in Section 7. Adding one just to showcase every bean encourages overusing `ignoring`.

Similarly, an `AuthenticationManager` bean is not added just for completeness. For this demo, `UserDetailsService` and `PasswordEncoder` with Basic/form login already wire the authentication flow properly. Any policy changing authentication providers must be tested separately.

## 10. Regression tests: proving behavior is preserved after removing the adapter

### 10.1. src/test/java/demo/MigrationHttpSecurityTests.java

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MigrationHttpSecurityTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicApiIsAccessibleWithoutLogin() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("public-api"));
    }

    @Test
    void apiAnonymousGetsBasic401NotWebRedirect() throws Exception {
        mvc.perform(get("/api/reports"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.WWW_AUTHENTICATE, containsString("Basic")));
    }

    @Test
    void incorrectBasicPasswordIsRejected() throws Exception {
        mvc.perform(get("/api/reports")
                .with(httpBasic("alice", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void validBasicUserCanRead() throws Exception {
        mvc.perform(get("/api/reports")
                .with(httpBasic("alice", "demo-only")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.report").value("read"));
    }

    @Test
    void authenticatedWithoutReadAuthorityIsForbidden()
            throws Exception {
        mvc.perform(get("/api/reports")
                .with(user("writer").authorities(
                    new SimpleGrantedAuthority("REPORT_WRITE")
                )))
            .andExpect(status().isForbidden());
    }

    @Test
    void postWithoutCsrfIsForbiddenEvenForWriter()
            throws Exception {
        mvc.perform(post("/api/reports")
                .with(user("writer").authorities(
                    new SimpleGrantedAuthority("REPORT_WRITE")
                )))
            .andExpect(status().isForbidden());
    }

    @Test
    void postWithCsrfButNoWriteAuthorityIsForbidden()
            throws Exception {
        mvc.perform(post("/api/reports")
                .with(user("alice").authorities(
                    new SimpleGrantedAuthority("REPORT_READ")
                ))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    void postWithCsrfAndWriteAuthoritySucceeds()
            throws Exception {
        mvc.perform(post("/api/reports")
                .with(user("writer").authorities(
                    new SimpleGrantedAuthority("REPORT_WRITE")
                ))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.report").value("created"));
    }

    @Test
    void webAnonymousGets302LoginRedirect() throws Exception {
        mvc.perform(get("/web/profile"))
            .andExpect(status().isFound())
            .andExpect(header().string(
                HttpHeaders.LOCATION, containsString("/login")));
    }

    @Test
    void webUserCanReadOwnPrincipal() throws Exception {
        mvc.perform(get("/web/profile")
                .with(user("alice").roles("USER")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.user").value("alice"));
    }

    @Test
    void normalUserCannotVisitWebAdmin() throws Exception {
        mvc.perform(get("/web/admin")
                .with(user("alice").roles("USER")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminRoleAllowsAdminPage() throws Exception {
        mvc.perform(get("/web/admin")
                .with(user("admin").roles("ADMIN")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("admin-only"));
    }

    @Test
    void webMutationNeedsCsrf() throws Exception {
        mvc.perform(post("/web/notes")
                .with(user("alice").roles("USER")))
            .andExpect(status().isForbidden());
    }

    @Test
    void webMutationWithRoleAndCsrfSucceeds() throws Exception {
        mvc.perform(post("/web/notes")
                .with(user("alice").roles("USER"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("saved"));
    }

    @Test
    void loginWorksWithCsrfAndRedirectsToConfiguredTarget()
            throws Exception {
        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", "demo-only"))
            .andExpect(status().isFound())
            .andExpect(redirectedUrl("/web/profile"));
    }

    @Test
    void unlistedMappedPathIsBlockedByCatchAll() throws Exception {
        mvc.perform(get("/shadow")
                .with(user("alice").roles("USER")))
            .andExpect(status().isForbidden());
    }

    @Test
    void unknownApiPathIsBlocked() throws Exception {
        mvc.perform(get("/api/new-private-path")
                .with(user("alice").authorities(
                    new SimpleGrantedAuthority("REPORT_READ")
                )))
            .andExpect(status().isForbidden());
    }
}
~~~

**What these tests prove:**

- Real HTTP filters run in the MockMvc context; `@SpringBootTest` + `@AutoConfigureMockMvc` verifies chain integration.
- Unauthenticated API requests return a 401 Basic challenge rather than being captured by the web form-login chain for a 302 redirect.
- Bad passwords are rejected; valid credentials + authority can read the API.
- `@WithMockUser`/`.with(user())` **does not** exercise password providers, so dedicated Basic tests remain necessary.
- POST without a CSRF token returns 403; when testing role rules, pass `csrf()` to avoid getting a 403 with “the right status code for the wrong reason.”
- Anonymous web requests redirect 302; non-admin users get 403, admins get 200.
- The `/shadow` controller exists yet is blocked by the catch-all `denyAll`; this protects against newly added unconfigured routes.
- The form-login test verifies the **exact redirect URL**, not just status 302.

In total, this file contains **17 tests**. No assertions depend on test execution order, and no state is written to a database.

### 10.2. src/test/java/demo/MigrationMethodSecurityTests.java

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest
class MigrationMethodSecurityTests {

    @Autowired
    AdminReportService adminService;

    @Test
    @WithMockUser(username = "admin", roles = "ADMIN")
    void adminIsAllowedByPreAuthorize() {
        assertThat(adminService.adminLabel())
            .isEqualTo("admin-only");
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void userWithoutAdminAuthorityIsDenied() {
        assertThatThrownBy(adminService::adminLabel)
            .isInstanceOf(AccessDeniedException.class);
    }
}
~~~

**Both positive and negative tests are needed.** If you forget `@EnableMethodSecurity`, positive tests may still return the expected string, while negative tests expose that the annotation is not enforced.

**Do not instantiate `new AdminReportService()` to test `@PreAuthorize`**, as that bypasses the Spring-managed proxy. Also do not mock the protected service itself and treat the result as a method-security integration test.

### 10.3. Running the tests

~~~bash
mvn test
~~~

Expected run: **19 tests** (17 HTTP tests + 2 method security tests). The tests aim to verify 0 failures/0 errors for the project as shown. This is an **expected outcome**; this guide does not claim Maven was executed or live logs were captured in the current environment.

Run only the HTTP suite:

~~~bash
mvn -Dtest=MigrationHttpSecurityTests test
~~~

In real security migrations, run tests both before and after configuration changes to catch regressions in status codes, redirects, headers, cookies, roles, and CSRF. A `200` response alone does not prove security if a request accidentally bypassed the chain; always include negative cases.

## 11. Boot 2 → Boot 3 and namespace changes to check

Removing `WebSecurityConfigurerAdapter` typically accompanies a runtime upgrade:

### 11.1. Java and the Servlet API

- Spring Boot 3 requires **Java 17 or newer**.
- Spring Framework 6 / Security 6 run on Jakarta EE namespaces, such as `jakarta.servlet.Filter` and `jakarta.servlet.http.HttpServletRequest`.
- Older libraries/filters compiled against `javax.servlet.*` may be incompatible with Jakarta Servlet; select adapter versions supporting Boot 3.
- **Do not** blindly find-and-replace every `javax.*` to `jakarta.*`: `javax.crypto`, `javax.net.ssl`, and many Java SE packages remain under `javax`.

### 11.2. DSL matchers

`antMatchers` was widely used in Security 5; modern versions use `requestMatchers`. How Spring builds a matcher from a String can depend on the MVC/Servlet environment. With **multiple DispatcherServlets or varying servlet paths**, check matcher semantics, version-appropriate `HandlerMappingIntrospector`/`MvcRequestMatcher`, and the actual context path.

Test tricky paths:

- `/api` vs `/api/`.
- `/api/private` vs `/api/private/`.
- Context path `/app` and non-default servlet mappings.
- Encoded slashes, dot segments, and semicolons/matrix variables if supported by the stack.
- URLs outside specialized chains falling into the catch-all.
- Whether additional methods (GET/POST/PUT/PATCH/DELETE) have rules.
- Whether `ERROR`/`FORWARD` dispatches are unintentionally blocked.

**Do not try to normalize paths manually via string slicing before delegating**; use runtime-appropriate matchers and test real requests.

### 11.3. Settings that must be migrated explicitly so nothing is lost without overrides

If the legacy system had custom settings inside `configure(HttpSecurity)`, review each area:

| Feature | Post-migration check |
| --- | --- |
| Form login | Login page, processing URL, failure/success handlers, saved request, `permitAll`. |
| Logout | POST/CSRF, session invalidation, clearing authentication, success URL. |
| CSRF | Repository, matching paths, token lifecycle; do not disable globally if cookie sessions exist. |
| CORS | Origin/method/header/credentials, preflight OPTIONS, proper `CorsConfigurationSource`. |
| Session | Session creation policy, fixation protection, concurrent sessions, `SecurityContextRepository`. |
| Exception handling | `AuthenticationEntryPoint`, `AccessDeniedHandler`, API 401/403 vs web redirect. |
| Headers | HSTS over HTTPS, CSP/Frame options/X-Content-Type-Options per policy. |
| Remember-me | Key/cookie/expiry/password changes, persistent token repository if used. |
| Custom filters | `addFilterBefore`/`addFilterAfter`, dependencies, position relative to authentication/authorization filters. |
| Authentication | Provider order, `UserDetailsService`, password hash migration, disabled users. |
| OAuth2/OIDC/SAML2 | Redirect URIs, callback paths, claims/scopes/role mapping, release-matched adapters. |
| Method security | `@EnableMethodSecurity`, `@PreAuthorize` proxies, permission evaluators. |
| Multi-chain | `@Order`, `securityMatcher`, default/catch-all coverage. |

Defining a `SecurityFilterChain` bean can also cause **Spring Boot's auto-configured default web security chain** to stop applying by default. Therefore, declare complete policies for all required paths instead of expecting the starter to supply a fallback chain.

## 12. From error diagnosis to proper fixes

### 12.1. After upgrading, every endpoint returns 403

Possible causes:

- `authorizeHttpRequests` has an overly broad `denyAll` or path rules are out of order.
- Mixing up `hasRole` and `hasAuthority` caused a prefix mismatch.
- Method security `@PreAuthorize` is now enforced and blocks a previously unprotected service.
- POST lacks a CSRF token because JS forms do not send it yet.
- Requests are matched earlier than expected by a specialized chain.

**How to fix:** test authorized GET, unauthorized GET, POST with/without CSRF, inspect `Authentication.getAuthorities()` in tests, and verify which chain matches first. Never add `anyRequest().permitAll()` as a “quick fix.”

### 12.2. API previously returned 401, now returns 302 /login

Usually the API fell into the form-login chain or another `AuthenticationEntryPoint`. Check `securityMatcher("/api/**")` and `@Order`. Verify `/api/v2/...` matches the path and the login URL belongs to the right chain.

**Fix:** restore the proper authentication/entry point config for the API, and add regression tests asserting `WWW-Authenticate` and `Location`.

### 12.3. Form login with valid password redirects to /login?error

Possible causes: `UserDetailsService` is not wired, `PasswordEncoder` mismatch, wrong credential provider, disabled user, mismatched login processing URL, or multiple `AuthenticationManager` instances. Inspect provider selection and password hashes rather than disabling the encoder or granting `permitAll`.

### 12.4. New controller is publicly reachable despite not being declared

Possible causes: only an `/api/**` chain exists with no catch-all, or `web.ignoring()` ignores an overly broad path. This is a **vulnerability**—fix `SecurityFilterChain` coverage, not just the HTTP status.

### 12.5. `@PreAuthorize` has no effect

Check:

- Is `@EnableMethodSecurity` enabled?
- Is the service a Spring-managed bean called **through its proxy**?
- Is self-invocation bypassing the proxy?
- Is the test mocking the bean instead of testing the real service?
- Are legacy global method security configs or conflicting adapters present?

Write denied tests for unauthorized users; testing only authorized calls is insufficient.

### 12.6. Test returns 403 for the wrong reason

For POST requests, `CsrfFilter` can return 403 before authorization runs. To test roles, supply a valid token with `csrf()` and vary authorities. To test CSRF, supply a valid role and omit the token.

For GET requests, when unauthenticated, the entry point may return **401** (Basic API) or **302** (web form login). Never assume all anonymous GETs produce the same code.

### 12.7. Login or OAuth2 callback enters a redirect loop

A narrow chain may fail to match `/login`, `/logout`, or `/login/oauth2/code/{registrationId}`. Inspect the default page, processing path, callback, session cookie, and reverse proxy host/scheme. During an upgrade, preserve legacy URLs or deliberately update IdP/redirect registrations.

## 13. Step-by-step safe migration workflow

**Step 1 — Capture the current contract in tests.** List public endpoints, protected endpoints, HTTP methods, roles/scopes, authentication entry points, CSRF, login/logout, headers, and sessions. Write integration tests running against the old version before modifying config.

**Step 2 — Upgrade runtime and dependencies in a controlled manner.** Verify Java 17, Boot 3/Security 6, Jakarta Servlet APIs, and custom libraries. Avoid mixing Spring Security 5 and 6 on the same classpath or bringing legacy `javax.servlet` adapters into a Jakarta runtime.

**Step 3 — Split configure(HttpSecurity).** Move HTTP rules into one or more `SecurityFilterChain` beans. Update `authorizeRequests`/`antMatchers` to the new DSL. Add a final `anyRequest` rule and an explicit default chain.

**Step 4 — Extract authentication beans.** Migrate `UserDetailsService`, `PasswordEncoder`, and providers; declare an `AuthenticationManager` bean only when a component needs to inject it. Verify password hashes, role mappings, and disabled/locked user handling.

**Step 5 — Audit web ignoring.** Prefer `permitAll()` for static/public resources. If an exception requires `WebSecurityCustomizer`, document the rationale and verify dynamic endpoints are not bypassed.

**Step 6 — Migrate method security.** Use `@EnableMethodSecurity`, test proxy invocation and negative permissions, and audit any prior permission evaluators or custom expressions.

**Step 7 — Verify login/CSRF/session.** Form login/logout, session repository, request cache, CSRF fields, CORS, and exception handling can shift behavior during code migration. Never accept “green tests” achieved by removing filters.

**Step 8 — Run HTTP integration tests.** Cover anonymous, invalid credentials, authorized, forbidden, missing/valid CSRF, 302 redirects, 401 vs 403 status codes, undeclared HTTP methods, paths outside the allowlist, and overlapping multi-chain routes.

**Step 9 — Test in a production-like environment.** Proxies/context paths/HTTPS, external IdPs, JDBC/LDAP user stores, and security headers can behave differently than localhost. Never emit real secrets in logs.

**Step 10 — Review under least privilege.** Prove no permissions were widened for any request or role. Only at the end delete legacy adapter classes, obsolete dependencies, and duplicate configs. Never leave both old and new configs competing inside the same `ApplicationContext`.

## 14. Anti-patterns and fixes

| Mistake | Risk | How to fix |
| --- | --- | --- |
| Replacing `WebSecurityConfigurerAdapter` with a `permitAll` chain to make the build pass. | The whole application may lose authorization. | Migrate each legacy rule and test denied cases. |
| Omitting `http.build()` or returning the wrong bean. | Security chain is never created. | Call `return http.build()` after the lambda DSL. |
| Creating an `/api/**` chain without a fallback chain. | URLs outside `/api/**` can bypass Spring Security filters. | Add a final catch-all chain. |
| Ordering `/api/**` before `/api/admin/**`. | Broad chain captures specialized requests. | `@Order` narrower chains first; test overlapping paths. |
| Using `web.ignoring()` instead of `permitAll()` everywhere. | Requests lose security headers/filter handling. | Prefer `permitAll()` inside the chain. |
| Disabling CSRF globally just because POST tests return 403. | Browser/session CSRF protection may be lost. | Configure forms/tokens/repositories properly, or apply a real stateless API threat model. |
| Copying `{noop}` from old demos into production. | Passwords stored unhashed. | Use strong encoders and safe hash migration. |
| Passing `roles("ROLE_ADMIN")` instead of the role name. | Prefix mismatch, 403, or user-build error. | Use `roles("ADMIN")` or `authorities("ROLE_ADMIN")`. |
| Registering two similar providers “just to be sure” login works. | Authentication ordering becomes hard to control. | Choose providers intentionally and test thoroughly. |
| Forgetting `@EnableMethodSecurity`. | `@PreAuthorize` is never enforced. | Enable method security and add negative tests. |
| Testing `new Service()` instead of the Spring bean. | Bypasses the method-security proxy. | `@Autowired` the Spring-managed service. |
| Setting `addFilters = false` on MockMvc. | False-green HTTP security tests. | Keep Spring Security filters enabled in tests. |
| Testing POST role rules without `csrf()`. | Right 403 status code, but due to missing token. | Supply a valid token when isolating authorization. |
| Changing `javax.servlet` to `jakarta.servlet` without checking libraries. | Classloading/adapter API mismatch. | Update dependencies and integration tests. |
| Changing matchers without testing context/servlet paths. | Routes bypassed or wrongly blocked. | Test real URLs/methods, checking dispatchers and proxies. |
| Granting admin rights to every logged-in resource. | Missing object/tenant checks. | Combine URL, method, and resource authorization. |

## 15. Final acceptance checklist

- [ ] No references/extensions of `WebSecurityConfigurerAdapter` or removed DSL methods remain in Boot 3/Security 6 code.
- [ ] At least one `SecurityFilterChain` bean exists with explicit policy for all critical paths.
- [ ] With multiple chains, `@Order`/`securityMatcher` are clear and a catch-all chain exists.
- [ ] `authorizeHttpRequests` uses `requestMatchers` with accurate semantics and HTTP methods, ending with `anyRequest`.
- [ ] Public URLs with `permitAll` are approved; `web.ignoring` is not used indiscriminately to bypass filters.
- [ ] Authentication source and `PasswordEncoder` are properly registered; user/password migration has tests.
- [ ] Custom `AuthenticationProvider`/manager beans exist only when needed and have failure tests.
- [ ] `@EnableMethodSecurity` replaces the legacy annotation; denied/authorized tests invoke through proxies.
- [ ] CSRF for sessions/forms still protects POST/PUT/PATCH/DELETE per the threat model.
- [ ] Form login, logout, request cache, redirects, and API 401 vs web 302 entry points have not drifted unintentionally.
- [ ] 403 missing role is tested distinctly from 403 missing CSRF, with dedicated negative cases.
- [ ] New endpoints outside the allowlist are denied, not routed outside the chain.
- [ ] Cookies, HTTPS, CORS, headers, forwarded proxies, sessions, and callback URLs are verified.
- [ ] Jakarta Servlet and third-party adapters are compatible with the current Boot/Security versions.
- [ ] No passwords/tokens are logged, no production users hardcoded, and `NoOpPasswordEncoder` is absent in prod.
- [ ] Before/after comparisons exist on a contract matrix rather than relying solely on startup success.

## 16. Knowledge check

**Question 1.** Why does Spring Security 6 no longer use `extends WebSecurityConfigurerAdapter`?

**Answer:** The adapter was removed; modern configuration uses `SecurityFilterChain` beans and separate authentication beans. The design shifts from override/inheritance to composition.

**Question 2.** Which API replaces `configure(HttpSecurity)`?

**Answer:** A `@Bean SecurityFilterChain` method accepting `HttpSecurity`, configuring it with the appropriate DSL, and returning `http.build()`.

**Question 3.** Does `securityMatcher("/api/**")` make `anyRequest().denyAll()` cover `/web/admin`?

**Answer:** No. `anyRequest` applies only to requests that match that chain. To protect URLs outside `/api/**`, you need another chain or a catch-all chain.

**Question 4.** When should an `AuthenticationManager` bean be declared?

**Answer:** When a component needs to inject/coordinate a specific manager or a custom authentication flow. Many applications only need `UserDetailsService` + `PasswordEncoder` and Spring's configured providers.

**Question 5.** Why prefer `permitAll` over `web.ignoring` for static resources?

**Answer:** `permitAll` requires no authentication while keeping requests inside Spring Security filters; `web.ignoring` skips those filters entirely.

**Question 6.** What replaces `@EnableGlobalMethodSecurity(prePostEnabled=true)`?

**Answer:** `@EnableMethodSecurity`, paired with tests confirming `@PreAuthorize` actually intercepts the Spring-managed bean's methods.

**Question 7.** Why might anonymous API requests return 302 instead of 401 after switching to bean config?

**Answer:** API URLs may be falling into the form-login chain/entry point, or chain selection/`@Order` is wrong. Separate the chains properly and assert `Location`/`WWW-Authenticate`.

**Question 8.** A POST without a CSRF token returns 403. Does that prove the role rule denied it?

**Answer:** No. `CsrfFilter` may reject the request earlier. To test role rules, attach a valid `csrf()` token and vary authorities.

**Question 9.** Does `@WithMockUser` test the real `PasswordEncoder`?

**Answer:** No. It mocks an `Authentication` for authorization testing. To test credentials/passwords, test HTTP Basic/`formLogin`/providers with valid and invalid credentials.

**Question 10.** Why do Java 17/Boot 3 upgrades require attention to Jakarta?

**Answer:** Jakarta EE Servlet APIs use `jakarta.servlet`; libraries still tied to legacy `javax.servlet` may be incompatible. Do not blindly replace every `javax` package, as many Java SE APIs keep that name.

---

**Conclusion:** Migrating from `WebSecurityConfigurerAdapter` to configuration beans is more than a syntax change. Separate **HTTP security** into `SecurityFilterChain` beans, separate **authentication** into `UserDetailsService`/`PasswordEncoder` and needed providers, upgrade method security to `@EnableMethodSecurity`, and preserve matcher/catch-all coverage, CSRF/session/login, and full 200/302/401/403 tests. A bean-based configuration is only complete once **pre- and post-upgrade security behaviors** have been verified and no endpoint has been inadvertently widened.