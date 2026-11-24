# Migrating antMatchers, mvcMatchers, and Choosing Compatible RequestMatchers — Spring Security Servlet

> **Context:** Upgrading from Spring Security 5.x / Spring Boot 2.x to Spring Security 6.x / Spring Boot 3.x (Java 17+) in Servlet/Spring MVC applications. The goal is not merely making code compile, but **preserving access allow/deny boundaries** when migrating `antMatchers` and `mvcMatchers` to `requestMatchers`, distinguishing `securityMatcher` from authorization matching, and choosing `MvcRequestMatcher`, `AntPathRequestMatcher`, `RegexRequestMatcher`, or PathPattern-based matchers where supported by your version.

## 1. Why is upgrading matchers a security-sensitive change?

Consider a Spring Security 5.x configuration:

~~~java
// LEGACY STYLE: do not use directly in a Spring Security 6 project.
http.authorizeRequests()
    .antMatchers("/public/**").permitAll()
    .antMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated();
~~~

Mechanically renaming the methods:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public/**").permitAll()
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated()
);
~~~

may work for simple apps, yet does not prove every request is classified the same way as before. When a URL involves a context path, custom `DispatcherServlet` path, trailing slash, or encoded segments, **a security matcher may interpret the path differently from MVC handler mapping**. Adding multiple `SecurityFilterChain` beans introduces another question: does the request even enter a protective chain?

A high-quality migration must answer:
- Which URLs remain public, which require authentication, and which require `ROLE_ADMIN`?
- Which **HTTP methods**, servlet paths, and normalized paths are the matchers checking?
- Could `/api/admin/**` be shadowed by an earlier `/api/** permitAll` rule?
- Are there requests that match no `SecurityFilterChain` at all?
- Does Spring MVC interpret paths the same way as the security matcher?
- Does the security policy test **unauthorized** users as well as authorized ones?

**Core takeaway:** API changes must be accompanied by testing **authorization semantics** along real HTTP paths.

## 2. From legacy APIs to modern APIs

| Intent | Spring Security 5.x style API | Common Spring Security 6.x approach |
| --- | --- | --- |
| Declare HTTP rules | `authorizeRequests()` | `authorizeHttpRequests(auth -> ...)` |
| Ant-style URL patterns | `antMatchers("/a/**")` | `requestMatchers("/a/**")` when auto-selection fits, or explicit matcher |
| MVC-style URL patterns | `mvcMatchers("/a/**")` | `requestMatchers(new MvcRequestMatcher(...))` / `MvcRequestMatcher.Builder` |
| Specific HTTP method | `antMatchers(HttpMethod.GET, "/a/**")` | `requestMatchers(HttpMethod.GET, "/a/**")` |
| Regex URL matching | `regexMatchers(...)` | `requestMatchers(new RegexRequestMatcher(...))` |
| Select filter chain scope | Legacy `antMatcher(...)`/`requestMatcher(...)` on `HttpSecurity` | `http.securityMatcher(...)` |
| Catch-all rule | `anyRequest().authenticated()` | `anyRequest().authenticated()` or `denyAll()` |
| Exclude resources from security chain | `web.ignoring().antMatchers(...)` | `WebSecurityCustomizer` using the new API, or usually better: `permitAll` |
| Role check | `hasRole("ADMIN")` | `hasRole("ADMIN")`, while verifying actual authority prefix |
| Authority check | `hasAuthority("SCOPE_read")` | `hasAuthority("SCOPE_read")` |

Modern `authorizeHttpRequests` uses **AuthorizationManager** and typically `AuthorizationFilter`, unlike older setups built on `FilterSecurityInterceptor` and custom voters. If a project previously used `AccessDecisionVoter`, `SecurityMetadataSource`, or custom interceptors, do not expect all custom behavior to carry over automatically from DSL changes alone.

### 2.1. Do not confuse the requestMatchers API with a specific matcher class

`requestMatchers(String...)` is a **convenience configuration overload**. It does not mean “always creates `AntPathRequestMatcher`” or “always creates `MvcRequestMatcher`” across every release and Servlet topology. In several Spring Security 6.x versions, the implementation auto-selects based on Spring MVC's presence and context. When multiple servlet mappings exist, auto-selection may be ambiguous or fail with an ambiguity error.

Whenever **matcher type** affects a security boundary, choose an explicit `RequestMatcher` suited to your app **and verify it on your exact runtime version** rather than relying on a blog post written for a different minor release.

## 3. What does RequestMatcher accept and return?

`org.springframework.security.web.util.matcher.RequestMatcher` determines whether an `HttpServletRequest` matches a condition. Conceptually:

~~~text
GET /api/admin/users
          |
          v
RequestMatcher.matches(request)
          |
       true/false
          |
          v
Corresponding authorization rule:
permitAll / authenticated / hasRole / hasAuthority / access(...)
~~~

A matcher can inspect:
- HTTP method;
- URI path normalized by the Servlet container and firewall;
- servlet path, path info;
- dispatcher type;
- regular expressions or AND/OR/NOT combinations of other matchers.

A matcher **only selects applicability scope**. It does not make an authorization decision on its own. `.requestMatchers("/api/admin/**").hasRole("ADMIN")` has two parts: **match the request**, then **check the authority**.

A request can match multiple patterns simultaneously. In standard `authorizeHttpRequests` configuration, rules are evaluated **in declaration order**, and the **first matching rule** determines the policy. Rule ordering is therefore part of your security contract.

## 4. Distinguishing securityMatcher from requestMatchers: two different layers

~~~text
Servlet request
      |
      v
FilterChainProxy
      |
      +--> SecurityFilterChain #1
      |    securityMatcher("/api/**") ? 
      |         |
      |         +-- yes -> run filters, then enter authorization:
      |                   requestMatchers("/api/admin/**").hasRole("ADMIN")
      |                   requestMatchers("/api/public/**").permitAll()
      |                   anyRequest().denyAll()
      |
      +--> SecurityFilterChain #2
      |    securityMatcher("/web/**") ?
      |
      +--> fallback SecurityFilterChain (if present)
~~~

- **`http.securityMatcher(...)`** decides which HTTP requests **enter an entire SecurityFilterChain**.
- **`authorizeHttpRequests(...).requestMatchers(...)`** decides rules **inside the already selected chain**.
- **`anyRequest().denyAll()` in chain #1 does not protect URLs that do not match chain #1's `securityMatcher`**.

Example missing a fallback:

~~~java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

This is an **illustrative fragment** (imports/config needed). If only this chain is declared, `/web/admin` is outside `/api/**`. You cannot look at `anyRequest()` inside `apiChain` and assume `/web/admin` is protected.

Add an explicit fallback:

~~~java
@Bean
@Order(2)
SecurityFilterChain fallback(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().denyAll())
        .build();
}
~~~

Both snippets are fragments illustrating **multiple chains** and do not need to be added to the single-chain project in Section 10. Test `@Order` precedence, each chain's scope, login/logout paths, and the fallback; prevent an overly broad chain from intercepting requests before the API chain.

### 4.1. Which chain must contain login/logout URLs?

A UI chain matching only `/web/**` conflicts with `formLogin` defaulting to POST `/login`. If `/login` does not belong to the UI chain, that chain's login filter **never receives the request**, leading to 404, 401, or redirect loops. When migrating:
- review `loginProcessingUrl`, `loginPage`, and `logoutUrl`;
- include those endpoints in the right chain's matcher;
- test real login/logout over HTTP;
- never apply global `permitAll` to paper over chain-matching mistakes.

Likewise, OAuth2 callbacks, SAML endpoints, Actuator, and error paths need the right chain and Servlet mapping, not only authorization rules.

## 5. Rule ordering and default policies

Dangerous example:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").permitAll()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().denyAll())
~~~

A request to `/api/admin/users` matches `/api/**` first: the `ADMIN` rule below **cannot rescue it**. A test checking only an `ADMIN` user will still pass, allowing the bug to slip into production.

Intentional ordering:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/public/**").permitAll()
    .anyRequest().denyAll())
~~~

In real apps, also test `/api/admin`, `/api/admin/`, `/api/administrator`, encoded paths, and HTTP methods for your matcher/version. **Do not assume root paths match `/**` identically across all matcher algorithms.**

### 5.1. Preserving HTTP methods during migration

Legacy config:

~~~java
// Legacy: opens GET only.
.antMatchers(HttpMethod.GET, "/reports/**").permitAll()
~~~

New config preserving meaning:

~~~java
.requestMatchers(HttpMethod.GET, "/reports/**").permitAll()
~~~

If you replace it with `requestMatchers("/reports/**").permitAll()`, you **may expose POST, PUT, PATCH, and DELETE** on the same URL whenever a controller supports those methods later. That is a serious migration bug.

For write endpoints, define method-specific rules and verify **CSRF** independently. A 403 on POST may come from CSRF rather than a non-matching `RequestMatcher`; never disable CSRF just to make tests pass.

### 5.2. Do not equate hasRole with hasAuthority

`hasRole("ADMIN")` typically requires authority `ROLE_ADMIN` when using the default role prefix. `hasAuthority("ADMIN")` requires the exact string `ADMIN`. JWT scopes usually map to `SCOPE_xxx` under default converters. Changing matchers must not silently alter authority strings outside tested plans.

## 6. AntPathRequestMatcher: when legacy Ant semantics must be preserved

`AntPathRequestMatcher` in Spring Security Web releases **that still provide this class** performs Ant-style matching. An explicit example:

~~~java
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;

AntPathRequestMatcher matcher =
    new AntPathRequestMatcher("/api/admin/**");

http.authorizeHttpRequests(auth -> auth
    .requestMatchers(matcher).hasRole("ADMIN")
    .anyRequest().denyAll());
~~~

This is a **fragment**, not a standalone compilable class. Choose an explicit Ant matcher when you must **preserve legacy behavior and have verified version support**—such as non-MVC Servlet apps or temporary migrations needing old pattern compatibility.

Points to test:
- `*` and `**` are Ant-style wildcards, **not regex**.
- Patterns ending in `/**` may have special optimization semantics in some versions; test root and trailing slashes.
- HTTP methods can be constrained by passing the method to the matcher constructor.
- Matching operates on Servlet request path components, typically `servletPath + pathInfo`, **not the full client URL including context path and query string**.
- Case sensitivity, percent decoding, semicolon segments, and firewall normalization are differences you must test.
- On newer Spring Security versions where this matcher is deprecated or superseded by `PathPattern`, plan a migration path. **Do not lock every Security 6.x release onto legacy classes permanently.**

### 6.1. When should an explicit Ant matcher be avoided?

If Spring MVC routing uses `PathPatternParser` or complex servlet paths, an Ant matcher may evaluate URLs differently from MVC controllers. Vulnerabilities arise when security decides a path misses a restricted rule while MVC routes it to a sensitive handler.

In MVC apps, align matcher and handler semantics. If you pick Ant explicitly to “silence an ambiguity exception,” verify the pattern truly covers the servlet handling the request rather than merely bypassing the exception.

## 7. MvcRequestMatcher: aligning with Spring MVC HandlerMapping

`MvcRequestMatcher` relies on `HandlerMappingIntrospector` to leverage Spring MVC path-mapping awareness. It is useful when URLs are handled by Spring MVC's `DispatcherServlet`, especially with custom servlet paths where security must match MVC interpretation.

Explicit example:

~~~java
import org.springframework.web.servlet.handler.HandlerMappingIntrospector;
import org.springframework.security.web.servlet.util.matcher.MvcRequestMatcher;

@Bean
SecurityFilterChain mvcSecurity(
        HttpSecurity http,
        HandlerMappingIntrospector introspector)
        throws Exception {

    MvcRequestMatcher.Builder mvc =
        new MvcRequestMatcher.Builder(introspector);

    return http.authorizeHttpRequests(auth -> auth
        .requestMatchers(mvc.pattern("/admin/**"))
            .hasRole("ADMIN")
        .requestMatchers(mvc.pattern("/public/**"))
            .permitAll()
        .anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

This is a **fragment requiring remaining imports** and a configured Spring MVC context. Do not drop this fragment into another config project and inadvertently create two competing chains.

**`HandlerMappingIntrospector` must belong to the right MVC application context.** In apps with a root servlet context plus a child `DispatcherServlet` context, placing `SecurityFilterChain` in the wrong context can fail to locate the introspector or see the real handler mappings. Never work around that with an empty self-instantiated introspector. Inspect the `mvcHandlerMappingIntrospector` bean, application contexts, and the real `DispatcherServlet` mapping.

### 7.1. Servlet path vs context path

Suppose an app configures:
- `server.servlet.context-path=/shop`;
- `spring.mvc.servlet.path=/app` in a supporting Boot version;
- controller `@GetMapping("/orders/{id}")`.

A client calls `/shop/app/orders/42`. However:
- context path `/shop` belongs to the Servlet container;
- servlet path `/app` belongs to the `DispatcherServlet` mapping;
- the Spring MVC controller pattern may be `/orders/{id}`.

With an explicit `MvcRequestMatcher`:

~~~java
MvcRequestMatcher.Builder mvc =
    new MvcRequestMatcher.Builder(introspector)
        .servletPath("/app");

http.authorizeHttpRequests(auth -> auth
    .requestMatchers(mvc.pattern("/orders/**"))
        .authenticated()
    .anyRequest().denyAll());
~~~

This is a fragment. **Do not prepend `/shop` to the MVC pattern automatically**. Across different Servlet mappings, `getServletPath()` and `getPathInfo()` values can change; verify with integration tests on the real configuration.

### 7.2. Multiple Servlets can create ambiguity

An application might host an MVC `DispatcherServlet`, an H2 console servlet, and a `/legacy/*` servlet. `requestMatchers("/api/**")` is not necessarily unambiguous across all three. Several Spring Security 6 releases detect ambiguous mappings and require explicit `RequestMatcher`s.

Solution:
1. Identify which servlet actually serves each request.
2. For MVC endpoints, use `MvcRequestMatcher` in the right context.
3. For non-MVC servlets, use an explicit matcher supporting that Servlet's path rather than assuming the MVC introspector knows every Servlet.
4. Keep chain-level `securityMatcher` and authorization matchers aligned around meaningful URL boundaries.
5. Test every protected Servlet endpoint, especially dev-only console/debug endpoints.

## 8. PathPatternRequestMatcher: use only when supported by your version

Modern Spring Framework provides `PathPatternParser` for segment-based path matching. **Newer** Spring Security 6.x branches offer `PathPatternRequestMatcher` or an equivalent mechanism; builder names, factories, and defaults vary across minor versions.

A **conditional illustrative** snippet, **not part of the Boot 3.3.5 project below**:

~~~java
// Compiles only if your Security version includes this API:
PathPatternRequestMatcher.Builder builder =
    PathPatternRequestMatcher.withDefaults();

RequestMatcher matcher =
    builder.matcher("/api/**");
~~~

Do not copy this into a project merely because an article says “Spring Security 6” without naming the minor version. Check:
- whether the API is actually published in your current dependency;
- whether `basePath` is needed for a custom `DispatcherServlet` mapping;
- whether Spring MVC uses a compatible `PathPatternParser`;
- differences in trailing slashes, wildcards, and encoded paths;
- package names, deprecations, and migration notes for your exact version.

When upgrading versions, prefer a compatible Spring Boot dependency management/BOM. Do not upgrade `spring-security-web` alone to get a newer matcher class while `spring-security-config`, `spring-security-core`, and Spring Framework remain misaligned.

**Key point:** `PathPattern` matchers can be a clean upgrade target on compatible stacks, yet migration requires tests; never swap an “Ant wildcard” for a “PathPattern wildcard” assuming universal equivalence across all URLs.

## 9. RegexRequestMatcher and custom matchers

Sometimes special path formats are needed:

~~~java
import org.springframework.security.web.util.matcher.RegexRequestMatcher;

RegexRequestMatcher invoices =
    new RegexRequestMatcher("^/api/invoices/[0-9]+$", "GET");

http.authorizeHttpRequests(auth -> auth
    .requestMatchers(invoices).hasRole("FINANCE")
    .anyRequest().denyAll());
~~~

This is an illustrative fragment. Regexes should use `^`/`$` anchors and be tested against request path representations, escaping, and HTTP methods. Avoid regex when a simple Spring MVC pattern suffices. When writing a custom `RequestMatcher`, test URI variants, methods, servlet mappings, and normalization; never build a matcher using `requestURI.startsWith` while ignoring context paths and segment boundaries.

An overly broad matcher lets public rules swallow sensitive paths; an overly narrow matcher lets URLs slip into another fallback or chain. Both must be caught in regression tests.

## 10. Runnable project with Java 17, Spring Boot 3.3.5, and MockMvc

This project demonstrates migration in **a simple Servlet/MVC application** using `authorizeHttpRequests` and `requestMatchers(String, HttpMethod)`. Explicit `MvcRequestMatcher` (Section 7) and `PathPattern` (Section 8) are **topology/version alternatives**, not pieces required inside this project.

### 10.1. Structure

~~~text
request-matcher-demo/
  pom.xml
  src/
    main/
      java/com/example/matcherdemo/
        MatcherDemoApplication.java
        SecurityConfig.java
        DemoController.java
    test/
      java/com/example/matcherdemo/
        MatcherPolicyTest.java
~~~

**Spring Boot 3.3.5** is solely a reproducible baseline for Java 17, **not** a claim that it is the latest release. When using another version, consult its matching documentation.

### 10.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.5</version>
    <relativePath/>
  </parent>

  <groupId>com.example</groupId>
  <artifactId>request-matcher-demo</artifactId>
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

### 10.3. Application

**`src/main/java/com/example/matcherdemo/MatcherDemoApplication.java`:**

~~~java
package com.example.matcherdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MatcherDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(MatcherDemoApplication.class, args);
    }
}
~~~

### 10.4. SecurityConfig

**`src/main/java/com/example/matcherdemo/SecurityConfig.java`:**

~~~java
package com.example.matcherdemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice-pass"))
            .authorities("ROLE_USER", "SCOPE_reports.read")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-pass"))
            .authorities("ROLE_ADMIN", "SCOPE_reports.read")
            .build();

        return new InMemoryUserDetailsManager(alice, admin);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/api/admin/**")
                    .hasRole("ADMIN")
                .requestMatchers(
                    HttpMethod.GET, "/api/reports/**")
                    .hasAuthority("SCOPE_reports.read")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(
                    SessionCreationPolicy.STATELESS))
            // Demo exposes only GET endpoints; CSRF is not disabled.
            .build();
    }
}
~~~

**Why is this configuration a clear migration example?**

- `requestMatchers("/public")` covers the public GET endpoint.
- `/api/admin/**` requires `ROLE_ADMIN`; an authenticated `USER` still gets 403.
- `requestMatchers(HttpMethod.GET, "/api/reports/**")` **preserves the GET method**; controllers on other HTTP methods will not open automatically.
- `SCOPE_reports.read` is explicitly granted to `alice` and `admin`, so `ADMIN` is not mistakenly assumed to hold all scopes.
- `anyRequest().denyAll()` blocks unlisted endpoints rather than “allowing anything authenticated” out of habit.
- HTTP Basic is enabled to test real authentication; form login is disabled to avoid entry-point ambiguity.
- `SessionCreationPolicy.STATELESS` is not a matcher-migration requirement; it is simply this API demo's choice.
- CSRF remains enabled. When adding state-changing POST endpoints, design and test CSRF separately.
- Hardcoded demo passwords in source **are for localhost only**; production must use proper identity/secret management and HTTPS.

### 10.5. Controller

**`src/main/java/com/example/matcherdemo/DemoController.java`:**

~~~java
package com.example.matcherdemo;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public Map<String, String> publicRoute() {
        return Map.of("message", "public");
    }

    @GetMapping("/api/admin/panel")
    public Map<String, String> admin(Authentication authentication) {
        return Map.of(
            "area", "admin",
            "user", authentication.getName());
    }

    @GetMapping("/api/reports/monthly")
    public Map<String, String> monthly(Authentication authentication) {
        return Map.of(
            "report", "monthly",
            "user", authentication.getName());
    }

    @GetMapping("/api/other")
    public Map<String, String> deniedByFallback() {
        return Map.of("message", "should-not-be-visible");
    }
}
~~~

`/api/other` is deliberately an **existing route** without an allow rule so we can test the `denyAll` fallback. Testing a non-existent URL and seeing 404 does not prove access control worked.

### 10.6. MockMvc integration tests

**`src/test/java/com/example/matcherdemo/MatcherPolicyTest.java`:**

~~~java
package com.example.matcherdemo;

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
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MatcherPolicyTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicRouteIsAvailableAnonymously() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("public"));
    }

    @Test
    void anonymousCannotEnterAdmin() throws Exception {
        mvc.perform(get("/api/admin/panel"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void ordinaryUserCannotEnterAdmin() throws Exception {
        mvc.perform(get("/api/admin/panel")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanEnterAdmin() throws Exception {
        mvc.perform(get("/api/admin/panel")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.area").value("admin"))
            .andExpect(jsonPath("$.user").value("admin"));
    }

    @Test
    void userWithScopeCanReadReports() throws Exception {
        mvc.perform(get("/api/reports/monthly")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.report").value("monthly"));
    }

    @Test
    void anonymousCannotReadReports() throws Exception {
        mvc.perform(get("/api/reports/monthly"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void fallbackDeniesAuthenticatedUser() throws Exception {
        mvc.perform(get("/api/other")
                .with(httpBasic("alice", "alice-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void wrongPasswordIsNotAccepted() throws Exception {
        mvc.perform(get("/api/admin/panel")
                .with(httpBasic("admin", "wrong")))
            .andExpect(status().isUnauthorized());
    }
}
~~~

**Test explanation:**
1. `@SpringBootTest` and `@AutoConfigureMockMvc` load the real Spring Security `FilterChainProxy` in the test context.
2. `httpBasic("user","password")` sends an `Authorization` header so the provider validates credentials, unlike `@WithMockUser` which mocks `Authentication`.
3. `USER` gets 403 on admin and `ADMIN` gets 200, proving the role rule is enforced rather than merely confirming the endpoint exists.
4. Reports require the matching scope; never assume `ADMIN` holds every scope unless granted.
5. Even with a controller at `/api/other`, requests return 403 due to the `deny` fallback.
6. Wrong password returning 401 proves authentication failure differs from authorization denial.
7. Never claim a 404 means “secure”; test real routes that become reachable when authorized.

### 10.7. Build, run, and expected results

In the directory containing `pom.xml`:

~~~bash
mvn validate
mvn test
mvn spring-boot:run
~~~

Maven output varies across Java/JUnit/Maven versions and environments. On localhost:

~~~bash
curl -i http://localhost:8080/api/admin/panel
curl -i -u alice:alice-pass http://localhost:8080/api/admin/panel
curl -i -u admin:admin-pass http://localhost:8080/api/admin/panel
curl -i -u alice:alice-pass http://localhost:8080/api/reports/monthly
~~~

Expected HTTP statuses in order: **401, 403, 200, 200** in this demo configuration; admin JSON contains `area=admin` and user `admin`, and report JSON contains `report=monthly`.

**Use demo credentials on localhost only.** HTTP Basic is Base64, not encryption; over real networks use HTTPS and never leave real passwords/tokens in terminal history or logs.

## 11. Diagnosing common migration errors

| Symptom | Causes to inspect | How to resolve |
| --- | --- | --- |
| `antMatchers` no longer compiles | Legacy DSL shortcut removed from active API | Switch to `requestMatchers` or explicit matchers as needed |
| `mvcMatchers` no longer compiles | Legacy MVC shortcut removed | Use `MvcRequestMatcher`/Builder or `requestMatchers` per version |
| Admin unexpectedly returns 200 for USER | Broad public rule placed before admin | Reorder rules and test that USER gets 403 |
| GET works, yet POST is also public | `HttpMethod.GET` dropped during migration | Restore method-specific matchers and fallback |
| `MvcRequestMatcher` missing introspector | Security config placed in the wrong context | Place MVC/security config and introspector in the right context |
| `requestMatchers(String)` reports ambiguous Servlet | App has multiple Servlet mappings | Pick explicit matchers for each protected Servlet |
| `/app/orders` misses `/orders` rule | Custom servlet path | Use `Builder.servletPath` or exact matcher + integration test |
| `anyRequest().denyAll()` present, yet URL stays open | URL falls outside chain's `securityMatcher` | Add a fallback chain and test chain selection |
| Login after migration returns 404 | Login processing URL outside chain | Fix chain matching and test POST `/login` |
| Status 401 turns into 302 | Authentication entry point/form login changed | Inspect chains, Basic/form config, and `Accept` header |
| Static resources lose security headers | `web.ignoring` used instead of `permitAll` | Prefer `permitAll` and test headers |
| 403 spikes after upgrade | Path semantics, CSRF, method, or dispatcher changed | Compare baseline, versions, and normalized paths |
| Regex matches prefix by mistake | Missing anchors or bad escaping | Write anchored `RegexRequestMatcher` and test boundaries |
| PathPattern API fails to compile | Code copied from a different minor version | Check Javadocs/BOM and use a supported matcher |
| `/admin` and `/admin/` behave differently | Trailing slash semantics changed | Canonicalize URLs and add negative tests |
| 404 interpreted as “blocked” | Controller does not exist; authorization untested | Test real routes and matcher decisions |
| Authorized URL leaks another user's data | Only URL-level role exists, no object check | Enforce ownership/tenant checks in service/method security |

### 11.1. Debugging at the right layer

If **the chain did not match**, inspect `securityMatcher` and `FilterChainProxy` first. If **the request entered the chain but hit the wrong rule**, inspect `requestMatchers` order, HTTP methods, path representation, and authorities. If **the rule is right yet the controller errors**, inspect MVC routing or business logic rather than weakening security to mask another layer's bug.

If a 403 comes from CSRF, renaming `antMatchers` to `requestMatchers` is not the direct cause; inspect `CsrfFilter` and tokens/repositories. If `Authentication` is missing or invalid, a Basic entry point can return 401 before you ever see an authorization 403. Rely on sanitized logs and integration tests without dumping `Authorization` headers or principal credentials.

## 12. Step-by-step safe migration process

### Step 1 — Capture the baseline policy

Inventory every:
- legacy `antMatchers`, `mvcMatchers`, `regexMatchers`;
- matchers in `WebSecurityCustomizer`/`web.ignoring`;
- chain-selection matchers;
- method-specific patterns;
- role/authority/permit/deny rules;
- `servletPath`/`contextPath` and custom dispatchers;
- rules for `/login`, `/logout`, OAuth2 callbacks, Actuator, and static assets;
- custom filters/`AccessDecisionVoter`s.

Do not simply grep one method name and rewrite it with a text regex.

### Step 2 — Lock supported versions

Run `mvn dependency:tree` or Gradle dependency trees to check **Spring Boot, Spring Security Web/Config, Spring Framework, and Micrometer (if present)**. Read Javadocs/references **for those exact versions**. Never pull a PathPattern matcher from a newer release into Security 6.3 without verifying the API.

### Step 3 — Map the HTTP topology

Identify:
- whether Spring MVC is on the classpath;
- single vs multiple `DispatcherServlet`/Servlets;
- context path, servlet path, reverse proxy rewrites;
- MVC path matching strategy;
- `StrictHttpFirewall`/normalization;
- chain matchers and ordering.

With multiple Servlets, specify explicit matchers per region instead of expecting unambiguous auto-selection.

### Step 4 — Choose matchers by semantics

- Simple MVC: `requestMatchers(String, HttpMethod)` typically suffices when verified by tests.
- Strict MVC alignment: `MvcRequestMatcher` with the right `HandlerMappingIntrospector`.
- Temporary Ant compatibility: `AntPathRequestMatcher` where supported, with a plan to retire deprecated APIs.
- PathPattern: only when your version provides the API and matching parsing strategy.
- Regex/custom: explicit matchers when conditions are genuinely special.

Never choose a matcher merely because its class name looks similar to legacy code.

### Step 5 — Order rules and fallbacks

Place:
1. Sensitive endpoints first.
2. Explicit method and authority rules.
3. Specific public endpoints.
4. Explicit fallback: typically `denyAll` or `authenticated` per policy.
5. Fallback `SecurityFilterChain` if the app uses multiple chains.

Never put `/api/** permitAll` ahead of `/api/admin/** hasRole`. Never let new endpoints become open automatically via an overly permissive fallback.

### Step 6 — Write an allow/deny test matrix

| Path and state | Anonymous | User | Admin |
| --- | --- | --- | --- |
| GET `/public` | 200 | 200 | 200 |
| GET `/api/admin/panel` | 401 per Basic demo | 403 | 200 |
| GET `/api/reports/monthly` | 401 | 200 with valid scope | 200 if granted scope |
| GET `/api/other` | Per entry point | 403 via `denyAll` | 403 via `denyAll` |
| GET `/api/administrator` | No implicit admin rights | No implicit admin rights | Only per real rules |
| POST `/api/reports/monthly` | Per auth/CSRF | Per CSRF + method rule | Per CSRF + method rule |

Statuses in this matrix reflect the **demo**, except rows for unpermitted paths. Apps with form login may redirect 302, while APIs using other entry points may return 401 or JSON errors; do not force one HTTP status across every stack.

### Step 7 — Test URL boundaries and Servlet mappings

Test:
- root vs child paths;
- trailing slashes, uppercase/lowercase;
- similar prefixes like `/admin` vs `/administrator`;
- encoded slashes/semicolons/double slashes in an isolated test environment;
- real `contextPath`/`servletPath`;
- GET/POST/DELETE and unexpected HTTP methods;
- forward/error dispatches where required;
- MVC endpoints vs non-MVC servlets.

Never weaken the firewall just to “keep old config working.” Malicious requests may be rejected by the container or firewall before reaching any matcher; understand that behavior rather than blaming every 400/403 on `RequestMatcher`.

### Step 8 — Deploy and observe

After deployment:
- compare 401/403/404/302 rates per route template against baseline;
- verify login/logout and newly introduced paths;
- record releases/versions on dashboards;
- keep rollback ready if authorization unexpectedly opens or blocks traffic;
- do not leave sensitive TRACE logs enabled in production for extended periods;
- never log tokens, passwords, session cookies, or raw `Authorization` headers in logs or traces.

## 13. Misconceptions to avoid

**“`requestMatchers` is always just `antMatchers` renamed.”** False. The string overload may choose matchers based on environment/version; when semantics matter, verify and declare explicitly.

**“`MvcRequestMatcher` works for every Servlet.”** False. It depends on Spring MVC's `HandlerMappingIntrospector` and is unaware of custom servlet or H2 console routes.

**“`securityMatcher` enforces permissions.”** False. It selects a `SecurityFilterChain`; authorization rules live inside the chain.

**“`anyRequest().denyAll()` protects every request in the app.”** True only within that chain's scope. Without a fallback for URLs outside all chains, those URLs can skip Spring Security filters.

**“Bottom rules override top rules.”** False in standard authorization config: the first matching rule wins.

**“Keeping the pattern while dropping the HTTP method is equivalent.”** False. A GET-only rule can turn into an all-method permit rule.

**“`hasRole` and `hasAuthority` are always identical.”** False. `ROLE_ADMIN` differs from literal `ADMIN` and from OAuth2 scope authorities.

**“`permitAll` and `web.ignoring` both mean no login required.”** Both open public resources, yet **filter-chain behavior differs**: `ignoring` bypasses Spring Security filters altogether.

**“GET `/admin` returning 404 proves the admin rule is secure.”** Insufficient. Test real routes, boundary paths, and both authorized and unauthorized principals.

**“`PathPatternRequestMatcher` exists across all Security 6.x releases.”** Never assume; verify the minor version and API.

**“Configuring security matchers prevents IDOR.”** False. URL-level authorization does not replace object/tenant ownership checks in the service layer.

## 14. Hands-on exercises

1. **From `antMatchers` to `requestMatchers`:** Migrate `/admin/** hasRole('ADMIN')` and test anonymous, USER, ADMIN, and `/administrator`. Results must prove the permitted scope did not widen.
2. **Test ordering:** Place `/api/** permitAll` before the admin rule. Test USER calling admin. Reverse the order and re-test. Explain first-match semantics.
3. **Preserve HTTP methods:** Migrate a `GET /reports/**`-only rule; send a mock POST to the same path and verify it is not permitted automatically.
4. **Custom MVC servlet path:** `DispatcherServlet` mapped to `/app`, controller `/orders`. Create `MvcRequestMatcher.Builder(introspector).servletPath("/app")` and test the real URL.
5. **Distinguish `securityMatcher`:** Configure only an `/api/**` chain and confirm `/web/secret` sits outside it; add a deny fallback and re-test.
6. **Ant vs MVC:** With two servlets, test auto-selected vs explicit matchers. Document which routes belong to MVC and which to custom servlets without “fixing” via broad `permitAll`.
7. **Static resources:** Replace `web.ignoring` with `requestMatchers(...).permitAll()` and verify configured security headers.
8. **PathPattern upgrade:** If supported by your version, migrate one path and run full boundary tests. If the class fails to compile, explain the dependency/version mismatch instead of overriding isolated dependencies.
9. **Regex paths:** Protect GET `/api/invoices/[0-9]+` with `RegexRequestMatcher` and test paths with extra characters or missing anchors.
10. **Migration regression:** Run the same request matrix before and after upgrading; if any status differs, pinpoint whether the cause is matcher, entry point, CSRF, filter chain, or MVC mapping.

## 15. Checklist before merging

- [ ] Checked versions of Spring Boot, Spring Security, and Spring MVC.
- [ ] Complete inventory of legacy matchers, chains, and ignoring rules.
- [ ] Identified context path, servlet path, multiple servlets, and proxy rewrites.
- [ ] Selected matchers by real semantics, not merely method names.
- [ ] If using explicit Ant/MVC/PathPattern matchers, verified API availability on target versions.
- [ ] Specific rules placed first; public rules cannot shadow sensitive rules.
- [ ] Preserved method restrictions, authorities, role prefixes, and dispatcher policies.
- [ ] Added fallback authorization rules and fallback chains where required.
- [ ] Login/logout/callback URLs reside inside the chain that handles them.
- [ ] Static resources still receive security headers per policy.
- [ ] Positive and negative tests exist for anonymous/USER/ADMIN.
- [ ] Tests cover root/trailing slash/similar prefixes/encoded paths/HTTP methods.
- [ ] Tested on the real Servlet topology if different from defaults.
- [ ] Neither CSRF nor `HttpFirewall` was relaxed just to pass migration.
- [ ] A lone 404 is not treated as proof of proper authorization.
- [ ] New URLs cannot become open automatically via an overly broad fallback.
- [ ] Per-route 401/403 logs/metrics and a deployment rollback plan are in place.
- [ ] No credentials, tokens, or sessions are logged during diagnostics.

**Summary:** Migrating from `antMatchers` and `mvcMatchers` to `requestMatchers` in Spring Security Servlet is **a change in how requests are selected**, not just a DSL rename. Separate `securityMatcher` (chain-level) from `requestMatchers` (rule-level), pick explicit matchers when Servlet/MVC semantics demand it, preserve ordering and HTTP methods, enforce strict fallbacks, and **prove correctness with negative integration tests** on the exact version you deploy.