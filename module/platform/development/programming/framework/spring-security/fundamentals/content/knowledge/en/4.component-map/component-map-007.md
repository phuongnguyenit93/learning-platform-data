# SecurityFilterChain and SecurityWebFilterChain at the Web Application Boundary

> **Focus:** Spring Security intercepts the processing flow **before a request reaches a controller/handler**. In **Servlet/Spring MVC** applications, the unit of configuration is `SecurityFilterChain` composed of Servlet `Filter`s, selected by `FilterChainProxy`. In **Spring WebFlux**, the corresponding unit is `SecurityWebFilterChain` composed of reactive `WebFilter`s, selected by `WebFilterChainProxy`. These two chain types serve two different web models; never carry configuration or thread assumptions from one model into the other.

This lesson is scoped to the **HTTP boundary of a web application**: where chains are attached, how requests are matched and processed, how to configure multiple chains, differences between Servlet and WebFlux, and how to test them properly. Do not equate request-level protection rules with per-resource/business authorization inside services.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Diagram a request's path through `DelegatingFilterProxy` → `FilterChainProxy` → `SecurityFilterChain` in Servlet and through `WebFilterChainProxy` → `SecurityWebFilterChain` in WebFlux.
2. Distinguish `HttpSecurity`/**`ServerHttpSecurity`** (configuration builders) from the chain produced by `build()` (the runtime configuration).
3. Distinguish **selecting a chain** (`securityMatcher`) from **selecting an authorization rule inside a chain** (`requestMatchers` or `pathMatchers`).
4. Order multiple chains with `@Order`, ensuring only the **first matching chain** is used, with a fallback protecting the rest.
5. Explain filter groups for authentication, authorization, CSRF, security headers, `SecurityContext`, and the difference between `ThreadLocal` and Reactor Context.
6. Build two standalone Spring MVC and WebFlux examples in Java 17+ that test `200`, `401`, `403`, HTTP method rules, and CSRF.
7. Identify bugs caused by misconfigured matchers, requests leaking outside all chains, confusing authorization filters with business logic, or placing custom filters at the wrong position.

## 2. A Shared Conceptual Framework

Both models follow the same sequence:

```text
HTTP request
    |
    v
Web framework receives request
    |
    v
Spring Security selects matching security chain
    |
    +--> Protective filters: context, authentication,
    |    exploit protection, authorization, ...
    |
    +--> If missing credentials or insufficient permission:
    |        return challenge/error; handler may never run
    |
    v
Controller / handler / router function
    |
    v
Service / domain / repository (check resource and business permissions)
    |
    v
HTTP response flows back through the processing chain
```

**This is the security "boundary" for web requests**, because filters can block requests before controller code executes. Not all requests pass through the exact same filters: the active chain depends on application type, bean configuration, matchers, and authentication mechanisms.

Quick comparison table:

| Aspect | Servlet / Spring MVC | Reactive / Spring WebFlux |
| --- | --- | --- |
| HTTP abstraction | `HttpServletRequest`, `HttpServletResponse` | `ServerWebExchange` |
| Web framework filter unit | Servlet `Filter` + `FilterChain` | Reactive `WebFilter` + `WebFilterChain` |
| Spring Security entry point | `DelegatingFilterProxy` forwarding to `FilterChainProxy` | `WebFilterChainProxy` in the WebFilter chain |
| Selected chain | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Builder | `HttpSecurity` | `ServerHttpSecurity` |
| Request rules | `authorizeHttpRequests` + `requestMatchers` | `authorizeExchange` + `pathMatchers` |
| Chain selection | `http.securityMatcher(...)` | `http.securityMatcher(ServerWebExchangeMatcher)` |
| Matching | `RequestMatcher` on Servlet request | `ServerWebExchangeMatcher` on exchange |
| Authentication | Servlet authentication filters/manager | Reactive authentication web filters/manager |
| Authorization | e.g. `AuthorizationFilter` | e.g. `AuthorizationWebFilter` |
| Current context | `SecurityContextHolder` (typically ThreadLocal) | `ReactiveSecurityContextHolder` (Reactor Context) |
| Output of `build()` | `SecurityFilterChain` | `SecurityWebFilterChain` |
| HTTP testing | `MockMvc` + Spring Security Test | `WebTestClient` + Spring Security Test |

**Similar names do not mean the two interfaces are directly interchangeable.** A Servlet `Filter` has signature `doFilter(request, response, chain)` and follows the servlet dispatch/thread model. A reactive `WebFilter` has signature `Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain)`, representing an asynchronous non-blocking pipeline. The two cannot be mixed like ordinary Java filter classes.

## 3. SecurityFilterChain in Servlet: Where Does a Request Go?

### 3.1. Actual Diagram

```text
Servlet container (e.g. Tomcat)
  |
  +-- Servlet FilterChain
        |
        +-- DelegatingFilterProxy
              | looks up Spring Bean named springSecurityFilterChain
              v
           FilterChainProxy
              |
              +-- picks first SecurityFilterChain whose matcher matches
              |      (A) /api/**  -> filters for API
              |      (B) /**      -> fallback filters
              |
              +-- Filter 1: security context / exploit protections ...
              +-- Filter 2: authentication, ...
              +-- Filter 3: authorization, ...
              |
              +-- Permitted to continue
                    |
                    v
               DispatcherServlet
                    |
                    v
               HandlerMapping -> Controller
```

`DelegatingFilterProxy` bridges the filter lifecycle managed by the Servlet container and beans inside Spring's `ApplicationContext`. The `springSecurityFilterChain` bean is typically `FilterChainProxy`, which is itself a Servlet `Filter`. It selects exactly one `SecurityFilterChain` for a request and invokes that chain's filters in the framework-established order.

Key takeaways:

- `FilterChainProxy` is the **chain dispatcher**; `SecurityFilterChain` is a **concrete set of filters** paired with a matcher. A `SecurityFilterChain` is neither an HTTP endpoint nor a controller.
- One `FilterChainProxy` can manage multiple `SecurityFilterChain`s; only the **first matching chain** is used. Subsequent chains **do not layer** additional protection on top of an earlier chain.
- If **no chain matches**, the request is not governed by Spring Security through those chains (even though other Servlet filters may exist). Never set `securityMatcher("/api/**")` on your sole chain and assume all other URLs are blocked automatically.
- `FilterChainProxy` performs foundational tasks such as applying `HttpFirewall` and clearing `SecurityContext` in Servlet execution. Do not bypass this mechanism by registering security filters haphazardly.
- `HttpSecurity` is a **builder** used at bean initialization; `http.build()` produces the filter chain configuration. Never confuse it with a per-request execution handler.

### 3.2. Authentication and Authorization in the Chain

A typical flow places filter groups in their proper positions:

```text
HTTP request
    |
    +-- SecurityContextHolderFilter (reads context / sets access strategy)
    +-- CsrfFilter (validates tokens on CSRF-protected requests)
    +-- authentication mechanism (e.g. BasicAuthenticationFilter)
    +-- AnonymousAuthenticationFilter (if no authentication present)
    +-- ExceptionTranslationFilter (handles security exceptions)
    +-- AuthorizationFilter (enforces request authorization)
    v
DispatcherServlet
```

This is a **responsibility illustration**, not a complete or immutable filter list for every version/configuration. A chain may add or omit filters (login, session, bearer token, remember-me, logout, OAuth2, headers...). Filter ordering matters, especially when inserting custom filters.

If an anonymous caller hits an endpoint requiring `authenticated`, they typically receive `401` or a redirect to login depending on `AuthenticationEntryPoint`. If an authenticated user lacks sufficient authorities, they typically receive `403`. Verify actual behavior because entry points, request caches, and other settings can alter the response.

### 3.3. Three Easily Confused Matching Scopes

```java
@Bean
@Order(1)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**") // 1. Which requests does this chain apply to?
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/report")
                .hasAuthority("REPORT_READ") // 2. Rule inside the chain
            .anyRequest().denyAll()           // 3. Remaining requests OF this chain
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

- `securityMatcher("/api/**")` selects the **scope of the entire chain**, not an endpoint rule.
- `requestMatchers(HttpMethod.GET, "/api/report")` selects a rule once a request **has already entered that chain**.
- `anyRequest().denyAll()` only "catches" remaining requests that matched this chain; it has no effect on `GET /other` if no chain matches `/other`.
- Specific rules must appear before general rules. Placing `/api/**.permitAll()` first prevents later restrictive rules from ever being evaluated.
- `securityMatcher` and `requestMatchers` may use different matcher implementations depending on MVC setup, multiple servlets, or configuration. Verify path semantics, HTTP methods, servlet paths, URL encoding, trailing slashes, and framework version rather than guessing from method names.

## 4. SecurityWebFilterChain in WebFlux: Same Goal, Different Mechanism

### 4.1. WebFlux Diagram

```text
Reactive server (e.g. Reactor Netty)
   |
   v
Spring WebFlux HTTP handler + WebFilter chain
   |
   v
WebFilterChainProxy
   |
   +-- Picks first SecurityWebFilterChain whose matcher matches
   |      (A) /api/** -> reactive API filters
   |      (B) all remaining requests -> fallback
   |
   +-- ReactorContextWebFilter / context integration
   +-- AuthenticationWebFilter (depending on mechanism)
   +-- CsrfWebFilter (if enabled)
   +-- AuthorizationWebFilter
   |
   v
DispatcherHandler -> annotated controller / RouterFunction
   |
   v
Mono / Flux, reactive service
```

A `SecurityWebFilterChain` consists of reactive `WebFilter`s. `ServerHttpSecurity` configures rules, and `build()` creates the chain; `WebFilterChainProxy` selects **one** chain via `ServerWebExchangeMatcher`. Reactive filters participate in a pipeline where requests/responses are processed asynchronously.

Critical difference: never use `ThreadLocal`-based `SecurityContextHolder` as a trusted identity source in reactive logic. A WebFlux request can switch threads during processing. Spring Security uses `ReactiveSecurityContextHolder` inside the **Reactor Context**, and publishers in that execution stream can read that context. Being reactive does not automatically create object-level authorization; services still need dedicated owner/tenant/ACL policies.

A small example of reading identity inside a publisher:

```java
// Illustrative snippet in a reactive service with Spring Security;
// imports: reactor.core.publisher.Mono,
// org.springframework.security.core.context.ReactiveSecurityContextHolder,
// org.springframework.security.core.context.SecurityContext.
Mono<String> currentName = ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .map(authentication -> authentication.getName());
```

If there is no security context, the publisher may emit no value. When an endpoint requires login, enforce `authenticated()` at the boundary; never treat `Mono.empty()` as a default user. Propagating context across schedulers and custom publishers must preserve the Reactor Context; never call `block()` on an event loop just to "read the principal".

### 4.2. Corresponding WebFlux Configuration

```java
@Bean
@Order(1)
SecurityWebFilterChain api(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            new PathPatternParserServerWebExchangeMatcher("/api/**"))
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers(HttpMethod.GET, "/api/report")
                .hasAuthority("REPORT_READ")
            .anyExchange().denyAll())
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

In WebFlux:

- `securityMatcher(...)` takes a `ServerWebExchangeMatcher` to select the **chain**.
- `authorizeExchange(...)` sets rules for requests that entered the chain; `pathMatchers(...)` matches paths/HTTP methods within that scope.
- `anyExchange().denyAll()` closes remaining paths **within the current chain**, without protecting requests that fall outside all chains.
- Multiple `SecurityWebFilterChain`s also require `@Order` and a sufficiently broad fallback.
- `@EnableWebFluxSecurity` enables WebFlux Security support in Java configuration when defining explicit chains.

## 5. Why First-Match Chain Priority and Fallbacks Matter

Suppose there are three requests:

```text
GET  /api/hello
GET  /profile
POST /api/tasks
```

And configuration:

```text
@Order(1) API Chain:
    match /api/**
    GET /api/hello -> API_READ
    POST /api/tasks -> API_WRITE
    other /api/** -> denyAll

FALLBACK Chain:
    match all URLs
    GET /public -> permitAll
    GET /profile -> authenticated
    other -> denyAll
```

| Request | Selected chain | Rule inside |
| --- | --- | --- |
| `GET /api/hello` | API | Requires `API_READ` |
| `POST /api/tasks` | API | Requires `API_WRITE` plus HTTP protections like CSRF when applicable |
| `DELETE /api/hello` | API | `denyAll`, since other methods are not permitted |
| `GET /profile` | FALLBACK | Requires `authenticated` |
| `GET /public` | FALLBACK | Public |
| `GET /unknown` | FALLBACK | `denyAll` |

**Pitfall 1: API chain does not match, and there is no fallback?** If you only define an API chain with `securityMatcher("/api/**")` and no fallback chain, paths outside `/api/**` may receive no Spring Security protection at all. Calling `anyRequest().denyAll()` inside the API chain cannot close that gap.

**Pitfall 2: Does the chain with stricter roles win?** False. Chains are selected by **bean order and matcher**, and only then is the chosen chain's policy evaluated. Roles/authorities are never used to pick a "more appropriate" chain.

**Pitfall 3: Does the fallback automatically apply its filters to the API chain?** No. Once the API chain matches, the fallback does not run. To share consistent HTTP security headers, session settings, or CSRF rules, configure each chain explicitly or reuse controlled shared configuration.

**Pitfall 4: Does `permitAll` equal "bypass all of Spring Security"?** No. `permitAll` only allows the request at the chain's authorization step; other filters in that chain still run. Skipping the filter chain entirely is a different operation that drops protections such as security headers/CSRF depending on configuration.

## 6. Demo A: Spring MVC / Servlet with Two SecurityFilterChains

The following demo pins Spring Boot **3.5.16** (Java 17+, Spring Security 6.5.x from the Spring Boot BOM) so the code is reproducible. **3.5.16 is the final release of the 3.5 line under OSS support**; when starting a new production project in 2026, choose Spring Boot 4.x/a supported branch and verify current APIs and patches. Use sample accounts and passwords strictly locally/in tests.

### 6.1. Structure

```text
servlet-chain-demo/
├── pom.xml
└── src/
    ├── main/java/demo/servlet/ServletChainApplication.java
    └── test/java/demo/servlet/ServletChainTests.java
```

**`pom.xml`:**

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
    <artifactId>servlet-chain-demo</artifactId>
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
```

### 6.2. Complete Java Code

Create `src/main/java/demo/servlet/ServletChainApplication.java`:

```java
package demo.servlet;

import jakarta.servlet.DispatcherType;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@EnableWebSecurity
public class ServletChainApplication {
    public static void main(String[] args) {
        SpringApplication.run(ServletChainApplication.class, args);
    }

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/hello")
                    .hasAuthority("API_READ")
                .requestMatchers(HttpMethod.POST, "/api/tasks")
                    .hasAuthority("API_WRITE")
                .requestMatchers(HttpMethod.GET, "/api/admin")
                    .hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            // CSRF remains enabled; POST requires a token if within CSRF scope.
            .build();
    }

    @Bean
    SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                // Allow only container error dispatches; do not expose client endpoints.
                .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/profile").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("demo-pass"))
                .authorities("API_READ", "ROLE_USER").build(),
            User.withUsername("writer")
                .password(encoder.encode("demo-pass"))
                .authorities("API_READ", "API_WRITE").build(),
            User.withUsername("admin")
                .password(encoder.encode("demo-pass"))
                .roles("ADMIN").build()
        );
    }
}

@RestController
class ServletRoutes {
    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/profile")
    String profile(Authentication authentication) {
        return "profile:" + authentication.getName();
    }

    @GetMapping("/api/hello")
    String hello(Authentication authentication) {
        return "api:" + authentication.getName();
    }

    @PostMapping("/api/tasks")
    String createTask(Authentication authentication) {
        // Illustrates action permission. No database write in this demo.
        return "created-by-" + authentication.getName();
    }

    @GetMapping("/api/admin")
    String apiAdmin() {
        return "admin";
    }
}
```

**Behavior breakdown:**

- `apiChain` has `@Order(1)` and `securityMatcher("/api/**")`, so all API requests enter here first; `fallbackChain` matches all remaining paths. Only one chain is chosen.
- Under API, `GET /api/hello` requires `API_READ`, `POST /api/tasks` requires `API_WRITE`, `GET /api/admin` requires `ROLE_ADMIN` per `hasRole("ADMIN")`; unlisted methods/paths are denied.
- In fallback, `GET /public` is public yet still passes through the filter chain; `GET /profile` requires authentication. URLs without explicit rules are denied.
- `PasswordEncoder` and in-memory users with credentials are **strictly for testing**; never use sample passwords or this configuration in production. `httpBasic` requires HTTPS in environments with real traffic.
- Both chains keep CSRF protection enabled by default in Spring Security Servlet. `POST /api/tasks` requires both a valid CSRF token and `API_WRITE` in this example. CSRF is checked in a filter before the handler runs, so the status code can be `403` even when the user holds `API_WRITE`.

### 6.3. Testing with MockMvc

Create `src/test/java/demo/servlet/ServletChainTests.java`:

```java
package demo.servlet;

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
class ServletChainTests {
    @Autowired
    MockMvc mvc;

    @Test
    void chainSelectionAndAuthorization() throws Exception {
        // Fallback public: no credentials needed.
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));

        // API: anonymous receives HTTP Basic challenge.
        mvc.perform(get("/api/hello"))
            .andExpect(status().isUnauthorized());

        // API_READ for Alice.
        mvc.perform(get("/api/hello").with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("api:alice"));

        // Admin has ROLE_ADMIN but lacks API_READ.
        mvc.perform(get("/api/hello").with(httpBasic("admin", "demo-pass")))
            .andExpect(status().isForbidden());

        // Admin API route uses role, not API_READ permission.
        mvc.perform(get("/api/admin").with(httpBasic("admin", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin"));

        mvc.perform(get("/api/admin").with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isForbidden());

        // Fallback also protects /profile.
        mvc.perform(get("/profile"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/profile").with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("profile:alice"));

        // Valid permission, yet POST missing CSRF token is still blocked.
        mvc.perform(post("/api/tasks").with(httpBasic("writer", "demo-pass")))
            .andExpect(status().isForbidden());

        // Has CSRF, yet Alice lacks API_WRITE.
        mvc.perform(post("/api/tasks")
                .with(httpBasic("alice", "demo-pass")).with(csrf()))
            .andExpect(status().isForbidden());

        // Valid credentials + valid authority + valid CSRF -> succeeds.
        mvc.perform(post("/api/tasks")
                .with(httpBasic("writer", "demo-pass")).with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("created-by-writer"));

        // /api/hello forbids POST even though GET on the same path is allowed.
        mvc.perform(post("/api/hello")
                .with(httpBasic("writer", "demo-pass")).with(csrf()))
            .andExpect(status().isForbidden());

        // Undeclared API path and non-API path are both denied.
        mvc.perform(get("/api/unknown")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isForbidden());
        mvc.perform(get("/unknown")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isForbidden());
    }
}
```

This is an integration test running through Spring MVC and the filter chain attached to `MockMvc`. `httpBasic("alice", "demo-pass")` builds a Basic header so the framework verifies via the real `UserDetailsService` in the test context; `csrf()` provides a valid test CSRF token. Tests that only inject a mock principal via `user(...)`/`@WithMockUser` verify rules without verifying real passwords.

### 6.4. Running and Manual Verification

Requires JDK 17+ and Maven compatible with Spring Boot 3.5; in the project directory:

```bash
mvn test
mvn spring-boot:run
```

In another terminal (on Windows PowerShell 5.1, use `curl.exe`):

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/api/hello
curl -i -u alice:demo-pass http://localhost:8080/api/hello
curl -i -u admin:demo-pass http://localhost:8080/api/admin
curl -i -u alice:demo-pass http://localhost:8080/profile
```

Expected responses are `200`, `401`, `200` with body `api:alice`, `200` with body `admin`, and `200` with body `profile:alice` respectively. The curl commands above use plain HTTP **strictly for local machines**: HTTP Basic does not encrypt passwords; real environments must configure HTTPS. Sending `POST` with curl requires fetching/sending the CSRF token per session/configuration, so the example uses `MockMvc + csrf()` to prove both conditions in tests.

## 7. Demo B: Spring WebFlux with SecurityWebFilterChain

This demo is a **standalone Maven project**—do not mix `spring-boot-starter-web` from Demo A into the same application. With both `web` and `webflux` starters present, Spring Boot may choose Servlet as the default application type; to study `SecurityWebFilterChain` properly, use `spring-boot-starter-webflux` alone. Java 17, Boot 3.5.16, and Spring Security 6.5.x match Demo A.

### 7.1. Structure

```text
reactive-chain-demo/
├── pom.xml
└── src/
    ├── main/java/demo/reactive/ReactiveChainApplication.java
    └── test/java/demo/reactive/ReactiveChainTests.java
```

**`pom.xml`:**

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
    <artifactId>reactive-chain-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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

### 7.2. Complete Java Code

Create `src/main/java/demo/reactive/ReactiveChainApplication.java`:

```java
package demo.reactive;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class ReactiveChainApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveChainApplication.class, args);
    }

    @Bean
    @Order(1)
    SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
        return http
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher("/api/**"))
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/hello")
                    .hasAuthority("API_READ")
                .pathMatchers(HttpMethod.POST, "/api/tasks")
                    .hasAuthority("API_WRITE")
                .pathMatchers(HttpMethod.GET, "/api/admin")
                    .hasRole("ADMIN")
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            // CSRF not disabled: POST requests require a valid token.
            .build();
    }

    @Bean
    SecurityWebFilterChain fallbackChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/public").permitAll()
                .pathMatchers(HttpMethod.GET, "/profile").authenticated()
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        return new MapReactiveUserDetailsService(
            User.withUsername("alice")
                .password(encoder.encode("demo-pass"))
                .authorities("API_READ", "ROLE_USER").build(),
            User.withUsername("writer")
                .password(encoder.encode("demo-pass"))
                .authorities("API_READ", "API_WRITE").build(),
            User.withUsername("admin")
                .password(encoder.encode("demo-pass"))
                .roles("ADMIN").build()
        );
    }
}

@RestController
class ReactiveRoutes {
    @GetMapping("/public")
    Mono<String> publicPage() {
        return Mono.just("public");
    }

    @GetMapping("/profile")
    Mono<String> profile() {
        return Mono.just("profile");
    }

    @GetMapping("/api/hello")
    Mono<String> apiHello() {
        return Mono.just("api-hello");
    }

    @PostMapping("/api/tasks")
    Mono<String> createTask() {
        // Simulates action only; no database writes.
        return Mono.just("created");
    }

    @GetMapping("/api/admin")
    Mono<String> apiAdmin() {
        return Mono.just("admin");
    }
}
```

**Parts of the demo:**

- `ServerHttpSecurity` is the reactive DSL, while `SecurityWebFilterChain` is the bean inspected by `WebFilterChainProxy` when requests arrive.
- `PathPatternParserServerWebExchangeMatcher("/api/**")` selects the API chain; the fallback chain has no narrowing matcher and thus catches non-API requests.
- `@Order(1)` prioritizes the API chain ahead of the fallback. `anyExchange().denyAll()` closes other paths **inside the chain**.
- `MapReactiveUserDetailsService` provides in-memory identities through Spring Security's reactive API. Do not use synchronous `InMemoryUserDetailsManager`/`UserDetailsService` and assume it is the default reactive integration.
- Handlers return `Mono<String>` to illustrate asynchronous processing style. In real services, non-blocking execution and reading the principal via Reactor Context matter far more than a controller returning `Mono.just(...)`.
- Spring Security WebFlux still supports CSRF and security headers per configuration. Rules like `API_READ/API_WRITE` are only examples; real apps must also enforce permissions on individual entities, tenants, and sensitive actions.

### 7.3. WebTestClient with Spring Security Test

Create `src/test/java/demo/reactive/ReactiveChainTests.java`:

```java
package demo.reactive;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class ReactiveChainTests {
    @Autowired
    ApplicationContext applicationContext;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(applicationContext)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void matchesApiFirstAndFallsBackForOtherPaths() {
        client.get().uri("/public").exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public");

        client.get().uri("/api/hello").exchange()
            .expectStatus().isUnauthorized();

        client.get().uri("/api/hello")
            .headers(h -> h.setBasicAuth("alice", "demo-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("api-hello");

        client.get().uri("/api/hello")
            .headers(h -> h.setBasicAuth("admin", "demo-pass"))
            .exchange()
            .expectStatus().isForbidden();

        client.get().uri("/api/admin")
            .headers(h -> h.setBasicAuth("admin", "demo-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("admin");

        client.get().uri("/api/admin")
            .headers(h -> h.setBasicAuth("alice", "demo-pass"))
            .exchange()
            .expectStatus().isForbidden();

        client.get().uri("/profile").exchange()
            .expectStatus().isUnauthorized();

        client.get().uri("/profile")
            .headers(h -> h.setBasicAuth("alice", "demo-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("profile");

        // POST requires a CSRF token even when writer holds API_WRITE.
        client.post().uri("/api/tasks")
            .headers(h -> h.setBasicAuth("writer", "demo-pass"))
            .exchange()
            .expectStatus().isForbidden();

        // Has CSRF, yet lacks API_WRITE -> still denied.
        client.mutateWith(csrf()).post().uri("/api/tasks")
            .headers(h -> h.setBasicAuth("alice", "demo-pass"))
            .exchange()
            .expectStatus().isForbidden();

        // Both CSRF and API_WRITE are valid.
        client.mutateWith(csrf()).post().uri("/api/tasks")
            .headers(h -> h.setBasicAuth("writer", "demo-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("created");

        client.get().uri("/api/unknown")
            .headers(h -> h.setBasicAuth("alice", "demo-pass"))
            .exchange()
            .expectStatus().isForbidden();

        client.get().uri("/unknown")
            .headers(h -> h.setBasicAuth("alice", "demo-pass"))
            .exchange()
            .expectStatus().isForbidden();
    }
}
```

`WebTestClient.bindToApplicationContext(...)` uses the Spring WebFlux handler chain initialized from the context; `apply(springSecurity())` integrates Spring Security test support, and `mutateWith(csrf())` supplies a valid CSRF token for test requests. `setBasicAuth(...)` exercises HTTP Basic credential authentication. No real server needs to start for this test. Unit-testing a single `WebFilter` does not replace **full-chain integration testing** when multiple matchers exist.

### 7.4. Run Commands

Inside `reactive-chain-demo`:

```bash
mvn test
mvn spring-boot:run
```

Try the GET requests with curl once the application is running:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/api/hello
curl -i -u alice:demo-pass http://localhost:8080/api/hello
curl -i -u admin:demo-pass http://localhost:8080/api/admin
curl -i -u alice:demo-pass http://localhost:8080/profile
```

Expected responses respectively: `200 public`; `401`; `200 api-hello`; `200 admin`; `200 profile`. In a CSRF-enabled model, POST requires a matching token, so verify both allow and deny paths via `WebTestClient` as shown above. Never use HTTP Basic over plain HTTP on untrusted networks; `localhost` examples are solely for learning.

## 8. Practical Differences When Moving from Servlet to WebFlux

| Concern | What to check |
| --- | --- |
| Filter type | A Servlet filter cannot be placed directly into `SecurityWebFilterChain`; a reactive web filter is not a Servlet `Filter` |
| Context | Servlet usually uses `SecurityContextHolder` on ThreadLocal; WebFlux uses `ReactiveSecurityContextHolder` via Reactor Context |
| Authorization API | `authorizeHttpRequests`/`requestMatchers` differ from `authorizeExchange`/`pathMatchers` |
| Custom authentication | Servlet authentication filters + `AuthenticationManager` differ from reactive `AuthenticationWebFilter` + `ReactiveAuthenticationManager` |
| Request object | `HttpServletRequest` differs from `ServerWebExchange` |
| Session | Servlet `HttpSession` differs from WebFlux `WebSession`; context/session persistence must match the stack |
| Blocking I/O | A WebFlux handler calling JDBC/blocking SDKs on the event loop can stall even when wrapped in `Mono`; use reactive drivers or proper offloading |
| Error handling | Servlet dispatch/error semantics differ from the WebFlux error pipeline; test actual status/error routes |
| CSRF | Both support CSRF; repositories, token request handlers, configuration, and test utilities differ |
| Testing | Spring MVC `MockMvc` differs from WebFlux `WebTestClient`; avoid picking the wrong tool because the two starters have similar names |
| Method security | Servlet typically uses `@EnableMethodSecurity` and method interceptors; WebFlux needs reactive method security and compatible publisher return types |
| Matcher | `RequestMatcher` and `ServerWebExchangeMatcher` are distinct APIs; pay close attention to HTTP method/path when porting code |
| Startup | Having both `spring-boot-starter-web` and `spring-boot-starter-webflux` does not guarantee WebFlux runs; check `WebApplicationType`, classpath, and auto-configuration |

### 8.1. Porting Custom Filters

**Illustrative Servlet** example (not a complete class):

```java
// Use Filter/OncePerRequestFilter in the Servlet stack.
http.addFilterBefore(myServletFilter, UsernamePasswordAuthenticationFilter.class);
```

**Illustrative WebFlux** example (not a complete class):

```java
// Use WebFilter with position defined by SecurityWebFiltersOrder.
http.addFilterAt(myReactiveWebFilter, SecurityWebFiltersOrder.AUTHENTICATION);
```

For custom authentication filters, place them at the authentication position, never arbitrarily after authorization. For logging, tracing, CORS, or security-header filters, pick a position matching their responsibility. If a Servlet `Filter` is also declared as a Spring bean in Boot, the container may auto-register it separately and execute it twice if also added to the Spring Security chain; manage registration explicitly.

### 8.2. Enforcing Permissions Beyond the Filter Boundary

A `.authenticated()` rule means "the actor has been recognized as authenticated by Spring Security under that mechanism". It **does not mean** the actor can read every record. For `GET /api/orders/{id}`, the service must still check tenant/owner/ACL. For `POST /api/payments`, beyond `API_WRITE`, you must also control limits, idempotency, state transitions, and authority over the funding source. This holds in both Servlet and WebFlux.

For multi-tenant data, define scoped queries such as `findByIdAndTenantId` or enforce policies in the service using the **tenant from the trusted identity**. URL matchers do not query the database to see who owns an object. Checking permissions only after data has already been returned in the response is too late.

## 9. Common Configuration Mistakes

### 9.1. Defining an API Chain and Forgetting a Fallback

**Symptom:** `/api/**` requires login, while `/admin` outside `/api/**` bypasses Spring Security completely.

**Cause:** only one chain has `securityMatcher("/api/**")`, and no chain matches `/admin`.

**Fix:** add a fallback chain without a narrowing matcher, using `anyRequest().denyAll()` or an explicit policy; test endpoints both inside and outside the prefix.

### 9.2. Putting an Overly Broad Matcher on a High-Priority Chain

**Symptom:** the prioritized API chain never executes; every request hits the catch-all chain above and skips required rules.

**Cause:** a match-all chain took priority ahead of a narrower chain.

**Fix:** place narrow chains first and the catch-all chain last; write tests proving which chain is selected. Never rely on bean method names or source-file declaration order.

### 9.3. Assuming Chains Stack Security Layers

**Symptom:** the API chain omits headers/CSRF configured on the fallback chain because developers expect the fallback to run afterward.

**Cause:** only the first matching chain runs.

**Fix:** share recurring rules across chains via appropriate helpers/configs, or reduce the number of chains when there is no reason to split; inspect the actual filter list.

### 9.4. Confusing `permitAll()` and `ignoring()`

**Symptom:** static resources or public endpoints skip all security filters, losing protective response headers.

**Cause:** bypassing the security filter chain instead of using an allow rule inside it.

**Fix:** permit requests inside the chain with `permitAll` when appropriate and intentional, keeping general security filters active.

### 9.5. Changing GET to POST While Forgetting CSRF and Method-Specific Authorization

**Symptom:** POST requests fail with 403 despite the user having the right role; or developers disable CSRF globally to "fix" it, exposing cookie-based endpoints to CSRF.

**Cause:** mixing up endpoint authorization and CSRF protection. These two checks are independent.

**Fix:** authorize by action/HTTP method, send a valid CSRF token when the browser may attach login credentials automatically; disable CSRF only if your threat model confirms it is safe. Test denied paths too.

### 9.6. Adding a Filter from the Wrong Framework or at the Wrong Position

**Symptom:** a `OncePerRequestFilter` class does nothing in a reactive chain; or bearer authentication is skipped because the filter was placed after authorization.

**Fix:** pick the right API (`Filter` vs `WebFilter`), the right chain, and the right order; verify the actual runtime application type and write end-to-end tests.

### 9.7. Using ThreadLocal in WebFlux

**Symptom:** the principal appears intermittently as the reactive pipeline switches schedulers, or user data leaks when stored in a global context.

**Fix:** use `ReactiveSecurityContextHolder` and pass verified identity through the publisher/Context; never call `block()` on the event loop.

### 9.8. Putting Admin Endpoints Under `/api/**` While Writing Their Rules in the Fallback

**Symptom:** the fallback declares `/api/admin/**.hasRole("ADMIN")`, yet requests are captured by the API chain, so the fallback rule never runs.

**Fix:** place rules inside the **chain that actually matches**. Review "chain matcher → rules inside chain", rather than merely grepping for `/api/admin` in code.

### 9.9. Confusing 404 and 403 on Paths Without Handlers

A request to a URL with no controller can return `403` because `denyAll` executes **before handler mapping decides 404**. This is not necessarily a routing bug. If your API needs to return 404 for certain URLs, maintain a clear and consistent security policy; never open all URLs just to change the error code.

## 10. How to Inspect the Running Filter Chain

### 10.1. Enabling Logs in Local/Staging

With Spring Boot 3.x, configure logging in `application.properties` in a test environment:

```properties
logging.level.org.springframework.security=DEBUG
```

For deeper analysis, you can temporarily raise TRACE on the relevant package, yet **never** keep detailed logs containing sensitive credentials/requests in production. Startup logs typically help identify attached filters; per-request logs show which requests are protected. Exact log levels and formats vary by version.

### 10.2. Debugging Checklist for a 401/403 Request

1. **Actual stack:** Spring MVC Servlet or WebFlux? Which server/proxy did the request pass through?
2. **Which chain matched?** Is there a matching `securityMatcher`, and what is the `@Order` sequence? Is there a fallback?
3. **Which rule matched?** Are path/HTTP method/servlet path/dispatcher type accurate? Did `anyRequest`/`anyExchange` block it?
4. **Authentication:** were credentials decoded and verified? Is `Authentication` anonymous or authenticated? Does it carry the exact authority name? `hasRole` expects the default `ROLE_` prefix.
5. **Exploit protection:** is a POST missing a CSRF token? Are CORS/preflight configured properly? Are headers/redirects affected by a proxy?
6. **Handler:** did the request reach the controller, or did a security filter block it earlier? If it reached the controller, owner/tenant policies must still be checked in the service.
7. **Tests:** did you test anonymous, normal user, admin, wrong role, wrong method, new URLs, and paths outside all chains?

Never log passwords, bearer tokens, session cookies, private keys, or raw `Authentication` objects to public log files. For WebFlux, check pipeline scheduling and Reactor Context whenever authentication flows across reactive components.

## 11. Self-Assessment Exercises

**Exercise 1.** An API chain has `securityMatcher("/api/**")` and `authorizeHttpRequests(anyRequest -> denyAll())`. There are no other chains. Is `GET /internal/health` protected by Spring Security?

**Answer:** No, if no other chain matches `/internal/health`. The API chain's `anyRequest` only evaluates requests that already matched `/api/**`. Missing a fallback is a configuration flaw.

**Exercise 2.** Two chains both match `GET /api/admin`. The `@Order(1)` chain requires `API_READ`, while the later chain requires `ROLE_ADMIN`. Which chain handles a request holding only `ROLE_ADMIN`?

**Answer:** Only the `@Order(1)` chain is used; lacking `API_READ`, the request is denied. The framework does not fall through to the next chain to try allowing it.

**Exercise 3.** A POST request has the right role yet lacks a CSRF token in an app using cookies/sessions with CSRF enabled. Can it reach the controller?

**Answer:** Normally no; CSRF protection rejects requests missing a token before executing the action. Never disable CSRF just because a role check exists.

**Exercise 4.** A reactive service calls `SecurityContextHolder.getContext()` and gets `null` after switching threads. Where should the bug be fixed?

**Answer:** Use the reactive `ReactiveSecurityContextHolder`/Reactor Context API or pass a verified actor explicitly through the pipeline. Never switch to `MODE_GLOBAL` so all threads see the same identity.

**Exercise 5.** `GET /api/orders/123` is protected with `authenticated()`. Can Alice view Bob's invoice?

**Answer:** The chain only requires `authenticated`; to prevent Alice from viewing Bob's invoice, the service/repository must verify ownership/tenant/permissions for order 123. An `authenticated` endpoint alone does not protect individual data objects.

## 12. Takeaways

1. **Servlet:** `DelegatingFilterProxy → FilterChainProxy → SecurityFilterChain → Servlet Filter → DispatcherServlet`.
2. **WebFlux:** `WebFilterChainProxy → SecurityWebFilterChain → WebFilter → DispatcherHandler`, paired with Reactor Context.
3. **Chain selection occurs before rule authorization.** `securityMatcher` selects the chain; `requestMatchers`/`pathMatchers` select permissions within the chain.
4. **The first matching chain is the only chain that runs**; order specific chains first and include a fallback so no requests slip through.
5. **`HttpSecurity` and `ServerHttpSecurity` are builders**, used for configuration, not filters running directly per request.
6. **Protection at the web boundary does not replace domain policies.** Enforce permissions by actor/action/resource/tenant/state and test denied paths.

## Official References

- [Spring Security 6.5 — Servlet Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html)
- [Spring Security 6.5 — Java Configuration and Multiple SecurityFilterChains](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html)
- [Spring Security 6.5 — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security 6.5 — WebFlux Security Configuration](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html)
- [Spring Security 6.5 — WebFlux CSRF](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html)
- [Spring Security — MockMvc HTTP Basic Test](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/http-basic.html)
- [Spring Security — WebTestClient Security Setup](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/setup.html)
- [Spring Security — WebFlux Testing CSRF](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/csrf.html)
- [Spring Boot 3.5.16 — End of OSS Support for 3.5.x](https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/)
