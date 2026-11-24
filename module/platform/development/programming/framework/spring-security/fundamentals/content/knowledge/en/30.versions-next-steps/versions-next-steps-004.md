# WebSecurityConfigurerAdapter, Legacy Matcher APIs, and Modern Lambda DSL

> **Scope:** HTTP security configuration for **Servlet / Spring MVC** applications using Spring Security. This lesson does not cover WebFlux configuration (`SecurityWebFilterChain`). The goal is to read legacy security code, migrate to bean-based configuration, and avoid altering access policies during version upgrades.

## 1. Why Did the Configuration Style Change?

Previously, applications typically created a class extending `WebSecurityConfigurerAdapter` and overrode `configure(HttpSecurity)`, `configure(WebSecurity)`, or `configure(AuthenticationManagerBuilder)`. That approach bundled multiple responsibilities into one subclass and easily led readers to confuse “which requests pass through the security filters” with “which users are authorized to access them.”

Modern configuration uses beans with clear, distinct responsibilities:

- **`SecurityFilterChain`**: describes the filters and HTTP rules; created via `HttpSecurity` and finalized with `http.build()`.
- **`UserDetailsService` / `AuthenticationProvider` / `PasswordEncoder`**: supplies user loading and authentication tailored to application needs.
- **`AuthenticationManager`**: only needs to be exposed as a bean when another component actually has to inject or invoke it.
- **`WebSecurityCustomizer`**: configures `WebSecurity`-level settings, especially requests that bypass the filter chain completely; use only intentionally.

The lambda style expresses the same policy using sub-blocks inside `HttpSecurity`; after each lambda call, configuration flow returns directly to the `HttpSecurity` object without needing `.and()`.

### Key Version Milestones to Recognize

| Version | Meaning when reading/migrating code |
| --- | --- |
| Spring Security 5.4 | Already supported declaring `SecurityFilterChain` beans directly. |
| Spring Security 5.7 | `WebSecurityConfigurerAdapter` was marked deprecated; Spring recommended component-based configuration. |
| Spring Security 5.8 | Transitional release providing APIs to prepare for upgrading to 6.x. |
| Spring Security 6.0 | Removed `WebSecurityConfigurerAdapter`; legacy `antMatchers`, `mvcMatchers` DSL APIs must be migrated to `requestMatchers`/appropriate matchers. |
| Spring Security 6.x | Uses `authorizeHttpRequests` + Lambda DSL; old chaining styles and many non-lambda configuration calls were marked for future removal. |
| Spring Security 7.0 | Lambda DSL is mandatory; `.and()` chaining and `authorizeRequests` are removed. `AntPathRequestMatcher`/`MvcRequestMatcher` are no longer supported; default path matching moves toward `PathPatternRequestMatcher`. |

**Do not infer the version solely from a code snippet.** Check the managed version in Maven/Gradle and the actual resolved dependencies. When upgrading Spring Boot, cross-check the accompanying Spring Security version as well. The runnable application example in section 5 targets Spring Boot 3.3.0 (Spring Security 6.x branch), while notes on 7.x indicate the API migration direction.

## 2. Recognizing Legacy-Style Configuration

A **historical example for Spring Security 5.x**, purely for understanding syntax; do not recompile verbatim on Spring Security 6/7:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.configuration.WebSecurityConfigurerAdapter;

@Configuration
@EnableWebSecurity
public class LegacySecurityConfig extends WebSecurityConfigurerAdapter {

    @Override
    protected void configure(HttpSecurity http) throws Exception {
        http
            .authorizeRequests()
                .antMatchers("/public/**").permitAll()
                .antMatchers(HttpMethod.GET, "/api/items/**").hasAnyRole("USER", "ADMIN")
                .antMatchers("/api/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            .and()
            .httpBasic();
    }
}
```

Reading top to bottom: `/public/**` allows public access; `GET /api/items/**` requires role `USER` or `ADMIN`; `/api/admin/**` requires `ADMIN`; remaining requests simply require authentication. `httpBasic()` enables HTTP Basic authentication so the API example has a way to send credentials. The `.and()` syntax returns configuration flow from `authorizeRequests()` back to `HttpSecurity`.

Legacy code **does not mean** all old matchers were a single API:

- `authorizeRequests().antMatchers(...)`: specifies **HTTP authorization** rules using Ant patterns.
- `authorizeRequests().mvcMatchers(...)`: used the old version's Spring MVC-integrated matcher semantics.
- `authorizeRequests().regexMatchers(...)`: used regular expressions in the legacy DSL.
- `http.antMatcher(...)`/`http.mvcMatcher(...)` (historical): scoped **an entire filter chain**, a different purpose from authorization inside the chain.
- `web.ignoring().antMatchers(...)`: excluded requests **from the entire Spring Security filter chain**, which is not equivalent to `permitAll()`.

When migrating, you must identify whether a matcher scopes a **chain**, defines an **authorization rule**, or **bypasses filters**.

## 3. API Conversion Map

| Legacy code / context | Modern direction | Reason |
| --- | --- | --- |
| `extends WebSecurityConfigurerAdapter` and `configure(HttpSecurity)` | `@Bean SecurityFilterChain filterChain(HttpSecurity http)` | Bean-based configuration, ending with `http.build()`. |
| `authorizeRequests()` | `authorizeHttpRequests(auth -> ...)` | Uses the modern `AuthorizationManager`/`AuthorizationFilter` model. |
| `antMatchers("/x/**")` or `mvcMatchers("/x/**")` in authorization | `requestMatchers("/x/**")` | Delegates rule matching to the modern DSL, picking the appropriate matcher per version and environment. |
| `regexMatchers(...)` in authorization | `requestMatchers(RegexRequestMatcher.regexMatcher(...))` | Explicitly specifies a regex matcher if truly needed. |
| `http.antMatcher("/api/**")` in chain config | `http.securityMatcher("/api/**")` | Selects which requests enter that chain. |
| `authorizeRequests().anyRequest()` | `authorizeHttpRequests(auth -> auth.anyRequest()...)` | Catch-all rule within the scope of the selected chain. |
| `.formLogin().and().httpBasic()` | `.formLogin(Customizer.withDefaults()).httpBasic(Customizer.withDefaults())` | Lambda DSL; `.and()` is gone in 7.x. |
| `configure(WebSecurity)` to skip URLs | `@Bean WebSecurityCustomizer`, if truly needing ignore | `ignoring()` skips filters and the protections they provide. |
| `configure(AuthenticationManagerBuilder)` | `UserDetailsService`, `AuthenticationProvider`, `PasswordEncoder` beans, or `AuthenticationManager` config when needed | Separates authentication concerns from HTTP rules. |
| `http.apply(customDsl)` | `http.with(customDsl, customizer)` on releases supporting the new API | Prepares for removing `.and()` in custom DSLs in 7.x. |

You must verify the actual `RequestMatcher` type when upgrading **6.x → 7.x**. On many 6.x releases, the `String`-taking overload can pick a matcher depending on whether Spring MVC is on the classpath; Spring Security 7 standardizes on `PathPatternRequestMatcher`. Do not assume the two matchers share identical syntax and semantics for all patterns. In particular, Ant patterns like `/**/admin` must be re-checked because `PathPattern` has different syntax restrictions.

## 4. How Does the Lambda DSL Work?

```java
http
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/public/**").permitAll()
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated()
    )
    .httpBasic(Customizer.withDefaults());

return http.build();
```

This is a **configuration snippet placed inside a bean method** and requires appropriate imports; a complete runnable program is in the next section.

- `auth -> ...` receives the dedicated authorization configurer object. When the lambda completes, you can keep chaining `.httpBasic(...)` on `HttpSecurity`.
- `Customizer.withDefaults()` is equivalent to an empty configuration lambda, using the feature's defaults. It does **not** mean “disable” the feature.
- `requestMatchers(...)` defines rules for requests matching the pattern. Rules are evaluated **in declaration order**; the first matching rule decides.
- `hasRole("ADMIN")` checks for authority `ROLE_ADMIN`; if stored authorities lack the `ROLE_` prefix, consider `hasAuthority("...")` matching the actual value.
- `anyRequest().authenticated()` is the fallback rule; place it **last** in the list. `denyAll()` is a stricter choice when the application only wants to expose explicitly listed endpoints.
- `permitAll()` removes the login requirement for that rule, but requests still traverse the filter chain; it does not disable CSRF or other protections.

Rule **ordering** mistake:

```java
// POLICY ERROR: /api/admin/** is already captured by the broader rule above it.
.requestMatchers("/api/**").authenticated()
.requestMatchers("/api/admin/**").hasRole("ADMIN")
```

```java
// CORRECT: specific first, general last.
.requestMatchers("/api/admin/**").hasRole("ADMIN")
.requestMatchers("/api/**").authenticated()
.anyRequest().denyAll()
```

## 5. Runnable Spring Boot Project: From Legacy Code to Modern Beans

The example uses **Java 17, Maven, and Spring Boot 3.3.0 / Spring Security 6.x**. Its purpose is testing matcher policies with HTTP Basic on GET endpoints; keeping default CSRF settings fits this example. This is a demo application, not a production user store or password handling setup.

### 5.1. File Structure

```text
security-migration-demo/
├── pom.xml
└── src/
    ├── main/java/example/demo/
    │   ├── DemoApplication.java
    │   ├── SecurityConfig.java
    │   └── DemoController.java
    └── test/java/example/demo/
        └── SecurityRulesTest.java
```

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
        <version>3.3.0</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>security-migration-demo</artifactId>
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
</project>
```

`src/main/java/example/demo/DemoApplication.java`:

```java
package example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

`src/main/java/example/demo/SecurityConfig.java`:

```java
package example.demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/items/**")
                    .hasAnyRole("USER", "ADMIN")
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
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
        return new InMemoryUserDetailsManager(
            User.withUsername("reader")
                .password(encoder.encode("reader-pass"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("USER", "ADMIN")
                .build()
        );
    }
}
```

Here `SecurityFilterChain` is **a bean**, so Spring Security uses it as the HTTP configuration. There is no `extends WebSecurityConfigurerAdapter`. Demo user provisioning is separated from matcher rules: `UserDetailsService` loads users, `PasswordEncoder` hashes passwords with BCrypt, and `SecurityFilterChain` decides URL access permissions.

`src/main/java/example/demo/DemoController.java`:

```java
package example.demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/api/items/{id}")
    public String item(@PathVariable String id) {
        return "item-" + id;
    }

    @GetMapping("/api/admin/report")
    public String report() {
        return "admin-only";
    }

    @GetMapping("/account")
    public String account() {
        return "signed-in";
    }
}
```

### 5.2. Running and Observing

From the directory containing `pom.xml`, using JDK 17+ and Maven:

```bash
mvn test
mvn spring-boot:run
```

Open another terminal on macOS/Linux; the following commands **print only the HTTP status code**, so they do not depend on framework headers or bodies:

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/public/ping
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/api/items/42
curl -s -o /dev/null -w '%{http_code}\n' -u reader:reader-pass http://localhost:8080/api/items/42
curl -s -o /dev/null -w '%{http_code}\n' -u reader:reader-pass http://localhost:8080/api/admin/report
curl -s -o /dev/null -w '%{http_code}\n' -u admin:admin-pass http://localhost:8080/api/admin/report
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/account
```

When the app runs on port 8080 without a proxy or other configuration changes, stdout in order is:

```text
200
401
200
403
200
401
```

Explaining each case: public needs no login; the item API without credentials receives an HTTP Basic challenge (**401**); USER can read the item (**200**); USER is authenticated but lacks the ADMIN role so gets **403**; ADMIN can read the report (**200**); unlisted paths still require login (**401**). With `formLogin` configured instead of `httpBasic` alone, unauthenticated requests may receive a **302** redirect to login; do not apply “every unauthenticated request always returns 401” across all application styles.

On Windows PowerShell, call `curl.exe` to avoid the `curl` alias; replace `/dev/null` with `NUL` when running directly on Windows.

### 5.3. Automated Policy Testing with MockMvc

`src/test/java/example/demo/SecurityRulesTest.java`:

```java
package example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityRulesTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointIsOpen() throws Exception {
        mvc.perform(get("/public/ping")).andExpect(status().isOk());
    }

    @Test
    void itemRequiresAuthentication() throws Exception {
        mvc.perform(get("/api/items/42")).andExpect(status().isUnauthorized());
    }

    @Test
    void readerMayViewItem() throws Exception {
        mvc.perform(get("/api/items/42").with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isOk());
    }

    @Test
    void readerMayNotViewAdminReport() throws Exception {
        mvc.perform(get("/api/admin/report").with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminMayViewReport() throws Exception {
        mvc.perform(get("/api/admin/report").with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk());
    }
}
```

`mvn test` should run these tests and the expected result is **5 passing tests** if the code and files match the above. For applications with state-changing methods like `POST`/`PUT`/`DELETE`, test CSRF specifically: when CSRF is enabled, MockMvc tests may need `.with(csrf())` alongside credentials. **Do not disable CSRF to fix a 403 test without analyzing how the application authenticates.**

## 6. Two Matcher Layers: Selecting the Filter Chain Before Selecting Rules

This is the most error-prone point when switching APIs.

```text
HTTP request
  ↓
DelegatingFilterProxy / FilterChainProxy
  ↓ select the FIRST SecurityFilterChain whose securityMatcher matches
Security filters in the chain (authentication, CSRF, authorization, ...)
  ↓ authorizeHttpRequests → requestMatchers → first matching rule
Controller if permitted
```

- `http.securityMatcher("/api/**")` = “which requests does **this chain** handle?”; if unconfigured, a chain's default matcher accepts every request.
- `authorizeHttpRequests(auth -> auth.requestMatchers("/api/admin/**")...)` = “**inside the selected chain**, what privileges does this request require?”.
- `anyRequest()` refers only to remaining requests **within the current chain**; it does not pull in requests outside that chain.
- When multiple `SecurityFilterChain` beans exist, `@Order(1)` is evaluated before `@Order(2)`; **only the first matching chain runs**, rather than combining authorizations across chains.
- If no chain matches, the request can **bypass Spring Security**, which is a serious security gap unless intentional.

Example of **two independent beans illustrating multi-chain configuration** (placed in the same `@Configuration` with appropriate imports):

```java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults());
    return http.build();
}

@Bean
SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/**").permitAll()
            .anyRequest().authenticated()
        )
        .formLogin(Customizer.withDefaults());
    return http.build();
}
```

`/api/admin/report` enters `apiChain` and applies the ADMIN rule; `/account` enters `fallbackChain`. Because the fallback has no `securityMatcher` of its own, it covers requests not picked up by earlier chains, including the default login page URL. If you declare only `apiChain`, requests outside `/api/**` are not protected by that chain. With multiple chains, also place filter-generated login/logout URLs within the appropriate chain's scope; a chain matching only `/api/**` typically cannot serve the default `/login` endpoint.

## 7. `requestMatchers`: Patterns, HTTP Methods, and Versions

`requestMatchers("/api/items/**")` is a path-based rule; `requestMatchers(HttpMethod.GET, "/api/items/**")` adds an HTTP method condition. If an application wants different permissions for GET vs. POST, define explicit rules per method or an appropriate fallback policy.

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/items/**").hasAuthority("item:read")
    .requestMatchers(HttpMethod.POST, "/api/items/**").hasAuthority("item:write")
    .anyRequest().denyAll()
)
```

The snippet above is a **fragment**; it requires a surrounding HTTP configuration and an authentication mechanism that grants those authorities. `hasAuthority("item:read")` matches the exact authority string; `hasRole("USER")` typically checks `ROLE_USER`. URL matchers primarily inspect the path and **do not evaluate query strings automatically**: `/api/items/42?preview=true` still hits path `/api/items/42`. To inspect parameters, use a custom `RequestMatcher` with corresponding tests.

### When Upgrading to Spring Security 7

Spring Security 7 uses `PathPatternRequestMatcher` in place of the discontinued Ant/MVC matcher mechanisms. Path rules must follow `PathPattern` semantics; URLs in the Java DSL are application-relative paths (excluding the context path). With multiple servlets, account for the **servlet path prefix** to avoid matching the wrong endpoint.

On releases supporting `PathPatternRequestMatcher`, you can declare matchers explicitly:

```java
import static org.springframework.security.web.servlet.util.matcher.PathPatternRequestMatcher.withDefaults;

// Fragment in a Spring Security configuration supporting PathPatternRequestMatcher:
var apiAdmin = withDefaults().matcher("/api/admin/**");
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(apiAdmin).hasRole("ADMIN")
    .anyRequest().authenticated()
);
```

This snippet illustrates explicit matcher usage on a release that provides that class; **do not** drop it verbatim into the Boot 3.3.0 project from section 5 if the Spring Security dependency does not provide the API yet. When migrating 6.x → 7.x, re-run matcher tests with trailing slashes, deep paths, encoded paths, multiple servlets, and `**` patterns; do not mechanically swap `AntPathRequestMatcher` for another class and assume full equivalence.

## 8. `permitAll()` Differs from `web.ignoring()`

Good example for opening static resources in a web application:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/css/**", "/js/**", "/images/**").permitAll()
    .anyRequest().authenticated()
);
```

Requests still traverse the security filters, so they can receive security headers and related protections. Conversely:

```java
@Bean
WebSecurityCustomizer webSecurityCustomizer() {
    return web -> web.ignoring().requestMatchers("/assets/**");
}
```

This `WebSecurityCustomizer` fragment makes `/assets/**` **bypass the Spring Security filter chain**. Use it only when requests genuinely must avoid all filters; Spring Security recommends preferring `permitAll()` for static resources. In particular, **do not** swap `web.ignoring()` for `permitAll()` or vice versa without evaluating the effects on filters, headers, auditing, and CSRF.

## 9. When a Legacy Application Still Configures AuthenticationManager

A historical adapter subclass might override `configure(AuthenticationManagerBuilder)` to add users, LDAP, or authentication providers. In modern bean-based configuration, do not blindly copy legacy syntax: preserve the **actual authentication mechanism** (password encoding, user store, provider order) and expose the corresponding beans.

If application code truly needs to inject `AuthenticationManager`, in Spring Security 6.x configuration you can obtain it via `AuthenticationConfiguration`:

```java
@Bean
AuthenticationManager authenticationManager(AuthenticationConfiguration configuration)
        throws Exception {
    return configuration.getAuthenticationManager();
}
```

This is an **additional fragment**; it requires importing `org.springframework.security.authentication.AuthenticationManager` and `org.springframework.security.config.annotation.authentication.configuration.AuthenticationConfiguration`. You do not need to declare this bean just for ordinary `HttpSecurity` configuration. With custom authentication providers or multiple filter chains, verify how providers are combined and the actual scope of the `AuthenticationManager` rather than assuming every application shares a single manager.

## 10. Common Migration Mistakes

1. **Upgrading dependencies to 6.x while keeping `extends WebSecurityConfigurerAdapter` or `antMatchers`.** This causes compilation errors because those APIs were removed. Switch to beans and modern matchers before running tests.
2. **Confusing `securityMatcher` with `requestMatchers`.** Misplacing them can leave requests unprotected by any chain; always maintain an appropriate fallback.
3. **Placing a broad rule before a specific rule.** For example, `/api/**` before `/api/admin/**` prevents the ADMIN rule from being reached; fix the order and test each URL.
4. **Writing `hasRole("ROLE_ADMIN")`.** `hasRole` prepends the role prefix by convention; use `hasRole("ADMIN")` or `hasAuthority("ROLE_ADMIN")` matching the stored value.
5. **Using `ignoring()` to expose static resources.** That bypasses all security filters; prefer `permitAll()` unless there is a strong reason to skip filters.
6. **Assuming `permitAll()` disables CSRF.** CSRF is a separate mechanism; state-changing requests can still receive 403 without a token.
7. **Keeping `.and()` or non-lambda DSL when preparing for 7.x.** Write Lambda DSL directly and use `Customizer.withDefaults()` for default feature configurations.
8. **Replacing Ant patterns with PathPattern without testing.** Wildcard syntax, servlet paths, and matching rules can differ; test edge cases.
9. **Forgetting filter-generated endpoints.** `formLogin()`, logout, or custom authentication endpoints may fall outside `securityMatcher`, causing 404s or broken login flows.
10. **Testing only successful requests.** A safe migration needs tests for 401 (unauthenticated), 403 (authenticated but unauthorized), 200 (authorized), and disallowed methods/URLs.

### Hands-On Pre-Sign-Off Migration Checklist

- [ ] Identify exact running Spring Boot/Spring Security and Java versions.
- [ ] Inventory legacy adapter configs, HTTP matchers, `WebSecurity` ignores, and authentication providers.
- [ ] Move HTTP rules to `SecurityFilterChain`; extract password/user/provider setup into explicit beans.
- [ ] Replace `authorizeRequests` with `authorizeHttpRequests`; replace legacy matchers according to **their exact role**.
- [ ] Review rule ordering from specific to general; put `anyRequest` last.
- [ ] With multiple chains, verify `@Order`, `securityMatcher`, fallback, and filter-generated endpoints.
- [ ] Preserve/verify CSRF, headers, sessions, CORS, authentication entry points, and exception handling against intended behavior.
- [ ] Write tests for anonymous, USER, and ADMIN across permitted and denied paths/methods.
- [ ] If upgrading to 7.x, remove legacy chaining DSL and re-verify all patterns against `PathPatternRequestMatcher`.

## 11. Official Sources for API Cross-Checking

- Spring Blog — *Spring Security without the WebSecurityConfigurerAdapter*: https://spring.io/blog/2022/02/21/spring-security-without-the-websecurityconfigureradapter
- Spring Security 6.5 — *Java Configuration*, especially multiple chains and `securityMatcher`: https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html
- Spring Security 6.5 — *Authorize HttpServletRequests*, including rule ordering and `permitAll` vs. `ignoring`: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- Spring Security — *Configuration Migrations for 7*: https://docs.spring.io/spring-security/reference/6.5/migration-7/configuration.html
- Spring Security — *Web Migrations for 7* (`PathPatternRequestMatcher`): https://docs.spring.io/spring-security/reference/6.5/migration-7/web.html

**Expected outcome:** reading a `WebSecurityConfigurerAdapter` configuration lets you recognize the legacy policy accurately; migrating to a `SecurityFilterChain` bean + Lambda DSL preserves authorization ordering, filter chain scoping, and HTTP protections, while you know which matchers must be re-evaluated when moving to Spring Security 7.
