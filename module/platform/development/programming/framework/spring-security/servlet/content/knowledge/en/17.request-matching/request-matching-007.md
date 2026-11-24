# AntPathRequestMatcher, MvcRequestMatcher, and Notes for Reading Legacy Configurations in Spring Security Servlet

## 1. Objectives and Scope

When securing a **Spring Security Servlet** application, we often write rules like "GET /api/public is freely accessible", "GET /api/projects/{id} requires login", and "/api/admin requires ROLE_ADMIN". Behind those rules lies an important question: **which requests actually match the declared path pattern and HTTP method?**

Spring Security uses **RequestMatcher** implementations to answer this question. Two names commonly seen when reading legacy code are:

- **AntPathRequestMatcher**: matches paths using Ant-style patterns and can optionally constrain the HTTP method.
- **MvcRequestMatcher**: integrates with how Spring MVC interprets request mappings via **HandlerMappingIntrospector**, especially useful when controllers also use MVC path patterns.

In Spring Security 6 and newer code, you must also distinguish **securityMatcher(...)** which selects a **SecurityFilterChain**, **requestMatchers(...)** which creates authorization rules *inside the chain*, and legacy APIs such as **antMatchers**, **mvcMatchers**, **authorizeRequests**, or **WebSecurityConfigurerAdapter**.

After this lesson, you will be able to:

1. Explain the RequestMatcher contract, the path of a Servlet request, and the meaning of true/false.
2. Compare AntPathRequestMatcher and MvcRequestMatcher by source of semantics, path, method, servlet path, and Spring MVC context.
3. Read Spring Security 5.x configurations using antMatchers/mvcMatchers/antMatcher without confusing filter chain selection with authorization.
4. Write modern configurations with SecurityFilterChain + authorizeHttpRequests + explicit RequestMatchers.
5. Know when HandlerMappingIntrospector is required and why multiple Servlets or multiple SecurityFilterChains change outcomes.
6. Run the **Java 17+ / Spring Boot 3.3.13 / Spring Security 6 / Maven** demo, test with curl, and verify with MockMvc.
7. Avoid common mistakes: overly broad wildcards, misordered rules, mistaking URL queries for paths, confusing 401 with 403, overlooking CSRF, or believing renaming DSL methods preserves identical semantics.

**Scope:** Servlet stack, primarily Spring MVC. WebFlux uses a different matcher and security filter chain mechanism. API recommendations are tied to the example's version branch; when upgrading Spring Security, check APIs and deprecations for the **exact version you run**.

## 2. What Does RequestMatcher Actually Do?

In Spring Security Servlet, **RequestMatcher** is an interface that takes an **HttpServletRequest** and returns whether the request matches a condition.

~~~java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.security.web.util.matcher.RequestMatcher;

// Conceptual signature from the interface:
boolean matches(HttpServletRequest request);
~~~

This is a contract illustration, not a standalone Java file: you cannot place a loose method at the top level. In real code, Spring Security invokes matchers to select a chain or evaluate authorization rules.

**RequestMatcher is not an AuthenticationManager.** Returning matches(request) == true only says the request satisfies a *condition*; it does not prove the user is logged in or authorized.

Example:

~~~text
GET /api/projects/42
   |
   | path/method matcher?
   v
MvcRequestMatcher(GET, "/api/projects/{id}") -> true
   |
   | authorization policy?
   v
authenticated() -> requires valid Authentication
   |
   +-- Not logged in: typically 401 with HTTP Basic
   +-- Valid login: proceeds to MVC controller
~~~

If a matcher for /api/admin returns true, the **hasRole("ADMIN")** rule is what decides the permission requirement. If it does not match, Spring Security can try the next rule or fall into **anyRequest().denyAll()**. Do not assume an unmatched request automatically returns HTTP 404: security may reject it before DispatcherServlet looks up a controller.

### What Can RequestMatcher Inspect?

Various implementations and compositions can inspect:

- Request path.
- HTTP method (GET, POST, PUT...).
- Servlet path or other request properties depending on the matcher.
- Headers, IP, a custom predicate, or compositions with **AndRequestMatcher / OrRequestMatcher / NegatedRequestMatcher**.

This lesson focuses on **AntPathRequestMatcher** and **MvcRequestMatcher**; do not equate every RequestMatcher type with Ant-style pattern matching.

## 3. Two Easily Confused Layers: securityMatcher and requestMatchers

A request must first be assigned to the appropriate **SecurityFilterChain**. Then, inside the selected chain, filters execute authentication and authorization.

~~~text
HTTP Servlet request
        |
        v
DelegatingFilterProxy
        |
        v
FilterChainProxy
        |
        +-- SecurityFilterChain @Order(1)
        |       securityMatcher("/api/**") ?
        |
        +-- SecurityFilterChain @Order(2)
        |       securityMatcher("/**") ?
        |
        v
FIRST matching chain in order
        |
        v
BasicAuthenticationFilter / appropriate filters
        |
        v
AuthorizationFilter
        |
        +-- requestMatchers(GET, "/api/public").permitAll()
        +-- requestMatchers(GET, "/api/admin").hasRole("ADMIN")
        +-- anyRequest().denyAll()
        |
        v
DispatcherServlet / Controller (if allowed)
~~~

| Position | Common API | Meaning |
| --- | --- | --- |
| **Select chain** | http.securityMatcher(...) | Should this chain handle the request? |
| **Select authorization rule** | authorizeHttpRequests(...).requestMatchers(...) | Which rule applies inside the selected chain? |
| **Declare MVC endpoint** | @GetMapping, @PostMapping, @RequestMapping | Which controller/handler receives the request if it reaches MVC? |

**Critical rule:** a request goes through only **the first matching chain** in FilterChainProxy; it does not run every chain. If no chain matches and no other protection exists, the request can pass through **without Spring Security applied**. Therefore, multi-chain configurations must verify coverage and provide an explicit fallback chain when needed.

**securityMatcher("/api/**") does not permit /api/**.** It only selects the chain; authentication/authorization must still be declared inside the chain. Conversely, **requestMatchers("/api/**").permitAll()** is a very broad access-granting rule inside a chain and can expose endpoints if placed ahead of stricter rules.

### Example of Wrong Rule Order

~~~java
// Illustrative snippet: DO NOT put this order into production.
authorize
    .requestMatchers("/api/**").permitAll()
    .requestMatchers("/api/admin").hasRole("ADMIN")
    .anyRequest().denyAll();
~~~

If the first rule already matches /api/admin, the ADMIN rule below is never evaluated. Place specific and sensitive rules before broad wildcards, or avoid permitAll on /api/** unless genuinely required.

This is a fragment inside an authorizeHttpRequests lambda, not a standalone Java class.

## 4. AntPathRequestMatcher: Reading Legacy Code

**AntPathRequestMatcher** lives in package:

~~~text
org.springframework.security.web.util.matcher.AntPathRequestMatcher
~~~

It can be constructed with a path pattern and an optional HTTP method. Example for code on a Spring Security 6 branch compatible with this class:

~~~java
RequestMatcher reportsGet =
    new AntPathRequestMatcher("/api/reports/**", "GET");
~~~

This is a fragment; in a full class you must import RequestMatcher and AntPathRequestMatcher. **GET** is the method constraint, and **/api/reports/\*\*** is the path pattern.

### 4.1. Ant-Style Semantics

Common symbols:

| Pattern | Intent | Caution |
| --- | --- | --- |
| **/api/public** | A specific path | Do not assume trailing-slash/encoded variant handling matches every MVC setup |
| **/api/reports/\*\*** | Sub-paths in Ant-style | Broader than an endpoint expecting a single parameter |
| **/api/reports/* ** | One path segment after /reports/ | `*` does not mean `**` at all positions |
| **/api/** | Broad API scope | Never use permitAll if sensitive endpoints exist |
| **/** | Nearly global scope | Suitable as an intentional fallback chain/rule, not an arbitrary public rule |

In the table above, the space after `*` in **/api/reports/* ** is only to prevent Markdown from misparsing emphasis; the actual pattern in code is **/api/reports/\*** with a single trailing asterisk when matching one segment. Shown clearly in a code block:

~~~text
One segment: /api/reports/*
Many levels: /api/reports/**
~~~

**Do not look only at a pattern and predict all edge cases** such as trailing slashes, empty paths, percent-encoding, semicolons, or path normalization. Those cases also depend on the implementation, HttpFirewall, framework version, and container configuration. Test with real requests on the target stack.

### 4.2. Which Part of HttpServletRequest Does It Match?

With traditional AntPathRequestMatcher, the path is typically derived from **servletPath + pathInfo** on HttpServletRequest. **The query string is not part of the path** used for matching.

~~~text
GET /api/reports/42?download=false
    ^^^^^^^^^^^^^^^  ^^^^^^^^^^^^^
    request path     query string
~~~

A rule for path /api/reports/42 normally does not change its result merely because query parameters differ. If business logic must check owner, reportId, or query parameters, implement **data/business-layer authorization** or a properly designed custom RequestMatcher; you cannot infer resource access permission from path matching alone.

When writing unit tests with MockHttpServletRequest, ensure **servletPath/pathInfo** accurately reflect the path read by the matcher; setting only **requestURI** does not always populate the data the matcher inspects. The testing section shows setting servletPath explicitly.

### 4.3. Is AntPathRequestMatcher the Modern Default Choice?

Do not treat it as the future default. In newer Spring Security lines, Ant-style APIs may be **deprecated and steered toward replacement** by PathPattern-based request matching. Especially when upgrading to versions with API changes, check the Javadoc/migration guide for **that exact version** before copying AntPathRequestMatcher constructors from older articles.

In this lesson, AntPathRequestMatcher is used mainly for **reading/testing legacy configurations**. The new application example uses **MvcRequestMatcher** explicitly to describe MVC endpoints in a Spring Security 6 environment.

## 5. MvcRequestMatcher: Aligning Semantics With Spring MVC

**MvcRequestMatcher** is a RequestMatcher integrated with Spring MVC, using **HandlerMappingIntrospector** to identify requests according to MVC's mapping model.

Full names:

~~~text
org.springframework.security.web.servlet.util.matcher.MvcRequestMatcher
org.springframework.web.servlet.handler.HandlerMappingIntrospector
~~~

Suppose you have a Spring MVC controller:

~~~java
@GetMapping("/api/reports/{reportId}")
public ReportDto show(@PathVariable String reportId) {
    // Fragment: ReportDto and business data are not defined here.
    return reportService.find(reportId);
}
~~~

This is only a fragment illustrating an MVC path variable; do not treat it as standalone compilable code. The path **/api/reports/{reportId}** represents a report route as MVC parses patterns. A corresponding MvcRequestMatcher can be defined:

~~~java
MvcRequestMatcher.Builder mvc =
    new MvcRequestMatcher.Builder(introspector);

RequestMatcher reportGet =
    mvc.pattern(HttpMethod.GET, "/api/reports/{reportId}");
~~~

Here **introspector** is a **HandlerMappingIntrospector** provided in the MVC context. Section 10 contains a complete, compilable SecurityConfig.

### 5.1. Why Is HandlerMappingIntrospector Needed?

Spring MVC can change its route-matching strategy depending on framework version and configuration, such as PathPatternParser and path-handling rules. MvcRequestMatcher relies on information from MVC instead of applying an independent set of Ant rules to every request.

Practical consequences:

- When matching MVC controllers, MvcRequestMatcher gives consistency advantages.
- Do not construct a HandlerMappingIntrospector outside the DispatcherServlet's ApplicationContext and expect mappings to always align.
- In a standard Spring Boot MVC app, a HandlerMappingIntrospector bean is provided by the framework and can be injected into SecurityConfig.
- With multiple DispatcherServlets or non-MVC Servlets, identify which servlet a matcher targets and test routing; never assume one MVC matcher covers the entire web app properly.

### 5.2. Attaching an HTTP Method

MvcRequestMatcher.Builder can construct a matcher for a specific method:

~~~java
RequestMatcher getReport =
    mvc.pattern(HttpMethod.GET, "/api/reports/{reportId}");
~~~

In this case **POST** to the same path does not match the **GET** matcher. Yet **failing to match an authorization rule** does not guarantee HTTP 405: if the request falls into **anyRequest().denyAll()**, security can return 401/403 before MVC handles it and returns Method Not Allowed.

If you want a standard 405 contract for an MVC endpoint, examine the interaction among mapping, authorization, and exception handling rather than expecting RequestMatcher to emit 405 itself.

### 5.3. Servlet Path and Context Path

**Servlet path** is not always the full URL path after the hostname. An app may run under a context path or a non-root DispatcherServlet mapping. **MvcRequestMatcher.Builder.servletPath(...)** lets you specify the servlet path when required.

Example configuration fragment for a DispatcherServlet mapped under a different servlet path:

~~~java
MvcRequestMatcher.Builder mvc =
    new MvcRequestMatcher.Builder(introspector)
        .servletPath("/mvc");

RequestMatcher protectedGet =
    mvc.pattern(HttpMethod.GET, "/api/reports/{reportId}");
~~~

The fragment above **applies only when DispatcherServlet and real mappings use servletPath "/mvc"**. Do not add servletPath("/mvc") to the root-path demo project in section 10, or the root app will fail to match as expected. When deploying under a context path, distinguish contextPath, servletPath, and pathInfo; run MockMvc/integration tests matching the real deployment setup.

**Easy mistake:** MvcRequestMatcher must not be used to infer permission to view a report merely because the route has a {reportId} variable. The matcher only identifies the request; checking "which user owns this report?" belongs in methods/services with proper data-level authorization.

## 6. Direct Comparison of Ant and MVC Matchers

| Criterion | AntPathRequestMatcher | MvcRequestMatcher |
| --- | --- | --- |
| Source of semantics | Ant-style path matching | Spring MVC semantics via HandlerMappingIntrospector |
| Usage context | Reading legacy code, some legacy filters/rules, controlled non-MVC URLs | Securing Spring MVC endpoints in branches supporting this class |
| Path variables | Handles Ant patterns; does not automatically stay in sync with all MVC mappings | Aligns with patterns used in MVC, such as /items/{id} |
| HTTP method | Constructor accepts method as String | Builder supports HttpMethod |
| MVC context | Does not need HandlerMappingIntrospector | Requires matching HandlerMappingIntrospector |
| Servlet path | Relies on Servlet request path parts | Can configure servletPath on builder |
| Query string | Not part of normal path | Not part of normal MVC matcher path |
| Trailing slash, encoding, path parameters | May differ from Spring MVC config | Follows MVC handling, still must be tested |
| Framework upgrades | Check API deprecation and PathPattern replacement per version | Check whether MVC matcher remains recommended in target version |

**Do not build a "guaranteed result table" for every wildcard/Unicode URL by guesswork.** For instance, when a controller uses an MVC path pattern that differs from AntPathMatcher configuration, edge cases around decoded paths, semicolons, or trailing slashes can diverge. Rather than relying on memory from an older version, write regression tests for sensitive routes.

### Same URL, Two Different Matching Concepts

~~~text
Spring MVC mapping: GET /api/reports/{reportId}
Legacy security:     /api/reports/**
Intended rule:       allow authenticated()
Unexpected scope:    may be wider than a single-segment report
~~~

If the controller only defines a single-segment route, an overly broad Ant wildcard can apply that same rule to new routes added under /api/reports/** in the future. Pick narrow matchers and keep a denyAll fallback. If the API truly intends to cover the whole /api/reports/** subtree, document the scope clearly and test every permission group.

## 7. Reading Legacy DSL: antMatchers, mvcMatchers, antMatcher

In Spring Security 5.x / WebSecurityConfigurerAdapter projects, you may encounter:

~~~java
// Legacy configuration fragment; DO NOT use as-is in Spring Security 6.
@Override
protected void configure(HttpSecurity http) throws Exception {
    http.antMatcher("/api/**")
        .authorizeRequests()
        .antMatchers("/api/public").permitAll()
        .antMatchers("/api/admin").hasRole("ADMIN")
        .anyRequest().authenticated();
}
~~~

Similar-looking method names play very different roles:

| Legacy Config | Legacy Meaning | Reading Guide When Migrating to Bean Config |
| --- | --- | --- |
| **http.antMatcher("/api/\*\*")** | Selects scope of HttpSecurity / security chain | **http.securityMatcher(...)** |
| **authorizeRequests().antMatchers(...)** | Applies authorization rule using Ant matcher | **authorizeHttpRequests().requestMatchers(...)** with explicitly chosen matcher/semantics |
| **authorizeRequests().mvcMatchers(...)** | Applies authorization rule using MVC-aware matcher | Create MvcRequestMatcher and pass to **requestMatchers(...)** if supported by version |
| **authorizeRequests()** | Legacy authorization DSL | **authorizeHttpRequests(...)** |
| **WebSecurityConfigurerAdapter** | Class-inheritance configuration style | **@Bean SecurityFilterChain** and related beans |
| **web.ignoring().antMatchers(...)** | Skips Spring Security filters on URLs | Consider **permitAll** first; never blindly bypass all filters |

**Warning:** migrating the DSL is not just renaming methods. For example:

~~~java
// Wrong intent when trying to SELECT a filter chain for /api/**:
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").permitAll());
~~~

This code fragment is not equivalent to the legacy **http.antMatcher("/api/\*\*")**: it **grants access** to API requests matching the pattern inside the current chain, which is completely different from selecting the chain's scope. To keep the chain selector, use **securityMatcher(...)** and declare separate authorization rules inside.

### WebSecurityConfigurerAdapter Is Gone in Spring Security 6

Do not try to import WebSecurityConfigurerAdapter in a Boot 3 / Security 6 project expecting it to compile. Modern configuration defines beans for SecurityFilterChain, UserDetailsService/AuthenticationProvider, PasswordEncoder, and other components as needed.

Keywords like **antMatchers** and **mvcMatchers** in older tutorials may no longer have corresponding DSL overloads in newer versions. Read the Javadoc for your **actual Security release** and choose explicit matchers if there is any doubt about default strategy.

### Is requestMatchers(String...) Always Ant?

**Never assume so.** Overloads of requestMatchers taking path strings can select a matcher based on **classpath, servlet environment, Spring Security version, and configuration**. With Spring MVC on the classpath, some Spring Security branches select an MVC-aware matcher; with multiple servlets, selection can become ambiguous and require explicit configuration.

In this lesson, the application config **does not rely on framework guesswork**: it builds **MvcRequestMatcher.Builder(introspector)** and passes explicit MvcRequestMatcher instances to requestMatchers(...).

## 8. Multiple SecurityFilterChains and @Order: Bugs That Appear Only After Deployment

Suppose a system has:

~~~text
Chain #1 @Order(1) securityMatcher("/api/**")
Chain #2 @Order(2) securityMatcher("/**")
~~~

A GET /api/admin request is handled by chain #1 first. It does **not** fall through to chain #2 simply because an authorization rule inside chain #1 did not match; chain #1 must render its own decision.

**Dangerous bug:** chain #1 has no protective rule for /api/admin, or broadly sets permitAll, while the developer assumed chain #2's hasRole("ADMIN") would protect it. In reality, chain #2 is never reached for that request.

**Another bug:** a chain selector is too narrow, e.g., matching only /api/private/**; a request to /api/private fails to match as the author expected and lacks a sufficiently protective fallback chain. Test base paths, trailing slashes, and all routing-accepted variants.

### Checklist to Distinguish Chain-Selection Matchers From Permission Matchers

When reading a configuration:

1. Find how many **SecurityFilterChain** beans exist.
2. Determine their order via **@Order** and default ordering.
3. Inspect each **securityMatcher(...)** or equivalent chain-selection matcher.
4. Identify which **first** chain receives a given request.
5. Inside that chain, read **authorizeHttpRequests(...)** in declaration order.
6. Find the **first** matching rule and its action: permitAll/authenticated/hasRole/denyAll.
7. Check which authentication filters (formLogin/httpBasic/OAuth2 resource server...) are enabled on this chain.
8. Cross-check MVC handlers to see if matching routes exist, especially with custom servlet paths.
9. If no chain matches, review protection coverage before concluding the request is safe.

These steps matter far more than guessing which method name is "closest to antMatchers".

## 9. Request Matching, Authorization, and HTTP Responses Are Not the Same Thing

A matcher only selects a branch. The final HTTP status depends on authentication, authorization, CSRF, exception handling, Spring MVC, and other filters together.

| Scenario in Section 10 Demo | Typical Result | Reason |
| --- | --- | --- |
| GET /api/public without credentials | 200 | permitAll rule |
| GET /api/projects/42 without credentials | 401 + Basic challenge | authenticated rule not satisfied |
| GET /api/projects/42 with valid learner | 200 | Basic authentication succeeds |
| GET /api/admin with valid learner | 403 | Missing ROLE_ADMIN |
| GET /api/admin with valid admin | 200 | Has required role |
| GET /api/projects/42/extra with valid admin | 403 | Does not match endpoint rule, hits denyAll |
| POST /api/admin with admin and valid CSRF | 403 | GET-only matcher does not match, denyAll |
| POST /api/admin without CSRF token | Possible 403 from CsrfFilter | CSRF may reject before authorization |

**401 vs 403:** HTTP Basic typically sends 401/WWW-Authenticate when unauthenticated; an authenticated user lacking privileges receives 403. However, 403 can also be a CSRF failure. **405** is normally returned by MVC only when the method is unsupported and the request reaches MVC; if security blocks first, do not assume 405.

**Never disable CSRF just to test method rules.** In POST tests, supply a valid token using spring-security-test **with(csrf())** to isolate the authorization branch. For browser apps using sessions/cookies, evaluate CSRF protection seriously; even HTTP Basic credentials can be cached and auto-sent by browsers.

### RequestMatcher Does Not Decide Data Permissions

A matcher for GET /api/projects/{projectId} only says the request matches the expected endpoint shape. It does not know:

- Whether the project belongs to the logged-in user.
- Whether the data is more sensitive than a general role allows.
- Whether the user's access to a specific project was revoked.
- Whether the projectId parameter is valid.

Never use permitAll/authenticated alone to skip ownership checks. Object-level authorization must be designed in the service/domain layer, or use method security backed by trusted data sources.

## 10. Runnable Application: Choosing Explicit MvcRequestMatcher

Demo uses:

- **Java 17+**, **Spring Boot 3.3.13**, **Spring Security 6**, **Maven**.
- A single SecurityFilterChain, avoiding multi-chain ordering confusion while learning matchers.
- GET **/api/public**: public.
- GET **/api/projects/{projectId}**: requires an authenticated user.
- GET **/api/admin**: ROLE_ADMIN only.
- All remaining requests: **denyAll**.
- HTTP Basic on local development, sample BCrypt accounts.
- **MockMvc** testing both MVC matchers and a standalone AntPathRequestMatcher.

Endpoints contain no data-persistence logic so the demo focuses strictly on matching. Accounts are test data, never for production. HTTP Basic transmits username/password in Base64; **HTTPS is required** when carrying real credentials.

### 10.1. Project Structure

~~~text
matcher-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/matcherdemo/
    │   ├── MatcherDemoApplication.java
    │   ├── SecurityConfig.java
    │   └── DemoController.java
    └── test/java/com/example/matcherdemo/
        └── MatchingIntegrationTest.java
~~~

### 10.2. Complete pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>matcher-demo</artifactId>
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

This is a **complete Maven XML file**. Use the Spring Boot parent to manage compatible dependency versions. Do not paste extra build blocks from other tutorials onto the end of pom.xml.

### 10.3. MatcherDemoApplication.java

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

### 10.4. SecurityConfig.java

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
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.servlet.util.matcher.MvcRequestMatcher;
import org.springframework.web.servlet.handler.HandlerMappingIntrospector;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails learner = User.withUsername("learner")
            .password(encoder.encode("learner-pass"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-pass"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(learner, admin);
    }

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http,
            HandlerMappingIntrospector introspector) throws Exception {

        MvcRequestMatcher.Builder mvc =
            new MvcRequestMatcher.Builder(introspector);

        http
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(
                    mvc.pattern(HttpMethod.GET, "/api/public"))
                    .permitAll()
                .requestMatchers(
                    mvc.pattern(HttpMethod.GET,
                        "/api/projects/{projectId}"))
                    .authenticated()
                .requestMatchers(
                    mvc.pattern(HttpMethod.GET, "/api/admin"))
                    .hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable);

        return http.build();
    }
}
~~~

**Why does the demo use MvcRequestMatcher explicitly?**

1. SecurityConfig injects the **HandlerMappingIntrospector** belonging to the Spring MVC app.
2. The builder creates matchers with path templates and HTTP methods for each endpoint.
3. The **/api/projects/{projectId}** rule matches the identical `@GetMapping` template in the controller.
4. **/api/admin** requires ROLE_ADMIN; the admin user is seeded with `roles("ADMIN")`, creating the matching authority.
5. **anyRequest().denyAll()** blocks undeclared paths/methods instead of exposing them through a broad wildcard.
6. **httpBasic** enables straightforward 401/403 testing, and **formLogin disabled** avoids HTML page redirects.
7. **STATELESS** makes clear each demo request authenticates via HTTP Basic; this does not disable CSRF.
8. No custom AuthenticationManager/BasicAuthenticationFilter is needed; Spring Security wires UserDetailsService and PasswordEncoder into the standard username/password flow.

**Version migration note:** the demo targets Spring Security 6.x inside Spring Boot 3.3.13. On newer versions, recommended APIs may change (especially PathPatternRequestMatcher); check compatibility before copying code across major versions.

### 10.5. DemoController.java

~~~java
package com.example.matcherdemo;

import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/api/public")
    public Map<String, String> publicEndpoint() {
        return Map.of("message", "public-ok");
    }

    @GetMapping("/api/projects/{projectId}")
    public Map<String, String> project(
            @PathVariable String projectId,
            Authentication authentication) {

        return Map.of(
            "projectId", projectId,
            "viewer", authentication.getName());
    }

    @GetMapping("/api/admin")
    public Map<String, String> admin() {
        return Map.of("message", "admin-ok");
    }
}
~~~

The controller does **not** try to verify passwords or re-check roles; the filter chain handles that. In a real application with project data, the service must add **object-level authorization** to check whether the user is permitted to view that specific `projectId`.

There are no POST/PUT/DELETE endpoints in the controller; this helps test HTTP method matching and CSRF independently.

## 11. Trying the Application With Maven and curl

From the directory containing pom.xml:

~~~bash
mvn spring-boot:run
~~~

Requires JDK 17+ and Maven. Repository access is needed if dependencies are not cached. By default the demo listens on **http://localhost:8080** unless port configuration is changed.

### 11.1. Public GET

~~~bash
curl -i http://localhost:8080/api/public
~~~

Expect **HTTP 200** and:

~~~json
{"message":"public-ok"}
~~~

### 11.2. Protected Endpoint Without Credentials

~~~bash
curl -i http://localhost:8080/api/projects/42
~~~

Expect **401 Unauthorized** and an HTTP Basic challenge, typically a **WWW-Authenticate: Basic ...** header in the demo setup.

### 11.3. Regular User Viewing a Project

~~~bash
curl -i -u learner:learner-pass \
  http://localhost:8080/api/projects/42
~~~

Expect **200 OK**:

~~~json
{"projectId":"42","viewer":"learner"}
~~~

### 11.4. Query Parameter Is Not Path

~~~bash
curl -i -u learner:learner-pass \
  "http://localhost:8080/api/projects/42?view=full"
~~~

Even with **view=full** in the query string, the matcher for GET /api/projects/{projectId} still matches the path; the controller ignores this query, so the projectId/viewer response stays the same.

### 11.5. Missing ADMIN Role

~~~bash
curl -i -u learner:learner-pass \
  http://localhost:8080/api/admin
~~~

Expect **403 Forbidden**, because username/password are valid yet learner only holds ROLE_USER.

### 11.6. Having ADMIN Role

~~~bash
curl -i -u admin:admin-pass \
  http://localhost:8080/api/admin
~~~

Expect **200 OK** with:

~~~json
{"message":"admin-ok"}
~~~

### 11.7. Wrong Password

~~~bash
curl -i -u learner:incorrect-password \
  http://localhost:8080/api/projects/42
~~~

Expect **401** because authentication fails, distinct from lacking the ADMIN role.

### 11.8. Similar Path That Is Not an Allowed Route

~~~bash
curl -i -u admin:admin-pass \
  http://localhost:8080/api/projects/42/extra
~~~

Expect **403** from **anyRequest().denyAll()** in the chain, not because the user lacks ADMIN privileges. Do not assume MVC returns 404 when security already rejected the request.

**Secret notice:** passwords in these curl commands are demo data only. With real credentials, avoid placing passwords in shell history, scripts, or process listings; always use **HTTPS** over the wire because Basic Base64 does not encrypt secrets.

## 12. MockMvc Testing Across Both Filter Chain and MVC

Create **src/test/java/com/example/matcherdemo/MatchingIntegrationTest.java**:

~~~java
package com.example.matcherdemo;

import static org.hamcrest.Matchers.startsWith;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class MatchingIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicGetNeedsNoLogin() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("public-ok"));
    }

    @Test
    void projectGetWithoutCredentialsIsChallenged() throws Exception {
        mvc.perform(get("/api/projects/42"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                "WWW-Authenticate", startsWith("Basic")));
    }

    @Test
    void mvcPathVariableMatchesValidProjectGet() throws Exception {
        mvc.perform(get("/api/projects/42")
                .with(httpBasic("learner", "learner-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.projectId").value("42"))
            .andExpect(jsonPath("$.viewer").value("learner"));
    }

    @Test
    void queryStringDoesNotChangeEndpointPath() throws Exception {
        mvc.perform(get("/api/projects/42")
                .param("view", "full")
                .with(httpBasic("learner", "learner-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.projectId").value("42"));
    }

    @Test
    void learnerIsForbiddenOnAdmin() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("learner", "learner-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void administratorCanReadAdmin() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("admin-ok"));
    }

    @Test
    void adjacentPathIsNotAllowedByMvcRule() throws Exception {
        mvc.perform(get("/api/projects/42/extra")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void postDoesNotMatchGetOnlyAdminRule() throws Exception {
        mvc.perform(post("/api/admin")
                .with(csrf())
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void legacyAntMatcherChecksServletPathAndHttpMethod() {
        AntPathRequestMatcher legacy =
            new AntPathRequestMatcher("/api/projects/**", "GET");

        MockHttpServletRequest good =
            new MockHttpServletRequest("GET", "/api/projects/42");
        good.setServletPath("/api/projects/42");
        assertTrue(legacy.matches(good));

        MockHttpServletRequest wrongMethod =
            new MockHttpServletRequest("POST", "/api/projects/42");
        wrongMethod.setServletPath("/api/projects/42");
        assertFalse(legacy.matches(wrongMethod));

        MockHttpServletRequest wrongPath =
            new MockHttpServletRequest("GET", "/api/admin");
        wrongPath.setServletPath("/api/admin");
        assertFalse(legacy.matches(wrongPath));
    }
}
~~~

Run:

~~~bash
mvn test
~~~

**What the tests verify:**

1. Public endpoint does not require login.
2. Project URL without credentials receives 401 + Basic challenge.
3. MVC path template accurately matches GET /api/projects/42 for a valid user.
4. Query parameters do not change path matching results.
5. Learner cannot access /api/admin even when authenticated.
6. Admin accesses with proper privileges.
7. Sub-path /api/projects/42/extra is not treated as a single-project template.
8. POST /api/admin with a **valid CSRF token** still misses the GET-only permission and hits denyAll.
9. Legacy AntPathRequestMatcher can be verified separately for path and method; the unit test explicitly sets **servletPath** so the matcher reads accurate input.

**MockMvc here passes through the Spring Security filter chain**, thanks to `@AutoConfigureMockMvc` and `spring-security-test`, so the HTTP Basic tests verify real authentication through the configured system. This is stronger testing than using `@WithMockUser` alone when your goal is testing `UserDetailsService`/`PasswordEncoder` alongside authorization.

### Why Does the POST Test Use with(csrf())?

In this example CSRF is not disabled. If POST /api/admin **lacks** a token, `CsrfFilter` can reject it immediately with 403, making the test "pass 403" without proving the **GET-only matcher** is working. Attaching a valid `with(csrf())` lets the request pass CSRF and reach the authorization rule, so the test reflects the intent of checking the method matcher.

### Why Does the Ant Test Not Only Set requestURI?

Traditional AntPathRequestMatcher uses `servletPath`/`pathInfo`. `MockHttpServletRequest` may need `setServletPath` to populate the matching path portion. In direct tests, set both the URI in the constructor and `servletPath` so you do not mistakenly assume a single Mock value populates full Servlet mapping metadata.

## 13. When Should You Use Which Matcher?

**When reading a Spring Security 5.x project:** if you see AntPathRequestMatcher or antMatchers, first identify whether it is used as a chain selector or authorization rule, then inspect patterns and rule order. Do not automatically "modernize" by replacing everything with MVC matchers without testing effects on servlet paths, wildcards, and encoding.

**When writing a Spring MVC application on a Spring Security 6 branch supporting MvcRequestMatcher:** using explicit MvcRequestMatcher helps protect routes with MVC semantics, especially with path variables. However, it needs the HandlerMappingIntrospector from the right context, and still requires object/service authorization when personal data depends on IDs.

**When an app has non-MVC Servlets:** avoid blindly applying MVC matchers across every Servlet. Identify actual request mappings and pick corresponding matchers. Use non-MVC matchers with explicit methods/paths, or another strategy supported by your framework version.

**When upgrading to newer Spring Security:** do not assume AntPathRequestMatcher or MvcRequestMatcher remains recommended forever. Newer branches steer toward **PathPatternRequestMatcher** and updated builder/path handling. Check migration guides, official deprecations, and post-upgrade tests; never copy Boot 3.3 APIs into another version without checking.

**When an app does not need explicit matchers:** the `requestMatchers(String...)` overload can be convenient, yet when behavior depends on servlet/MVC or a security review demands exact proof, use explicit RequestMatchers or verify the actual implementation for your version. Never claim path strings are always interpreted as Ant across every version.

### Quick Decision Table

| Scenario | Recommended Approach |
| --- | --- |
| MVC controller with path variables, compatible Spring Security 6 | Consider MvcRequestMatcher + HandlerMappingIntrospector |
| Fixing bugs in legacy Ant rules before upgrading | Understand Ant semantics and add regression tests first |
| Multiple servlets / DispatcherServlets | Identify servletPath, context, and chain matchers clearly |
| Multiple SecurityFilterChains | Design securityMatcher + @Order + dedicated fallback chain |
| Rules with many wildcards | Audit granted scope and order, add denyAll |
| Resource ID in path | Route matcher + object-level authorization in service |
| Major Spring Security upgrade | Consult target version's migration guide/Javadoc and test |

## 14. Common Mistakes When Migrating Legacy Configurations

### Mistake 1 — Converting http.antMatcher into requestMatchers(...).permitAll

Semantically wrong. `antMatcher` on `HttpSecurity` previously selected the **chain scope**. `permitAll` inside `authorizeHttpRequests` **grants access** to matching requests. Use `securityMatcher` to select the chain, then write separate authorization rules.

### Mistake 2 — Thinking antMatchers and mvcMatchers Differ Only in Name

Wrong. Ant and MVC matchers can behave differently on special path cases, servlet mappings, encoded paths, and trailing slashes. Never upgrade via string find-and-replace without tests.

### Mistake 3 — Placing a Wildcard permitAll Before an ADMIN Rule

For example, `permitAll("/api/**")` before `hasRole("ADMIN")` can expose `/api/admin`. The first matching rule normally decides authorization; use narrow patterns and a denyAll fallback.

### Mistake 4 — Believing a Second SecurityFilterChain Adds Rules Onto the First Chain

FilterChainProxy picks the **first** matching chain. Chains are not stacked like independent middleware. Verify `@Order` and `securityMatcher`.

### Mistake 5 — Using a GET Matcher and Expecting 405 Automatically

Failing to match an authorization rule can lead to 401/403. 405 is MVC mapping behavior only when the request reaches MVC. Test the actual component responsible.

### Mistake 6 — Confusing Query Strings With URL Paths

Query parameters are not paths. A security rule for `/api/projects/{id}` does not check which user owns a project, and must never rely on query strings to decide ownership unless governed by a dedicated policy.

### Mistake 7 — Forgetting Servlet Path and Context Path

A matcher configured for a root MVC app may break when DispatcherServlet is mapped at a different servlet path. Never grab full URLs and compare with ad-hoc string equals; configure and test on the real topology.

### Mistake 8 — Injecting the Wrong HandlerMappingIntrospector

MvcRequestMatcher needs to see the right MVC application context. In apps with split contexts or multiple servlets, configure appropriately; run integration tests rather than constructing a standalone matcher lacking MVC handler mappings.

### Mistake 9 — Using @WithMockUser and Concluding BasicAuthenticationFilter Works

`@WithMockUser` creates a mock Authentication in tests. It helps test authorization, but does not prove usernames/passwords are looked up via UserDetailsService. To test the full flow, run real HTTP Basic or form login tests.

### Mistake 10 — Testing POST Without CSRF and Claiming the Method Rule Was Verified

A POST returning 403 may come from `CsrfFilter`. If your goal is testing HTTP method matchers, send a valid CSRF token in MockMvc, or unit-test `RequestMatcher` directly with `MockHttpServletRequest`.

### Mistake 11 — Neglecting Regions Matching No Chain

If no SecurityFilterChain covers a request and no other protection exists, the request may proceed outside Spring Security. Create an explicit fallback chain and test unexpected URLs.

### Mistake 12 — Treating securityMatcher("/**") as Sufficient Security

`securityMatcher("/**")` only selects the chain. You still need `AuthenticationProvider`, `authorizeHttpRequests`, CSRF/session policies, and specific rules. A matching matcher does not block access itself.

### Mistake 13 — Treating Matchers as User-Resource Ownership Checks

Even if `/api/projects/42` matches the pattern, whether the user may view project 42 depends on business logic. Never omit object-level authorization.

### Mistake 14 — Carrying AntPathRequestMatcher Code Into a New Major Version Unchecked

The API may be deprecated or changed. Choose the matching solution supported by the target framework version, check the migration guide, and run the full security regression test suite.

## 15. Workflow for Reading Legacy Configs When Taking Over a Project

Do not start editing the moment you see `antMatchers`. Walk through step by step:

1. **Record actual versions**: Spring Security, Spring Framework, Boot, and Servlet container; do not use syntax from another version.
2. **List configuration beans**: SecurityFilterChain, legacy WebSecurityConfigurerAdapter, WebSecurityCustomizer, and auto-registered filters.
3. **Identify dispatchers**: does the app run at root context or a context path; are there multiple DispatcherServlets or non-MVC Servlets?
4. **Identify chain selection**: `antMatcher`/`securityMatcher` and `@Order`; which requests enter which chain?
5. **Separate authentication from authorization**: form login, Basic, Bearer, session/CSRF; do rules only check roles or is method security also used?
6. **Read permission rules in order**: permitAll/authenticated/hasRole/hasAuthority/denyAll; spot broad shadowing wildcards.
7. **Cross-check controller mappings**: `@GetMapping`, `@PostMapping`, path variables, and methods; do not rely solely on comments.
8. **Analyze edge cases**: base path, trailing slashes, encoded characters, semicolon path parameters, query strings, method mismatches.
9. **Write tests before changing matchers**: both allowed and denied cases, especially negative tests.
10. **Choose explicit matchers when needed**: Ant in the current version, MVC + introspector, or PathPattern on compatible newer lines.
11. **Upgrade per migration guide**: update code to compile, then compare HTTP behavior before and after.
12. **Analyze changed statuses**: 401/403/404/405 can stem from filter ordering rather than controllers.
13. **Account for CSRF when methods change**: never disable globally just to test an endpoint.
14. **Check default deny / fallback chain**: requests matching no permission rule or chain must never become public accidentally.
15. **Audit sensitive info**: never log Authorization headers, CSRF tokens, passwords, or Session IDs in tests or production debugging.

**Review principle:** changing from `antMatchers` to `requestMatchers` must prove *equivalent protection scope* or document why the scope changed, not merely prove it compiles.

## 16. Practice Exercises With Answers

### Exercise A — Selecting Chain or Selecting Permission?

Compare these two configurations:

~~~java
http.securityMatcher("/api/**");
~~~

~~~java
authorize.requestMatchers("/api/**").permitAll();
~~~

Are they equivalent?

**Answer:** No. The first selects a chain's scope; the second grants permitAll to the pattern inside a chain. Confusing them can make `/api/admin` public.

### Exercise B — GET-Only Rule

A matcher is configured for `GET /api/admin`, and an admin user sends `POST /api/admin`. Does the matcher return true? Must the response necessarily be 405?

**Answer:** The method does not match, so the GET-only matcher returns false. The response does not have to be 405: CSRF, authorization denyAll, or another handler can act before MVC.

### Exercise C — ROLE_ Prefix

A user is declared with `roles("ADMIN")`. Which authority does `hasRole("ADMIN")` check under default config?

**Answer:** `ROLE_ADMIN`. If you use `authorities("ADMIN")`, no prefix is added automatically; you may need `hasAuthority("ADMIN")` depending on design.

### Exercise D — Overly Broad /api/reports/**

The controller only has `GET /api/reports/{id}`; does permitting all of `/api/reports/**` always match requirements?

**Answer:** Not necessarily. Broad Ant wildcards can include sub-paths beyond a single-segment route; if new routes are added later, the rule may over-grant access. Pick a matcher matching the endpoint/intent and add negative-path tests.

### Exercise E — Query Parameter

Does `GET /api/projects/42?view=full` differ for the path matcher of `GET /api/projects/42`?

**Answer:** Query strings are normally not part of the path compared by Ant/MVC path matchers. However, permission to view project 42 still needs service-layer checks against real data.

### Exercise F — Two Chains

Chain #1 matches `/api/**`, and Chain #2 matches `/**` with an ADMIN rule. If Chain #1 receives `/api/admin`, does Chain #2 automatically check the role afterward?

**Answer:** No. Only the first matching chain runs, and protective rules must exist inside it.

### Exercise G — @WithMockUser vs. HTTP Basic

`@WithMockUser(roles="ADMIN")` makes a `GET /api/admin` test pass. Does that prove BCrypt PasswordEncoder and InMemoryUserDetailsManager are wired properly?

**Answer:** Not yet. `@WithMockUser` injects a mock Authentication; to test the credential flow, use `httpBasic("admin", "admin-pass")` through MockMvc.

### Exercise H — Custom Servlet Path

An MVC app changes DispatcherServlet `servletPath` from root to `/mvc`. Should you keep all `MvcRequestMatcher` builders unchanged without testing?

**Answer:** No. Inspect servlet path, context path, HandlerMappingIntrospector, and matcher constructors/builders. Configure `servletPath` if appropriate, then test real URLs.

### Exercise I — CSRF Blocking POST Tests

`POST /api/admin` returns 403 without sending CSRF. Can you conclude the GET-only rule blocked it?

**Answer:** Not yet. `CsrfFilter` can return 403 first. Attach a valid CSRF token to isolate method/authorization checks, or test the matcher directly.

### Exercise K — Upgrading APIs

You see a legacy project using `WebSecurityConfigurerAdapter`, `antMatchers`, and `AntPathRequestMatcher`. Should you replace everything with string `requestMatchers` before writing tests?

**Answer:** No. Record versions, chain selection, servlet context, and rule order, write regression tests, choose matchers suited to the target version, and verify access permissions did not change unintentionally.

## 17. Checklist When Applying RequestMatcher

- [ ] Clearly identified **chain-selection matcher** vs. **authorization-rule matcher**.
- [ ] Identified the exact Spring Security version before choosing Ant, MVC, or PathPattern matchers.
- [ ] Distinguished AntPathRequestMatcher and MvcRequestMatcher by source of semantics.
- [ ] If using MVC matchers, verified HandlerMappingIntrospector belongs to the right MVC context.
- [ ] Constrained HTTP methods where they are part of the API contract.
- [ ] Verified context path, servlet path, and multiple servlets when present.
- [ ] Never treated query strings as paths or used route matching in place of object-level authorization.
- [ ] Checked `securityMatcher` + `@Order` ordering in multi-chain applications.
- [ ] Verified the first matching rule does not grant overly broad `permitAll`.
- [ ] Included `denyAll` fallback or equivalent protection strategy so no URL is left exposed.
- [ ] Distinguished 401/403 from security vs. 404/405 from MVC.
- [ ] GET and POST tests handle CSRF properly to draw accurate conclusions.
- [ ] Sensitive endpoints have pass/fail tests with authorized and unauthorized roles.
- [ ] Tested wildcards, path variables, similar URLs, wrong methods, and query strings.
- [ ] When migrating `antMatchers`/`mvcMatchers`/`WebSecurityConfigurerAdapter`, verified security behavior rather than compilation alone.
- [ ] Avoided bypassing the Spring Security filter chain with `web.ignoring` unless consequences are fully understood.
- [ ] Maintained regression tests to re-run whenever upgrading Spring Security or the Servlet container.

**Conclusion:** **AntPathRequestMatcher** and **MvcRequestMatcher** both implement RequestMatcher, yet should never be treated as unconditionally interchangeable. Ant matchers carry Ant-style semantics common in legacy projects; MVC matchers use HandlerMappingIntrospector to align more closely with Spring MVC request mappings. When reading legacy configs, the essential skill is distinguishing **http.antMatcher/securityMatcher** (chain selection) from **antMatchers/mvcMatchers/requestMatchers** inside authorization (rule selection). Use explicit matchers when semantics matter, maintain **deny-by-default**, and prove with MockMvc both what is permitted and what is denied.
