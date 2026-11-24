# Identifying javax.servlet, jakarta.servlet, and Legacy-Generation Examples

## 1. Reading Spring Security by Version, Not Only by API Name

A common mistake when learning Spring Security is finding an article online, copying a configuration class, and immediately hitting `cannot find symbol`, `package javax.servlet does not exist`, or `WebSecurityConfigurerAdapter cannot be resolved`. Sometimes the code compiles, yet routes end up more open than intended. The root cause may lie not in Java syntax, but in the **generation of Spring Boot, Spring Framework, Spring Security, Servlet API, and dependent libraries**.

This lesson belongs to the **Versions and Next Steps** section of *Spring Security - fundamentals*. It helps distinguish:

- **Spring Boot 2.x / Spring Framework 5.x / Spring Security 5.x** patterns, which commonly contain `javax.servlet`, `WebSecurityConfigurerAdapter`, `authorizeRequests`, and `antMatchers`.
- **Spring Boot 3.x / Spring Framework 6.x / Spring Security 6.x** patterns, using `jakarta.servlet`, `SecurityFilterChain` beans, and `authorizeHttpRequests`.
- **Spring Boot 4.x / Spring Framework 7.x / Spring Security 7.x** patterns, still under the Jakarta namespace but with additional API changes and required Lambda DSL.
- **WebFlux** cases: using `SecurityWebFilterChain`, `ServerHttpSecurity`, and reactive `WebFilter`, not Servlet filters, regardless of whether the app is on Boot 3 or Boot 4.

The ultimate goal is not merely making the application “stop throwing errors,” but **preserving or improving the security policy**, verifying public/protected paths, roles, passwords, CSRF, sessions, filter matching, and object-level permissions after a version shift.

## 2. Quick Generation Identification Map

| Signal | Common legacy generation | Boot 3 / Security 6 generation | Boot 4 / Security 7 generation |
| --- | --- | --- | --- |
| Spring Boot | 2.7.x or older | 3.0–3.5.x | 4.0/4.1+ |
| Spring Framework | 5.3.x | 6.x | 7.x |
| Spring Security | 5.x (5.7/5.8 was the transition phase) | 6.x | 7.x |
| Servlet environment | Java EE/Jakarta EE 8, `javax.servlet` package | Jakarta EE `jakarta.servlet` namespace | Still `jakarta.servlet`, newer Servlet baseline |
| Validation | `javax.validation` | `jakarta.validation` | `jakarta.validation` |
| JPA | `javax.persistence` | `jakarta.persistence` | `jakarta.persistence` |
| Java | Many apps ran JDK 8/11 depending on 2.x release | Minimum **Java 17** | Minimum **Java 17** per current Boot 4 |
| Security config | `WebSecurityConfigurerAdapter` or bean chain | `@Bean SecurityFilterChain` | Bean chain, Lambda DSL required in Security 7 |
| How to verify facts | Read build files and pinned 5.x docs | Read build files and pinned 6.x docs | Read 7.x/Boot 4 migration guides |

This is a **heuristic map, not a one-to-one rule**. The `SecurityFilterChain` bean appeared in Spring Security 5.4, before generation 6. `WebSecurityConfigurerAdapter` was deprecated in 5.7 and removed in 6.0. Therefore, a tutorial containing `SecurityFilterChain` does not automatically prove it was written for Security 6; you must check the actual versions in `pom.xml` or `build.gradle`.

**Specific runnable version for this lesson:** the hands-on example selects **Spring Boot 3.5.16, Java 17+, and BOM-managed Security 6.x**. Boot 3.5.16 is a released version; it serves as an API-stable illustrative milestone, **not a recommendation to pick it as a long-term production branch in 2026**. Teams running Boot 4/Security 7 must consult that branch's migration docs; do not downgrade dependencies just to match an example.

## 3. `javax.servlet` and `jakarta.servlet` Are Two Different Binary Types

Before Jakarta EE 9, standard Servlet APIs used `javax.servlet`:

```java
// Legacy Servlet imports
import javax.servlet.Filter;
import javax.servlet.FilterChain;
import javax.servlet.ServletException;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;
```

Starting with Jakarta EE 9, the API namespace moved to `jakarta`, so Spring Boot 3.x projects use:

```java
// Jakarta Servlet imports
import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
```

Two classes with the same short name like `Filter` have **different fully-qualified class names**; they do not automatically convert into one another. A JAR compiled against `javax.servlet.Filter` cannot link with a filter chain using `jakarta.servlet.Filter`. Do not fix this by adding both Servlet API JARs so “the IDE finds the class”; that masks a binary/runtime mismatch instead of resolving it.

### Common Namespace Migration Table

| Legacy API | New Jakarta API | Purpose |
| --- | --- | --- |
| `javax.servlet.Filter` | `jakarta.servlet.Filter` | Servlet filter |
| `javax.servlet.http.HttpServletRequest` | `jakarta.servlet.http.HttpServletRequest` | HTTP request |
| `javax.servlet.http.HttpServletResponse` | `jakarta.servlet.http.HttpServletResponse` | HTTP response |
| `javax.servlet.ServletException` | `jakarta.servlet.ServletException` | Servlet exception |
| `javax.persistence.Entity` | `jakarta.persistence.Entity` | JPA entity |
| `javax.persistence.Id` | `jakarta.persistence.Id` | JPA primary key |
| `javax.validation.Valid` | `jakarta.validation.Valid` | Validation |
| `javax.validation.constraints.NotBlank` | `jakarta.validation.constraints.NotBlank` | Bean Validation constraint |
| `javax.annotation.PostConstruct` | `jakarta.annotation.PostConstruct` | Lifecycle callback |
| `javax.transaction.Transactional` | `jakarta.transaction.Transactional` | Jakarta Transactions API |

**Critically important:** not every `javax.*` package moved to `jakarta.*`. Many packages belonging to **Java SE** retain the `javax` name: `javax.crypto.Cipher`, `javax.net.ssl.SSLContext`, `javax.sql.DataSource`, `javax.xml.parsers.DocumentBuilder`, `javax.annotation.processing.Processor`. There is no blanket `javax.crypto` → `jakarta.crypto` replacement for the JDK.

Likewise, do not change `org.springframework.transaction.annotation.Transactional`; that is Spring's annotation, not Jakarta Transactions. For many third-party APIs, changing imports alone is insufficient because the **artifact/version** must also be compatible.

## 4. Checking Imports Alone Is Not Enough: Check the Build and Container

Spring Boot 2.x typically uses Servlet containers such as Tomcat 9 (`javax` namespace). Spring Boot 3.5 defaults to Tomcat 10.1/Servlet 6.0 and compatible Jakarta libraries via dependency management. Spring Boot 4 has newer container requirements; check the **System Requirements** page for the exact branch. A WAR compiled for Boot 3.x cannot be expected to run safely on Tomcat 9 merely because the methods are still named `doFilter`.

In Maven, a legacy sign may be a direct `javax.servlet:javax.servlet-api` dependency. With Boot 3, the Servlet API coordinates are `jakarta.servlet:jakarta.servlet-api`, though when using `spring-boot-starter-web` and an embedded container you **usually do not need to declare a separate API dependency**. Let the Spring Boot BOM pick the compatible version; do not pin the Servlet API arbitrarily.

Run these commands in the directory containing `pom.xml`:

```bash
java -version
mvn -version
mvn dependency:tree
mvn help:effective-pom
```

Check:

- The Spring Boot parent/BOM version, and whether it is overridden in child modules.
- That `spring-security-web`, `spring-security-config`, and Spring Framework belong to the same generation.
- Whether `javax.servlet-api`/`jakarta.servlet-api` or web container transitives introduce conflicts.
- That Hibernate/JPA/Validation libraries are Jakarta-compatible.
- Third-party starters, custom filters, servlet listeners, test dependencies, and the target WAR container.

With Gradle you can run:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-web --configuration runtimeClasspath
```

On Windows PowerShell/CMD, use `gradlew.bat` if the project provides the wrapper. The dependency tree is **evidence of runtime versions**, not mere guesswork from a single import statement.

## 5. Immediately Recognizing a Legacy `WebSecurityConfigurerAdapter` Example

The following example reflects the Spring Security 5 style:

```java
// HISTORICAL SNIPPET — cannot be copied verbatim into Security 6/7
@Configuration
@EnableWebSecurity
public class LegacySecurity extends WebSecurityConfigurerAdapter {

    @Override
    protected void configure(HttpSecurity http) throws Exception {
        http
            .authorizeRequests()
                .antMatchers("/public/**").permitAll()
                .antMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
                .and()
            .httpBasic();
    }
}
```

This is a **historical fragment**, not a file in the runnable project in section 8. The telltale signs:

1. `extends WebSecurityConfigurerAdapter`: subclassing a framework adapter, deprecated in 5.7 and removed in 6.0.
2. `configure(HttpSecurity)` with `@Override`: instead of a `SecurityFilterChain` bean.
3. `authorizeRequests()`: legacy authorization DSL; modern patterns use `authorizeHttpRequests(...)`.
4. `antMatchers(...)`: legacy matcher DSL; Security 6 uses `requestMatchers(...)` or explicit `RequestMatcher`s.
5. `.and().httpBasic()`: previous-generation fluent/nested DSL; Security 7 requires Lambda DSL.
6. The project often still contains `javax.servlet.*` when custom filters and servlet hooks are present.

A blog post with these markers is **not necessarily wrong in the context of the year it was written**. However, if your target is Boot 3/Security 6, do not bring back the adapter via an old dependency just to copy a tutorial. Convert the structure and **verify the semantics** of the policy.

### Corresponding Modern Configuration Pattern

```java
// FRAGMENT INSIDE A SECURITY 6 @Bean SecurityFilterChain
http
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/public/**").permitAll()
        .requestMatchers("/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated())
    .httpBasic(Customizer.withDefaults());

return http.build();
```

This pattern uses `AuthorizationManager`-based authorization and Lambda DSL. In a real project, additional configuration such as password encoder/provider, session, CSRF, OAuth2, or exception handling is needed depending on requirements; a two-line conversion **does not prove** the application has been fully migrated.

## 6. Legacy-to-Spring-Security-6 API Conversion Table

| Legacy code | Modern pattern | What else to check |
| --- | --- | --- |
| `extends WebSecurityConfigurerAdapter` | `@Bean SecurityFilterChain(HttpSecurity)` | How many chains, matchers, and fallbacks exist? |
| Override `configure(HttpSecurity)` | Configure bean then `return http.build()` | Is authentication/filter order preserved? |
| `authorizeRequests()` | `authorizeHttpRequests(auth -> ...)` | Request authorization/dispatch semantics |
| `antMatchers(path)` | `requestMatchers(path)` | MVC/Ant matching semantics and ordering |
| `mvcMatchers(path)` | `requestMatchers(path)` or explicit matcher | Servlet path and MVC infrastructure |
| `http.antMatcher(path)` | `http.securityMatcher(path)` | Scopes the **entire chain** |
| `http.csrf().disable()` | `http.csrf(csrf -> csrf.disable())` *only if truly needed* | Do not weaken CSRF protection unintentionally |
| `.and().formLogin()` | `.formLogin(Customizer.withDefaults())` | Login page, session, success handler |
| `.and().httpBasic()` | `.httpBasic(Customizer.withDefaults())` | Client/entry point, HTTPS |
| `@EnableGlobalMethodSecurity(prePostEnabled=true)` | `@EnableMethodSecurity` | Method proxies, SpEL, parameter names |
| `configure(AuthenticationManagerBuilder)` | `UserDetailsService` / `PasswordEncoder` / provider beans | Hashing, account status, lookup |
| `web.ignoring().antMatchers(...)` | `WebSecurityCustomizer` or consider `permitAll()` | Ignoring bypasses the filter chain, unlike permitAll |

Do not just find-and-replace tokens. Syntactically valid conversions can have **different security behavior**:

- `web.ignoring()` typically skips Spring Security filters and security headers; `permitAll()` still processes requests through the chain.
- `securityMatcher()` selects the chain; `requestMatchers()` inside `authorizeHttpRequests()` selects authorization rules. If no chain matches, Spring Security may **leave that request unprotected**.
- `hasRole("ADMIN")` normally checks authority `ROLE_ADMIN`, unlike `hasAuthority("ADMIN")` and `hasAuthority("SCOPE_admin")`.
- Configuring `anyRequest().permitAll()` can open every newly added route; prefer deny-by-default or a catch-all rule matching your requirements.
- When migrating `authorizeRequests` to `authorizeHttpRequests`, test HTTP methods, paths, servlet paths, dispatcher types, roles, and error handling.

## 7. `securityMatcher` and `requestMatchers` — One Word Off Changes the Whole Chain

Illustrative example with multiple chains:

```java
// FRAGMENT — methods must be placed inside a configuration class.
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(a -> a
            .requestMatchers("/api/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}

@Bean
SecurityFilterChain fallback(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(a -> a
            .anyRequest().denyAll())
        .build();
}
```

**Meaning:**

- `securityMatcher("/api/**")` states that the first chain **applies only** to URLs matching `/api/**`.
- `requestMatchers("/api/admin/**")` defines rules **inside the selected chain**.
- `@Order(1)` prioritizes the first chain; the fallback chain denies anything unmatched.
- If you omit the fallback chain, requests outside `/api/**` may bypass Spring Security even though you wrote `anyRequest().authenticated()` inside the API chain.

This is not a complete production configuration: real applications require CSRF, OAuth2/JWT, login, headers, and custom filters placed in the proper chain. Older docs calling `antMatcher` directly on `HttpSecurity` usually meant **scoping the entire chain**, which must not be mistakenly converted into a `requestMatchers` rule inside a global chain.

## 8. Runnable Java 17+ Example: Boot 3, `jakarta.servlet`, and Bean Chain

The complete example below runs with **Java 17+, Maven, Spring Boot 3.5.16, Spring MVC, and Spring Security 6.x**. It demonstrates a modern custom Servlet filter using `jakarta.servlet` signatures and an HTTP policy with verified behavior.

Goals:

- `GET /api/public` allows anonymous access and returns JSON.
- `GET /api/me` requires authentication and returns the username.
- `GET /api/admin` requires the `ADMIN` role.
- A custom filter adds the `X-Servlet-Namespace: jakarta` header to prove it executed.
- Demo accounts `alice/alice-pass` with role `USER` and `admin/admin-pass` with role `ADMIN`; passwords are encoded with `PasswordEncoder`.
- Tests cover anonymous access, wrong password, wrong role, and valid admin through the filter chain.

### 8.1. Project Structure

```text
security-jakarta-demo/
├── pom.xml
└── src/
    ├── main/java/demo/
    │   ├── SecurityJakartaApplication.java
    │   ├── SecurityConfiguration.java
    │   ├── ServletMarkerFilter.java
    │   └── ApiController.java
    └── test/java/demo/
        └── SecurityJakartaTests.java
```

### 8.2. Maven `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>security-jakarta-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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

This is a **complete Maven POM**, with `<plugin>` properly nested inside `<plugins>`. Do not add `javax.servlet-api`; the web starter selects the Jakarta Servlet container. The Boot parent manages the versions of Spring dependencies.

### 8.3. `src/main/java/demo/SecurityJakartaApplication.java`

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityJakartaApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityJakartaApplication.class, args);
    }
}
```

### 8.4. `src/main/java/demo/ServletMarkerFilter.java`

```java
package demo;

import java.io.IOException;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.web.filter.OncePerRequestFilter;

public final class ServletMarkerFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {
        response.setHeader("X-Servlet-Namespace", "jakarta");
        chain.doFilter(request, response);
    }
}
```

`jakarta.servlet.FilterChain`, `ServletException`, `HttpServletRequest`, and `HttpServletResponse` must be used **consistently**. Replacing even one of these with a `javax` version can break the `@Override` signature or fail at runtime.

**Avoiding double registration:** the filter is instantiated with `new ServletMarkerFilter()` inside the Spring Security chain, not annotated with `@Component` and not declared as a separate Servlet `Filter` bean. Spring Boot can automatically register Servlet `Filter` beans with the container; if you also add that same bean to the security chain, the filter may run twice or in the wrong order. This example avoids that pitfall.

The `X-Servlet-Namespace` header is **only a demo marker**, not a security header to add in production. Never put tokens, sessions, or passwords into custom headers for debugging.

### 8.5. `src/main/java/demo/SecurityConfiguration.java`

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;

import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

@Configuration
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password(encoder.encode("alice-pass"))
                        .roles("USER").build(),
                User.withUsername("admin")
                        .password(encoder.encode("admin-pass"))
                        .roles("ADMIN").build());
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/api/public")
                            .permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/me")
                            .authenticated()
                        .requestMatchers(HttpMethod.GET, "/api/admin")
                            .hasRole("ADMIN")
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .addFilterBefore(
                        new ServletMarkerFilter(),
                        UsernamePasswordAuthenticationFilter.class)
                .build();
    }
}
```

**Differences from legacy tutorials:**

- No more `extends WebSecurityConfigurerAdapter`; only a `SecurityFilterChain` bean.
- No calls to `authorizeRequests` or `antMatchers`; uses `authorizeHttpRequests`/`requestMatchers` by HTTP method and path.
- Lambda DSL needs no `.and()`.
- `hasRole("ADMIN")` requires the `ROLE_ADMIN` authority produced by `.roles("ADMIN")`.
- Passwords are hashed with a delegating encoder; never use `{noop}` in production.
- `httpBasic` handles `Authorization: Basic ...`; outside localhost, HTTPS is required.
- `formLogin` is disabled solely for this GET API demo; CSRF remains enabled by default. Do not assume HTTP Basic is automatically stateless or immune to CSRF.
- `addFilterBefore` inserts the filter at a well-known Spring Security position; no legacy adapter class is needed.

### 8.6. `src/main/java/demo/ApiController.java`

```java
package demo;

import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {

    @GetMapping("/api/public")
    public Map<String, String> publicEndpoint() {
        return Map.of("access", "public");
    }

    @GetMapping("/api/me")
    public Map<String, String> me(Authentication auth) {
        return Map.of("username", auth.getName());
    }

    @GetMapping("/api/admin")
    public Map<String, String> admin() {
        return Map.of("access", "admin");
    }
}
```

The controller uses `Authentication` supplied by Spring Security rather than trusting `isAdmin` or `role` values from JSON/request bodies. It does not need to import Servlet APIs directly; that is normal: **there is no reason to add Jakarta imports to a controller just to prove “modern code”**.

### 8.7. `src/test/java/demo/SecurityJakartaTests.java`

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc(addFilters = true)
class SecurityJakartaTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicApiAndJakartaFilterWork() throws Exception {
        mvc.perform(get("/api/public"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.access").value("public"))
                .andExpect(header().string(
                        "X-Servlet-Namespace", "jakarta"));
    }

    @Test
    void anonymousCannotReadMe() throws Exception {
        mvc.perform(get("/api/me"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongPasswordIsRejected() throws Exception {
        mvc.perform(get("/api/me")
                        .with(httpBasic("alice", "wrong")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void realAlicePasswordWorks() throws Exception {
        mvc.perform(get("/api/me")
                        .with(httpBasic("alice", "alice-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("alice"));
    }

    @Test
    void userIsForbiddenOnAdmin() throws Exception {
        mvc.perform(get("/api/admin")
                        .with(httpBasic("alice", "alice-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminIsAllowed() throws Exception {
        mvc.perform(get("/api/admin")
                        .with(httpBasic("admin", "admin-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.access").value("admin"));
    }
}
```

With `@SpringBootTest` and `@AutoConfigureMockMvc(addFilters = true)`, tests run through the application context's security filters. `httpBasic(...)` sets the credential header so the demo's real provider authenticates it. **`@WithMockUser` or `with(user(...))`** is suitable for testing authorization with a mock principal, but **does not** verify passwords. Never replace wrong/valid password tests with mock principals and conclude that authentication works.

`MockMvc` does not open an HTTP socket; if you need to test a real server, TLS, or Servlet container, run the JAR and add integration tests with `RANDOM_PORT` or an HTTP client. The demo header shows that the custom filter in the chain was invoked, not that every servlet filter in production is configured properly.

### 8.8. Building and Testing with curl

Requires JDK 17+, Maven 3.6.3+, and downloaded dependencies. In the directory with `pom.xml`:

```bash
java -version
mvn -version
mvn -q test
mvn -q -DskipTests package
java -jar target/security-jakarta-demo-0.0.1-SNAPSHOT.jar
```

Second terminal:

```bash
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/me
curl -i -u alice:wrong http://localhost:8080/api/me
curl -i -u alice:alice-pass http://localhost:8080/api/me
curl -i -u alice:alice-pass http://localhost:8080/api/admin
curl -i -u admin:admin-pass http://localhost:8080/api/admin
```

**Expected** HTTP statuses in order: **200, 401, 401, 200, 403, 200**. JSON when calling public:

```json
{
  "access": "public"
}
```

When Alice reads `/api/me`:

```json
{
  "username": "alice"
}
```

When admin reads `/api/admin`:

```json
{
  "access": "admin"
}
```

The public response includes the `X-Servlet-Namespace: jakarta` header; the test code checks this exact header name and value. JSON/header/error body formatting may vary by Spring/Jackson version. **This is expected output, not a recorded Maven execution log.** Never use demo accounts/passwords in production or Basic credentials over plain public HTTP.

## 9. Legacy Code Snippets You Can Read—But Should Not Paste Into New Projects

A legacy custom filter might be written as:

```java
// LEGACY FRAGMENT
import javax.servlet.FilterChain;
import javax.servlet.ServletException;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;
```

The modern signature must consistently use `jakarta.servlet.*` as shown in `ServletMarkerFilter`. If you mix `javax.servlet.FilterChain` with `jakarta.servlet.http.HttpServletRequest`, `@Override` will no longer match the base class method. The error “method does not override or implement a method from a supertype” is a cue to compare full package names in parameter signatures.

Legacy configuration:

```java
@EnableGlobalMethodSecurity(prePostEnabled = true)
public class OldMethodConfig {}

// In legacy adapter/config:
http.authorizeRequests().antMatchers("/admin/**").hasRole("ADMIN");
```

Switch to `@EnableMethodSecurity` and `@PreAuthorize` on Spring-managed beans; modern request authorization uses `authorizeHttpRequests`. However, **migrating method security does not automatically make data safe per owner/tenant**. `hasRole("ADMIN")` is only coarse-grained permission; services must still enforce resource-level checks.

The legacy pattern `web.ignoring().antMatchers("/css/**")` also needs review: ignoring skips the filter chain, whereas `permitAll()` lets requests pass through the chain and still receive other protections. Do not assume the two behaviors are equivalent by default.

## 10. JPA, Bean Validation, and Jakarta Are Not Just About Security

In Boot 3+ projects, these imports typically change together:

```java
// LEGACY
import javax.persistence.Entity;
import javax.persistence.Id;
import javax.validation.Valid;
import javax.validation.constraints.NotBlank;
```

```java
// NEW
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
```

These fragments only illustrate namespaces without complete entities or controllers. When upgrading:

- Use a Jakarta-compatible JPA/Hibernate provider rather than keeping an older ORM version.
- When you need Bean Validation in Spring MVC, declare `spring-boot-starter-validation` appropriately; do not assume the web starter includes all validators.
- Do not change JDBC's `javax.sql.DataSource`; it belongs to Java SE.
- Do not change `org.springframework.transaction.annotation.Transactional`; only the Jakarta Transactions API moved namespaces.
- Check third-party libraries too: a security filter from an external framework compiled against `javax` can prevent the app from starting even after you update all imports in your own source code.
- If using annotation processing, stale generated code or JPA metamodels can also keep `javax` in build outputs; clean and rebuild after updating.

Split migration into two questions: **has the source code switched namespaces properly?** and **are all runtime dependencies on the same Jakarta generation?** Both must be confirmed.

## 11. Do Not Confuse Servlet MVC with WebFlux

Spring MVC runs on a Servlet container and uses `HttpSecurity`, `SecurityFilterChain`, and `jakarta.servlet.Filter` when a Servlet Filter is needed. Spring WebFlux often runs on Reactor Netty and uses `ServerHttpSecurity`, `SecurityWebFilterChain`, and reactive `WebFilter`, without Servlet Filters in the normal reactive flow.

Reactive example (fragment, not a standalone program):

```java
@Bean
SecurityWebFilterChain reactiveSecurity(ServerHttpSecurity http) {
    return http
            .authorizeExchange(ex -> ex
                    .pathMatchers("/public").permitAll()
                    .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
}
```

If you encounter a WebFlux tutorial with neither `javax.servlet` nor `jakarta.servlet`, that does **not** mean it is outdated. It may simply be a different stack. Check `spring-boot-starter-webflux`, the application type, and the actual web server; if a project includes both web and webflux starters, do not guess the stack from a single import.

## 12. Security Behavior Changes You Must Not Overlook When Upgrading

### HTTP Matchers and Fallbacks

Differences among `antMatchers`, `mvcMatchers`, and `requestMatchers` can affect path pattern matching, servlet paths, and HTTP methods. Test both allowed URLs and similar URLs that must be blocked. With multiple security chains, verify `securityMatcher` and chain order so no request slips outside every chain.

### CSRF and Authentication Model

Many older examples wrote `http.csrf().disable()` just to call APIs from Postman. In Lambda DSL, the syntactic equivalent is `http.csrf(csrf -> csrf.disable())`—but **you should not do that by default**. Cookie/session applications and browser credential models carry CSRF risk; disable CSRF only with a clear architectural justification and explicit tests. `with(csrf())` in Spring Security Test verifies that requests with a CSRF token succeed, not that the UI actually renders the token.

### Method Security

`@EnableGlobalMethodSecurity(prePostEnabled=true)` is the legacy pattern; use `@EnableMethodSecurity` when upgrading and test `@PreAuthorize`/`@PostAuthorize`. When SpEL expressions reference parameter names, the migration guide advises checking the `-parameters` compiler flag. Spring AOP proxies may not intercept self-invocation, so do not rely solely on annotations for internal calls within the same bean.

### SecurityContext and Dispatch

Security 6 migrations introduced changes around servlet dispatcher types and security context persistence. An `ERROR`/`FORWARD` or async dispatch can be denied if rules do not account for it. Do not open `permitAll("/**")` to silence a 403; inspect dispatcher types, exception handling, session persistence, and release-specific rules.

### Roles/Scopes and Non-Namespace Changes

`hasRole("ADMIN")` checks `ROLE_ADMIN` by default; `hasAuthority("SCOPE_reports.read")` requires an authority with that exact name. When changing JWT converters or OAuth2 integrations, do not automatically map scopes to roles unless your policy defines that mapping. Changing `javax` to `jakarta` will not fix authority mapping bugs.

### Browser/UI/Static Resources

`web.ignoring()` can cause static files to bypass security filters and security headers; `permitAll()` in authorization rules does not. Test UI login/logout, session cookies, redirects, and CSS/JS assets during migration to catch issues that unit tests miss.

## 13. Error Messages and Systematic Troubleshooting

| Error/symptom | What to check | Resolution path |
| --- | --- | --- |
| `package javax.servlet does not exist` | `javax` code on a Boot 3/Jakarta classpath | Update imports and libraries to the same generation |
| `package jakarta.servlet does not exist` | Boot 2/legacy Servlet API or missing dependency | Check Boot version, starters, and runtime |
| `NoClassDefFoundError: javax/servlet/Filter` | Legacy JAR expecting `javax` on a Jakarta runtime | Upgrade/replace library; inspect dependency tree |
| `NoClassDefFoundError: jakarta/servlet/Filter` | Servlet API/container is too old | Use a Jakarta-compatible container |
| `method does not override...` | Signature mixes `javax` and `jakarta` or API changed | Compare full parameter class names |
| `cannot find symbol: WebSecurityConfigurerAdapter` | Security 5 code on Security 6/7 | Use a `SecurityFilterChain` bean |
| `cannot find symbol: antMatchers` | Legacy DSL was removed | Use `requestMatchers` + test semantics |
| 401 after migration | Authentication/session/entry point changed | Test credentials and context persistence |
| 403 after migration | Role, CSRF, dispatch, matcher, or method security | Identify which filter/rule rejected the request |
| 200 for a route that should be protected | No chain matched or fallback is too permissive | Verify `securityMatcher` and deny-by-default |
| Boot 3 WAR fails on Tomcat 9 | Jakarta WAR on a `javax` Servlet container | Upgrade to a Jakarta-compatible container |
| `@Valid` does not trigger | Missing Jakarta validation provider/starter | Check starter and constraints |

**Debugging order:** first verify runtime versions and the dependency tree; next read compile/class-loading errors; finally test each behavior group. Arbitrarily adding a `javax.servlet-api` JAR to a Boot 3 project just to turn a compile error into a runtime conflict is never a solution.

If `rg` (ripgrep) is available, search for legacy traces:

```bash
rg -n 'javax\.servlet|javax\.persistence|javax\.validation|WebSecurityConfigurerAdapter|authorizeRequests\(|antMatchers\(|mvcMatchers\(|EnableGlobalMethodSecurity' src
```

This command **only lists locations to inspect**; it modifies nothing. When searching a large source tree, identify test fixtures or historical migration code before deleting anything; not every occurrence of `javax` needs replacement, especially outside Jakarta APIs.

## 14. Testable Upgrade Process with Rollback Readiness

1. **Pin source and target:** Boot 2.7/Security 5 → Boot 3.x/Security 6, or Boot 3.5/Security 6 → Boot 4/Security 7. The two problems have different migration guides.
2. **Upgrade to the maintenance release and read deprecations:** Security 5.8 is the official stepping stone for Security 6. Do not override dependencies haphazardly to force new APIs.
3. **Verify Java/toolchain:** Boot 3 requires Java 17+ and compatible Maven/Gradle versions; check both CI and the runtime container.
4. **Upgrade the Jakarta ecosystem:** Servlet container, JPA provider, Validation, javax-based libraries, and WAR packaging.
5. **Convert Security config:** bean chains, Lambda DSL, request matchers, method security, and authentication providers/encoders.
6. **Build a before–after policy matrix:** public/protected paths, methods, roles/scopes, owner/tenant checks, login/logout, CSRF, sessions, and static resources.
7. **Run unit + MockMvc + HTTP integration tests:** invalid/valid credentials, 401/403, missing CSRF, unmatched paths, multiple chains, and dispatcher types if used.
8. **Verify deployment environment:** embedded JAR or WAR, reverse proxy, TLS, ingress, CORS, session store, and IdP/OAuth2/JWT issuer if present.
9. **Never fix failing tests by loosening permissions:** avoid `anyRequest().permitAll()` just because you saw a 403.
10. **Keep dependency locks and a rollback plan:** record BOM versions, plugin/container versions, regression test results, and intentional security changes.

Best practice: split the migration into small reviewable commits rather than simultaneously changing namespaces, rewriting authorization, and altering authentication architecture without comparative tests.

## 15. Continuing On to Spring Security 7 and Spring Boot 4

The Security 7 generation introduces further API changes and requires Lambda DSL, while Spring Boot 4 builds on Spring Framework 7 and newer Servlet/container baselines. **The `jakarta.servlet` namespace remains**, but updating imports alone is not enough to go from 6 → 7.

When learning or migrating onward:

- Always check **version-pinned** docs such as `/6.5/` when a project uses Security 6.5. An unpinned `/reference/` page may show the latest version and APIs missing in your project.
- From Boot 2.7, read the **Boot 3.0 Migration Guide** and **Security 5.8 → 6.0** first.
- From Boot 3.x, read **Security 6.5 → 7.0** and **Boot 3.5 → 4.0**; account for third-party starters, Jackson, testing, and JVM/container requirements.
- Study `Authentication`, `SecurityContext`, `AuthorizationManager`, `SecurityFilterChain`, and Servlet vs. reactive deeply—these concepts outlast DSL method names.
- If a tutorial uses `.and()`, `WebSecurityConfigurerAdapter`, or `javax.servlet`, clearly mark it as **legacy target** before deciding how to rewrite it.

Never downgrade Security dependencies or the Java runtime of a production project just to make a 2021 blog post compile. Keep the organization-approved stack and translate the tutorial's intent into compatible APIs.

## 16. Pitfalls to Avoid

1. “Every `javax.*` must become `jakarta.*`” — false, because many packages belong to Java SE.
2. “Adding both Servlet API JARs makes them compatible” — false; they are distinct binary types.
3. “`SecurityFilterChain` only exists in Security 6” — false, it was introduced in Security 5.4.
4. “Deprecated `WebSecurityConfigurerAdapter` still exists in Security 6” — false, it was removed.
5. “`antMatchers` and `requestMatchers` can simply be renamed without checking HTTP behavior” — dangerous.
6. “`securityMatcher` and `requestMatchers` are the same” — one selects the chain, the other selects rules.
7. “Use `.and()` on Security 7 like old tutorials” — no longer supported as before.
8. “Omit `@EnableMethodSecurity` because `@PreAuthorize` works automatically” — it must be enabled properly and invoked through a Spring proxy.
9. “Disable CSRF globally so POST tests pass” — can expose browser clients to vulnerabilities.
10. “`web.ignoring` and `permitAll` are identical” — they differ in whether requests go through the filter chain.
11. “Tomcat 9 runs a Boot 3 WAR normally” — incompatible namespaces/containers.
12. “Code compiles means the policy did not change” — tests must still verify 401/403, roles, matchers, and sessions.
13. “`javax.crypto` must become `jakarta.crypto`” — it is not a Jakarta EE API.
14. “JPA/Validation are unrelated to Boot upgrades because this lesson is about Security” — Boot 3 upgrades Jakarta across the whole ecosystem.
15. “If WebFlux errors on Servlet filters, just add `jakarta.servlet-api`” — reactive stacks use WebFilters.
16. “`@WithMockUser` proves the password is valid” — a mock principal bypasses credential validation.
17. “An admin role is enough to read any tenant/object” — object-level authorization must still be enforced.
18. “Every `<dependency>` or parent POM automatically gets compatible versions” — transitives or overrides can break the BOM.
19. “Hiding an endpoint from the menu protects the URL” — the server still requires authorization.
20. “The latest docs always match the project version” — pin versioned docs and verify APIs.

## 17. Checklist When Reading an Example Online

- [ ] Determine actual Boot/Framework/Security/JDK versions from build files and the dependency tree.
- [ ] Identify Servlet MVC vs. WebFlux, and embedded JAR vs. external WAR container.
- [ ] Inspect `javax.servlet`/`jakarta.servlet` imports; do not blindly rewrite Java SE packages.
- [ ] Verify JPA/Validation/third-party libraries are Jakarta-compatible.
- [ ] If you see `WebSecurityConfigurerAdapter`, `authorizeRequests`, `antMatchers`, or `.and()`, check the tutorial's target version.
- [ ] Migrate to a `SecurityFilterChain` bean and Lambda DSL where appropriate.
- [ ] Distinguish `securityMatcher` (selecting a chain) from `requestMatchers` (selecting rules).
- [ ] Verify path/method rule ordering, fallbacks, and multiple filter chains.
- [ ] Preserve authentication behavior, role prefixes, CSRF, sessions, login/logout, and method security.
- [ ] Do not use `web.ignoring` for protected endpoints; evaluate static resource policies.
- [ ] Write tests for 200/401/403, anonymous access, wrong credentials, and unintended routes.
- [ ] Test different object IDs/tenants, not just whether a user is logged in.
- [ ] Check Servlet container version before deploying a WAR.
- [ ] Never hardcode passwords or leave `permitAll("/**")` in production from a tutorial demo.
- [ ] Consult official docs for the exact release when APIs differ.

## 18. Self-Practice Exercises

1. A code snippet contains `javax.servlet.Filter`, `antMatchers`, and `WebSecurityConfigurerAdapter`. Hypothesize its generation and state how to verify it.
2. Why does `javax.crypto.Cipher` not need to be changed to `jakarta.crypto.Cipher`?
3. Explain the runtime difference between `javax.servlet.http.HttpServletRequest` and `jakarta.servlet.http.HttpServletRequest`.
4. A Security 5 configuration used `configure(HttpSecurity)`; which beans are needed in Security 6?
5. Distinguish `securityMatcher("/api/**")` and `requestMatchers("/api/admin/**")` for a `/health` request.
6. If an API chain exists without a fallback chain, are requests outside that chain guaranteed to be protected? Why or why not?
7. Why might adding `javax.servlet-api` to Boot 3 fail to fix `NoClassDefFoundError`?
8. When moving from `web.ignoring` to `permitAll`, how might security headers differ?
9. Why does getting 200 with `@WithMockUser` fail to prove the username/password provider works?
10. A Boot 3 WAR fails to start on Tomcat 9: what should you check?
11. What kind of test catches a semantics change when moving from `antMatchers` to `requestMatchers`?
12. When moving from Security 6 to 7, why are Lambda DSL and migration docs important?
13. Name three errors caught immediately at compile time and three errors that appear only at runtime or in security tests.
14. Why does a WebFlux application not need to import `jakarta.servlet.Filter`?
15. Write a 2.7 → 3.5 migration plan covering versions, Jakarta, filter chains, passwords, and regression tests.

## 19. Versioned Official Documentation

- [Spring Boot 3.0 Migration Guide — Jakarta EE and Java 17](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide)
- [Spring Boot 3.5 System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html)
- [Spring Security 6.5 — Migrating to 6.0](https://docs.spring.io/spring-security/reference/6.5/migration/index.html)
- [Spring Security 6.5 — Servlet Migration](https://docs.spring.io/spring-security/reference/6.5/migration/servlet/index.html)
- [Spring Security 6.5 — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security 6.5 — Java Configuration and Matchers](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html)
- [Spring Security 6.5 — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Security 6.5 — MockMvc Testing](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/index.html)
- [Spring Security 6.5 — Lambda DSL Migration to 7](https://docs.spring.io/spring-security/reference/6.5/migration-7/configuration.html)
- [Spring Security 7 — Migrating to 7.0](https://docs.spring.io/spring-security/reference/migration/)
- [Spring Security without WebSecurityConfigurerAdapter — Spring team](https://spring.io/blog/2022/02/21/spring-security-without-the-websecurityconfigureradapter)
- [Spring Boot 4 System Requirements](https://docs.spring.io/spring-boot/system-requirements.html)

**Key takeaway:** `javax.servlet` → `jakarta.servlet` is an **API and binary compatibility boundary**, whereas `WebSecurityConfigurerAdapter` → `SecurityFilterChain` is a **Spring Security configuration change**. A migration is complete only when **dependencies, imports, filter chains, and security tests** all match your project's version—not merely when the IDE stops showing red squiggles.
