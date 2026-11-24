# Servlet SecurityFilterChain and Reactive SecurityWebFilterChain in Spring Boot

> **Module:** Spring Boot - web-runtime · **Group:** Security Integration. This article explains how Spring Security plugs a security layer into two web runtimes: **Spring MVC on Servlet** and **Spring WebFlux reactive**. The focus is on distinguishing `SecurityFilterChain` from `SecurityWebFilterChain`, execution paths, chain selection conditions, writing authorization rules, storing security context, CSRF, CORS, common pitfalls, and testing. Examples use **Java 17+**, Maven, **Spring Boot 4.1.2**, and Spring Security with Boot-managed dependencies. The two MVC/WebFlux applications are placed in **two independent projects**.

## Learning Objectives

After this article, you will be able to:

1. Describe both HTTP processing pipelines and explain why `SecurityFilterChain` and `SecurityWebFilterChain` cannot be swapped.
2. Identify the responsibilities of `DelegatingFilterProxy`, `FilterChainProxy`, and `jakarta.servlet.Filter` in Servlet, contrasted with `WebFilterChainProxy` and `org.springframework.web.server.WebFilter` in WebFlux.
3. Distinguish **authentication** (verifying the caller) from **authorization** (deciding access to a resource), as well as the role of `SecurityContext`.
4. Write chains using `HttpSecurity.authorizeHttpRequests(...)` on MVC and `ServerHttpSecurity.authorizeExchange(...)` on WebFlux, using `permitAll`, `authenticated`, and `hasRole`.
5. Understand **first matching security chain**, `@Order` priority, and the difference between **chain-level matchers** and **authorization rule matchers**.
6. Build and run two independent REST demos for the same endpoints and observe 200/401/403 via cURL.
7. Explain CSRF, stateless APIs, sessions, Reactive Context, filter ordering, CORS, and pitfalls when integrating JWT, OAuth2, method security, or custom filters.
8. Choose the right way to design and test security when moving between MVC and WebFlux.

## 1. The Common Problem: Requests Must Pass Through Security Before the Controller

An endpoint like `GET /admin` can be declared with `@GetMapping`. Spring MVC or WebFlux decides which **controller/handler** processes the URL. Spring Security handles **who is allowed to reach that handler** along with mechanisms such as request authorization, authentication, CSRF, headers, sessions, or exception translation.

Conceptual flow:

~~~text
HTTP request
  -> web server receives request
  -> Spring Security web chain
       1. check/execute authentication mechanism if needed
       2. access/maintain security context
       3. make access decision
       4. CSRF/CORS/security headers/exception handling per configuration
  -> MVC controller or WebFlux handler
  -> HTTP response
~~~

Note that the order in the diagram is **conceptual**: real filters have specific positions, multiple filters may run before/after authentication, and CORS preflight or CSRF may handle a request before authorization. Do not rely on this diagram to hand-code filter ordering.

**Authentication** verifies identity/credentials, such as HTTP Basic, session cookies, bearer JWTs, OAuth2 login, or mTLS. **Authorization** decides permission for a URL/method/resource. Having a valid Authentication does not mean access to every endpoint.

Example:

| Request | Caller | Rule | Typical Result |
| --- | --- | --- | --- |
| `GET /public` | Anonymous | `permitAll()` | 200 |
| `GET /me` | Anonymous | `authenticated()` | 401 with HTTP Basic API |
| `GET /me` | Authenticated USER | `authenticated()` | 200 |
| `GET /admin` | Authenticated USER, without ADMIN | `hasRole("ADMIN")` | 403 |
| `GET /admin` | Authenticated ADMIN | `hasRole("ADMIN")` | 200 |

**401** usually means missing or invalid authentication and may include `WWW-Authenticate`. **403** usually means authenticated without permission, or the request was rejected by another policy (such as CSRF). With form login or OAuth2 redirects, an unauthenticated user **may receive 302** instead of 401. The status depends on the entry point and actual setup, not merely the presence of a `SecurityFilterChain`.

## 2. Two Web Stacks Handle Requests Differently

### 2.1. Servlet / Spring MVC

~~~text
Browser / API client
  |
  v
Servlet container (Tomcat/Jetty)
  |
  v
Servlet Filter chain
  |
  +-- DelegatingFilterProxy("springSecurityFilterChain")
  |      |
  |      v
  |   FilterChainProxy
  |      |
  |      +-- picks first SecurityFilterChain whose RequestMatcher matches
  |      |
  |      +-- runs jakarta.servlet.Filter instances inside the chain
  |             CSRF, Authentication, Authorization, ...
  |
  v
DispatcherServlet
  |
  v
@Controller / @RestController
  |
  v
HTTP response via Servlet container
~~~

- `DelegatingFilterProxy` is a bridge between a **Servlet container Filter** and a Spring-managed bean. In Boot configuration, registration is typically auto-configured without writing `web.xml`.
- `FilterChainProxy` is the Spring Security mechanism that manages and selects one of the `SecurityFilterChain` instances.
- A `SecurityFilterChain` consists of a **RequestMatcher** and a list of **Servlet Filters** applied when the request matches.
- Filters operate on `HttpServletRequest`/`HttpServletResponse` and continue execution via `FilterChain.doFilter(...)`.
- `HttpSecurity` is a builder for configuring the filter chain, not a filter directly invoked on every request.

### 2.2. Reactive / Spring WebFlux

~~~text
Browser / API client
  |
  v
Reactor Netty (common) or WebFlux-compatible runtime
  |
  v
HTTP exchange -> WebFilter chain
  |
  +-- Spring Security WebFilterChainProxy
  |      |
  |      +-- picks first SecurityWebFilterChain matching ServerWebExchange
  |      |
  |      +-- runs WebFilters in the reactive pipeline
  |             CSRF, Authentication, Authorization, ...
  |
  v
DispatcherHandler
  |
  v
Handler / @RestController (Mono/Flux)
  |
  v
Non-blocking HTTP response
~~~

- `SecurityWebFilterChain` holds a **ServerWebExchangeMatcher** and a list of **WebFilter** instances using reactive APIs.
- `ServerHttpSecurity` configures security behavior for **WebFlux**, unlike `HttpSecurity` in Servlet.
- `WebFilter.filter(ServerWebExchange, WebFilterChain)` returns `Mono<Void>`, which can emit completion/errors or complete asynchronously.
- The reactive authentication context is typically propagated via **Reactor Context**, not guaranteed to stay in the same ThreadLocal across schedulers.
- `SecurityWebFilterChain` is **not** a `jakarta.servlet.Filter` and is not registered through a Servlet `FilterRegistrationBean`.

If an application has both `spring-boot-starter-webmvc` and `spring-boot-starter-webflux`, Spring Boot normally selects the **Servlet/MVC web application type**, unless explicitly configured otherwise. Merely adding the WebFlux starter to use `WebClient` **does not** switch server requests to reactive. Check the runtime type before choosing security APIs.

## 3. Comparison of Classes, APIs, and Lifecycles

| Topic | Servlet / MVC | Reactive / WebFlux |
| --- | --- | --- |
| Web runtime | Servlet container, `DispatcherServlet` | WebFlux runtime, `DispatcherHandler` |
| Chain type | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Builder | `HttpSecurity` | `ServerHttpSecurity` |
| Security container/proxy | `FilterChainProxy` via `DelegatingFilterProxy` | `WebFilterChainProxy` in WebFlux filter chain |
| Filter interface | `jakarta.servlet.Filter` | `org.springframework.web.server.WebFilter` |
| Matcher input | `HttpServletRequest` + `RequestMatcher` | `ServerWebExchange` + `ServerWebExchangeMatcher` |
| Authorization DSL | `authorizeHttpRequests(...)` | `authorizeExchange(...)` |
| URL rule | `requestMatchers(...)` | `pathMatchers(...)` / `matchers(...)` |
| Fallback rule | `anyRequest()` | `anyExchange()` |
| Basic auth | `httpBasic(...)` | `httpBasic(...)` |
| User lookup | `UserDetailsService` or authentication provider | `ReactiveUserDetailsService` / reactive authentication manager |
| Security context | `SecurityContextHolder`, typically thread-bound | `ReactiveSecurityContextHolder`, Reactor Context |
| Session infrastructure | `HttpSession`, `SecurityContextRepository` | `WebSession`, `ServerSecurityContextRepository` |
| Method security | `@EnableMethodSecurity` | `@EnableReactiveMethodSecurity` |
| HTTP result | Servlet response, async via appropriate APIs | Publisher (`Mono`/`Flux`) |
| Custom filter ordering | Spring Security filter order, `addFilterBefore/After`... | `SecurityWebFiltersOrder` / `addFilterAt` and reactive semantics |

Common ground: both support multiple chains, authentication mechanisms, authorization rules, CSRF, CORS, and headers. **However, the Java classes and extension points differ**; you cannot simply rename Servlet types to reactive ones and keep the same implementation approach.

## 4. Chain Selection: First Match, Not “Merge All”

An application can declare multiple chains, for example a dedicated chain for `/api/**` and a fallback chain for other URLs. Both Servlet and reactive stacks select the **first matching chain** according to priority order (typically via `@Order`).

~~~text
Request GET /api/orders
  |
  +-- Chain A @Order(1), securityMatcher /api/**  -> MATCH -> USE A
  |
  +-- Chain B @Order(2), matcher /admin/**        -> not evaluated
  |
  +-- Fallback chain                              -> not evaluated
~~~

All authorization rules and filters of A govern the request. If A **denies access** and returns 403, the framework **does not** try chain B just because B might permit the request. Security chain selection and permission evaluation are **not** two identical fallback loops.

If a request matches no chain, it can **pass through without Spring Security protection**. Therefore, always have a **fallback chain** matching any request and using `authenticated()` or `denyAll()` per policy.

### 4.1. `@Order`

- `@Order(1)` is evaluated before `@Order(2)`.
- Lower order values have higher priority; do not rely on bean names or file declaration order for security.
- Specialized chains should have explicit order values, with the fallback placed last.
- Do not grant access via an overly broad matcher on a high-priority chain expecting a lower-priority chain to restrict it later.
- When matchers overlap, test URLs that match multiple chains to verify which chain is **actually selected**.

### 4.2. Chain Matchers Differ from Authorization Matchers

**Servlet:**

~~~java
// Illustrative fragment of a SecurityFilterChain for /api/**.
http.securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/public").permitAll()
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated());
~~~

`securityMatcher("/api/**")` decides **whether this chain is used**. Once the chain is selected, `requestMatchers("/api/admin/**")` decides **permissions** for a request within that chain. `anyRequest()` is only a fallback **inside the selected chain**; it does not protect URLs outside `/api/**`.

**Reactive:**

~~~java
// Illustrative fragment: chain for /api/** in WebFlux.
http.securityMatcher(
        new PathPatternParserServerWebExchangeMatcher("/api/**"))
    .authorizeExchange(ex -> ex
        .pathMatchers("/api/public").permitAll()
        .pathMatchers("/api/admin/**").hasRole("ADMIN")
        .anyExchange().authenticated());
~~~

Chain matchers use `ServerWebExchangeMatcher`; authorization matchers select rules within a chain and can also match HTTP methods.

**Do not confuse** MVC's `requestMatchers(...)` with WebFlux's `pathMatchers(...)`. Also do not use Servlet matchers to secure WebFlux or vice versa.

### 4.3. Rule Order Inside a Chain Also Matters

Example:

~~~java
// WRONG for intent: broad rule is evaluated first.
auth.requestMatchers("/api/**").permitAll()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated();
~~~

A request to `/api/admin/stats` will already be handled by the broad `permitAll` rule, so the specific admin rule is never reached. Place **specific rules first**, and broad/fallback rules last:

~~~java
auth.requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/public/**").permitAll()
    .anyRequest().authenticated();
~~~

In WebFlux, apply the same principle using `pathMatchers(...)`. Always test requests at pattern boundaries.

## 5. A Basic Servlet Chain in Spring MVC

Modern Spring Security configuration pattern:

~~~java
// Spring MVC fragment, not a standalone class.
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/public").permitAll()
            .requestMatchers("/admin").hasRole("ADMIN")
            .anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults());
    return http.build();
}
~~~

- `@Bean` exposes a `SecurityFilterChain`.
- `HttpSecurity` builds the list of servlet security filters and request matcher; `build()` finalizes the configuration.
- `permitAll()` allows public endpoints but **does not remove all security filters**.
- `hasRole("ADMIN")` checks the **`ROLE_ADMIN`** authority by convention, not an arbitrary string `ADMIN` (to check a literal authority string, use `hasAuthority(...)`).
- `anyRequest().authenticated()` does not require the admin role: any authenticated user can access the remaining URLs.
- `httpBasic(...)` adds the HTTP Basic mechanism. While convenient for demos, production must use HTTPS and an appropriate auth mechanism; do not treat Basic Base64 encoding as secret encryption.

**CSRF remains enabled by default** because the sample does not disable it. The demo below only reads via GET. If you add POST/PUT/DELETE using browser credentials, handle CSRF tokens or properly analyze stateless bearer token scenarios; do not disable it globally just to make tests pass.

## 6. A Basic Reactive Chain in Spring WebFlux

~~~java
// Spring WebFlux fragment, not a standalone class.
@Bean
SecurityWebFilterChain springSecurityFilterChain(ServerHttpSecurity http) {
    return http
        .authorizeExchange(ex -> ex
            .pathMatchers("/public").permitAll()
            .pathMatchers("/admin").hasRole("ADMIN")
            .anyExchange().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

- `ServerHttpSecurity` is the **WebFlux** builder; it does not accept `HttpServletRequest`.
- `SecurityWebFilterChain` is created by the builder and runs inside the reactive stack's web filter chain.
- `authorizeExchange(...)` evaluates permissions on `ServerWebExchange`; `anyExchange()` is the fallback.
- `httpBasic(...)` uses the reactive authentication stack; user lookup can be a `ReactiveUserDetailsService`.
- Calling `build()` does not subscribe to a `Mono`; this is startup-time chain configuration, not manual request handling.

When reading authentication inside a pipeline, use `ReactiveSecurityContextHolder.getContext()` or the principal from `ServerWebExchange.getPrincipal()`; do not rely on `SecurityContextHolder.getContext()` inside a reactive `flatMap` across arbitrary threads. Reactor can switch schedulers and threads during a request's lifecycle.

## 7. Two Runnable Projects: Same Rules, Different Runtimes

For comparison, we build two projects with the **same endpoints and users**:

| Endpoint | Public | learner / USER | admin / ADMIN |
| --- | --- | --- | --- |
| `GET /public` | 200 | 200 | 200 |
| `GET /me` | 401 | 200 | 200 |
| `GET /admin` | 401 | 403 | 200 |

The 401/403 results assume requests use HTTP Basic, the client has no valid cookie/session, and no other entry point is configured. In the demo, passwords are hardcoded **for localhost only**, never as production secrets and never for live internet-facing systems. Both use BCrypt for hashing in-memory users. Never store real passwords in plaintext in a project.

### 7.1. Project A — Servlet MVC SecurityFilterChain

**Structure:**

~~~text
security-servlet-demo/
  pom.xml
  src/main/java/com/example/servletsecurity/
    ServletSecurityApplication.java
    ServletSecurityConfig.java
    ApiController.java
  src/main/resources/
    application.properties
~~~

**`pom.xml`**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>security-servlet-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
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

This is a **Servlet stack** Maven project with embedded Tomcat. Spring Boot manages compatible Spring Security versions. Do not add `spring-boot-starter-webflux` to Project A.

**`ServletSecurityApplication.java`**

~~~java
package com.example.servletsecurity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ServletSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(ServletSecurityApplication.class, args);
    }
}
~~~

**`ServletSecurityConfig.java`**

~~~java
package com.example.servletsecurity;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebSecurity
public class ServletSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public", "/error").permitAll()
                        .requestMatchers("/admin").hasRole("ADMIN")
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
        // Demo credentials, for non-public local environments only.
        UserDetails learner = User.withUsername("learner")
                .password(encoder.encode("learner-demo-123"))
                .roles("USER")
                .build();
        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-demo-123"))
                .roles("USER", "ADMIN")
                .build();
        return new InMemoryUserDetailsManager(learner, admin);
    }
}
~~~

**Explanation:**

- `@EnableWebSecurity` makes the example's intent explicit; with standard Spring Boot auto-configuration, Spring Security integration can also activate automatically when the starter is on the classpath.
- `SecurityFilterChain` is the bean protecting all requests because no narrower `securityMatcher(...)` is set. HTTP Basic is enabled and authentication is backed by `UserDetailsService`.
- `PasswordEncoder` uses BCrypt rather than storing plaintext passwords on the user object. Literal passwords only serve the demo so learners can easily test with cURL; in practice, obtain credentials from an identity provider, secret storage, or credential provisioning.
- `ROLE_USER` and `ROLE_ADMIN` are attached by the `.roles(...)` builder; hence `hasRole("ADMIN")` matches the admin user.
- `/error` is `permitAll` to avoid 401 loops when the framework needs to render errors; do not treat this as access to real data.

**`ApiController.java`**

~~~java
package com.example.servletsecurity;

import java.security.Principal;
import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {

    @GetMapping("/public")
    public Map<String, String> publicInfo() {
        return Map.of("message", "public");
    }

    @GetMapping("/me")
    public Map<String, String> me(Principal principal) {
        return Map.of("user", principal.getName());
    }

    @GetMapping("/admin")
    public Map<String, String> admin() {
        return Map.of("message", "admin only");
    }
}
~~~

MVC `Principal` is supplied from the security request context. The `me()` method only executes after authorization permits an authenticated user. Never rely on a query string like `user=admin` to construct a Principal yourself.

**`application.properties`**

~~~properties
server.port=8080
logging.level.org.springframework.security=INFO
~~~

Using `INFO` avoids printing excessive output in the demo. During debugging, you can raise it to DEBUG in a controlled test environment; never log passwords, Basic headers, bearer tokens, or personal data.

### 7.2. Project B — WebFlux SecurityWebFilterChain

**Structure:**

~~~text
security-reactive-demo/
  pom.xml
  src/main/java/com/example/reactivesecurity/
    ReactiveSecurityApplication.java
    ReactiveSecurityConfig.java
    ApiController.java
  src/main/resources/
    application.properties
~~~

**`pom.xml`**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>security-reactive-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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

`spring-boot-starter-webflux` uses WebFlux with Reactor Netty by default, **not** the servlet MVC starter. Avoid mixing both starters in Project B if you want to observe the genuine reactive security pipeline.

**`ReactiveSecurityApplication.java`**

~~~java
package com.example.reactivesecurity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveSecurityApplication.class, args);
    }
}
~~~

**`ReactiveSecurityConfig.java`**

~~~java
package com.example.reactivesecurity;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(ex -> ex
                        .pathMatchers("/public", "/error").permitAll()
                        .pathMatchers("/admin").hasRole("ADMIN")
                        .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    ReactiveUserDetailsService userDetailsService(PasswordEncoder encoder) {
        // Demo credentials, do not use in production.
        UserDetails learner = User.withUsername("learner")
                .password(encoder.encode("learner-demo-123"))
                .roles("USER")
                .build();
        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-demo-123"))
                .roles("USER", "ADMIN")
                .build();
        return new MapReactiveUserDetailsService(learner, admin);
    }
}
~~~

**Explanation:**

- There is no Servlet-style `HttpSecurity` or `SecurityFilterChain`; the right bean is `SecurityWebFilterChain` built from `ServerHttpSecurity`.
- `MapReactiveUserDetailsService` is a demo implementation of `ReactiveUserDetailsService`; user data resides in memory, not a production database/repository.
- BCrypt is a CPU-bound operation; under heavy workloads, consider authentication resource sizing. Do not put custom blocking JDBC authentication onto the Reactor Netty event loop; if your source only has blocking APIs, isolate it on an appropriate scheduler or switch to a reactive repository/auth manager.
- `authorizeExchange(...)` protects WebFlux exchanges; `anyExchange().authenticated()` is the fallback for all other routes.

**`ApiController.java`**

~~~java
package com.example.reactivesecurity;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    @GetMapping("/public")
    public Mono<Map<String, String>> publicInfo() {
        return Mono.just(Map.of("message", "public"));
    }

    @GetMapping("/me")
    public Mono<Map<String, String>> me(ServerWebExchange exchange) {
        return exchange.getPrincipal()
                .map(principal -> Map.of("user", principal.getName()));
    }

    @GetMapping("/admin")
    public Mono<Map<String, String>> admin() {
        return Mono.just(Map.of("message", "admin only"));
    }
}
~~~

`ServerWebExchange.getPrincipal()` returns `Mono<Principal>` in WebFlux; the controller continues processing with Reactor operators. Underneath, Spring Security manages the context in reactive execution without needing manual `subscribe()` or `block()` calls.

**`application.properties`**

~~~properties
server.port=8080
logging.level.org.springframework.security=INFO
~~~

### 7.3. Running and Testing with cURL

Run **one project at a time** because both use port 8080:

~~~bash
# Inside security-servlet-demo/ or security-reactive-demo/:
mvn spring-boot:run
~~~

In another terminal:

~~~bash
# 1. Public route:
curl -i http://localhost:8080/public

# 2. Protected route without Authorization:
curl -i http://localhost:8080/me

# 3. Authenticated as USER:
curl -i -u learner:learner-demo-123 http://localhost:8080/me

# 4. USER attempts admin:
curl -i -u learner:learner-demo-123 http://localhost:8080/admin

# 5. ADMIN accesses admin:
curl -i -u admin:admin-demo-123 http://localhost:8080/admin
~~~

Expected results under the HTTP Basic configuration of both examples:

| Command | Status | Typical Body |
| --- | --- | --- |
| Anonymous GET `/public` | 200 | `{"message":"public"}` |
| Anonymous GET `/me` | 401 | May have error body or empty body; includes HTTP Basic challenge |
| GET `/me` as learner | 200 | `{"user":"learner"}` |
| GET `/admin` as learner | 403 | Depends on error representation, not the controller's response |
| GET `/admin` as admin | 200 | `{"message":"admin only"}` |

JSON property order may vary, and error bodies may vary depending on stack/Boot error configuration. **Only assert responses known from the controller**; do not hardcode error body details when you have not verified them in practice.

On PowerShell, use `curl.exe -i -u learner:learner-demo-123 http://localhost:8080/me`. On Windows, note that `curl` may be an alias for `Invoke-WebRequest` depending on the version.

Packaging:

~~~bash
mvn package
java -jar target/security-servlet-demo-0.0.1-SNAPSHOT.jar
~~~

For the reactive project, use the corresponding JAR name:

~~~bash
java -jar target/security-reactive-demo-0.0.1-SNAPSHOT.jar
~~~

Run inside the appropriate project directory after `mvn package`; do not run both JARs simultaneously on the same port unless you change the port.

**Security warning:** HTTP Basic sends credentials using Base64 encoding, **not** encryption. The `http://localhost:8080` example is only suitable for local testing. Production requires HTTPS (including across reverse proxies with proper trust boundaries) and an identity store/credential management rather than hardcoded demo users.

## 8. Multiple Chains in Servlet: Configuration Example and Ordering

An application might want:

- `/api/**` to use HTTP Basic or bearer JWT.
- Remaining URLs to accept only form/session-logged-in users or be denied.
- No path “leaking” outside Spring Security.

Illustrative fragment placed in a `@Configuration` class (do not add directly alongside the chain in the example above without adjusting configuration):

~~~java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(a -> a
            .requestMatchers("/api/status").permitAll()
            .requestMatchers("/api/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}

@Bean
@Order(2)
SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(a -> a.anyRequest().denyAll())
        .build();
}
~~~

Meaning:

- `@Order(1)` gives priority to `/api/**`. Endpoints outside that prefix do not enter the API chain.
- `fallbackChain` matches all remaining URLs and denies them; this is **deny-by-default**. In a real application, you might replace it with `formLogin`/appropriate permissions, but never omit a fallback unless another layer actively protects those routes.
- When `/api/admin/x` lacks permission, the 403 result does not cause Spring Security to “try the fallback chain” next.
- If the Servlet is mounted under a custom `spring.mvc.servlet.path`, matcher semantics can be subtler. Spring Security 7 had a vulnerability involving `securityMatchers(String)` combined with a Servlet path and matcher builder in certain versions before being patched. Always upgrade to a patched Spring Security release and **test real paths**, not just matcher unit tests.

**Regarding CSRF:** if an API chain only uses bearer tokens in `Authorization` and browsers do not attach credentials automatically, you may consider disabling CSRF **only for that chain/those paths** after assessing the threat model. If cookies/sessions or HTTP Basic auto-sent by browsers are used, do not assume CSRF is unnecessary. Keep it enabled by default unless there is a clear reason.

## 9. Multiple Chains in Reactive: Corresponding Example

The WebFlux fragment differs in matcher API:

~~~java
@Bean
@Order(1)
SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            new PathPatternParserServerWebExchangeMatcher("/api/**"))
        .authorizeExchange(ex -> ex
            .pathMatchers("/api/status").permitAll()
            .pathMatchers("/api/admin/**").hasRole("ADMIN")
            .anyExchange().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}

@Bean
@Order(2)
SecurityWebFilterChain fallbackChain(ServerHttpSecurity http) {
    return http
        .authorizeExchange(ex -> ex.anyExchange().denyAll())
        .build();
}
~~~

Here `PathPatternParserServerWebExchangeMatcher` belongs to `org.springframework.security.web.server.util.matcher`. The fragment requires imports for `Bean`, `Order`, `Customizer`, `SecurityWebFilterChain`, and `ServerHttpSecurity` in a reactive configuration class, not a Servlet class.

**Similarity:** first match and `@Order` priority. **Difference:** the matcher takes `ServerWebExchange`, and filters are reactive `WebFilter` instances. Do not copy `HttpSecurity.securityMatcher(...)` with `RequestMatcher` into WebFlux.

### One Chain per Request, Not One Filter per URL

Security filters live inside the selected chain; even with multiple chain beans, a single request does not normally run through all of those chains sequentially. To block a request by permission, put the rule/authorization inside the **chain that actually matches**. If you need to apply a cross-cutting policy to all URLs, configure it in every relevant chain or via a shared customizer/policy bean—do not assume the fallback chain runs after specialized chains.

## 10. Servlet SecurityContextHolder and Reactor Context

### Servlet: Usually Bound to the Current Thread

In synchronous Servlet execution, many Spring Security components use `SecurityContextHolder` (whose standard strategy relies on `ThreadLocal`) to access the current request's `Authentication`.

~~~java
// Fragment in Servlet code after Spring Security authentication:
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();
String username = authentication.getName();
~~~

This example is **not standalone**; it requires Spring Security context imports. When using async executors, `@Async`, `CompletableFuture`, or application-spawned threads, **do not assume** the security context automatically follows the thread. You can use `DelegatingSecurityContextExecutor` or supported propagation mechanisms. Keep request context lifecycles isolated and never share mutable Authentication across users.

### Reactive: Subscriber Context, Not Thread-Local by Default

In WebFlux, asynchronous operators can resume on multiple threads/schedulers. Spring Security uses **Reactor Context** to propagate the reactive `SecurityContext`:

~~~java
// WebFlux fragment; call inside a Reactor pipeline (do not call block() yourself).
Mono<String> username = ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication().getName());
~~~

Or in an HTTP handler use `ServerWebExchange.getPrincipal()`, as shown in the demo. Do not call `SecurityContextHolder.getContext()` inside a reactive `flatMap` expecting the user to always be present. If you create a Publisher outside the subscription chain, call `subscribe()` manually, offload tasks to a scheduler, or bridge blocking code, you need to understand **context propagation**.

Reactive method security also has requirements: the policy relies on `@EnableReactiveMethodSecurity` and an appropriate return type (usually `Mono`/`Flux`), ensuring the security context is present in the subscriber context. The same service method can have different semantics if it returns a plain value or calls `block()` internally; annotations alone do not make every method reactive.

### Data Stored in Sessions

- Servlet typically uses `HttpSession` and `SecurityContextRepository` to store/restore context across requests when using session-based auth.
- WebFlux uses `WebSession` and `ServerSecurityContextRepository`; the reactive mechanism is not a direct wrapper around `HttpSession`.
- With stateless bearer JWTs, you may not need server-side login sessions; however, **stateless** does not mean “free of CSRF/CORS/permission issues”.
- When using Spring Session/Redis, choose the integration matching Servlet or reactive and evaluate session fixation, expiry, invalidation, and logout.

## 11. CSRF: Defaults and Why You Should Not Disable It Unconditionally

**CSRF** (Cross-Site Request Forgery) is the ability of another site to trigger state-changing requests using credentials that a browser attaches automatically (such as a login session cookie). Spring Security enables CSRF protection by default for **unsafe methods** like POST/PUT/PATCH/DELETE in both Servlet and WebFlux.

### Servlet

~~~java
// Illustrative when customization is needed, NOT advice to disable CSRF globally.
http.csrf(csrf -> csrf
    .ignoringRequestMatchers("/api/token/**"));
~~~

This fragment is only appropriate when the endpoint genuinely does not rely on browser auto-sent credentials and has been evaluated; ignoring CSRF does not mean authentication/authorization automatically works.

### WebFlux

~~~java
// Conceptual illustration; matcher types in WebFlux differ from Servlet.
http.csrf(csrf -> csrf
    .requireCsrfProtectionMatcher(customServerWebExchangeMatcher));
~~~

`customServerWebExchangeMatcher` is an application-defined `ServerWebExchangeMatcher` based on risk; this fragment is **not standalone** and should not be copied without an explicit policy. For HTML forms/sessions, deliver the CSRF token to the client via a supported mechanism. Never disable CSRF just because a Postman POST returned 403.

**HTTP Basic can also be cached/auto-sent by browsers**, so do not assume a Basic-only API is immune to CSRF in all cases. With an OAuth2 bearer header actively added by scripts and no cookies, the threat model differs, though you must still assess XSS, CORS, token storage, and request permissions.

CSRF differs from CORS: CORS governs which cross-origin requests a browser allows JavaScript to read/send by policy, **not** a substitute for CSRF protection.

## 12. CORS, Security Headers, and Processing Order

Browsers may send an `OPTIONS` preflight **without carrying cookies/Authorization** like the actual request. If a security chain requires authentication before handling CORS properly, preflight requests can be rejected.

- Servlet uses CORS configuration via Spring MVC and Spring Security (e.g., `http.cors(Customizer.withDefaults())` when appropriate CORS config is present) or `CorsConfigurationSource`.
- WebFlux uses WebFlux-compatible CORS configuration or `CorsWebFilter`/Spring Security chain; avoid configuring both places in ways that emit conflicting headers.
- Only allow appropriate `Access-Control-Allow-Origin` values. Never carelessly combine wildcard origins with credentials.
- Do not use `permitAll("/**")` just to fix 401/403 preflight responses.
- Headers such as `Content-Security-Policy`, `X-Content-Type-Options`, HSTS, and `Referrer-Policy` may be configured by Spring Security depending on the web stack; do not assume CSP/HSTS is automatically configured merely by adding the starter without verifying.

If the application sits behind a reverse proxy, configure trusted forwarded headers and TLS termination properly; prevent the server from trusting `X-Forwarded-*` headers forged by internet clients. Incorrect redirect URLs or HTTP ↔ HTTPS loops must never be fixed by disabling the security chain.

## 13. JWT, OAuth2, and API Security: Choosing Providers by Stack

The HTTP Basic examples above teach **chain structure**. Production REST APIs typically use OAuth2 resource servers, OpenID Connect, or session-based login depending on the product.

**Servlet JWT resource server (fragment):**

~~~java
// Illustrative once OAuth2 Resource Server dependency and issuer/JWK config are present.
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/public").permitAll()
        .anyRequest().authenticated())
    .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()));
~~~

**WebFlux JWT resource server (fragment):**

~~~java
// Illustrative; requires reactive JWT decoder and resource server dependency.
http.authorizeExchange(ex -> ex
        .pathMatchers("/public").permitAll()
        .anyExchange().authenticated())
    .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()));
~~~

Real configuration also requires an issuer URI/JWK Set URI, signature verification, `exp`, `nbf`, issuer, audience, algorithm checks, scope/authority mapping, JWK caching, and error handling. **Do not trust a JWT just because Base64 decoding succeeds.** Never hand-roll a JWT parser that validates signatures with regex.

Some differences:

| Item | Servlet | Reactive |
| --- | --- | --- |
| Web security builder | `HttpSecurity` | `ServerHttpSecurity` |
| Token authentication runtime | Servlet filters/authentication manager | Reactive WebFilters/reactive auth manager |
| Method security | `@EnableMethodSecurity` | `@EnableReactiveMethodSecurity` |
| JWT decoder | `JwtDecoder` | `ReactiveJwtDecoder` |
| User details | `UserDetailsService` | `ReactiveUserDetailsService` |
| Auth context | SecurityContextHolder/Servlet request | ReactiveSecurityContextHolder/Reactor Context |
| Request matcher | `RequestMatcher` | `ServerWebExchangeMatcher` |

Actual OAuth2 beans can be auto-configured by Boot given the right starter/properties; do not carelessly mix both servlet and reactive providers in the same context.

## 14. Custom Filters: Right Interface, Right Position, Never Block the Event Loop

### Servlet Custom Filter

A standard Servlet filter implements `jakarta.servlet.Filter` or extends `OncePerRequestFilter`. When integrating into a Spring Security chain, you can use `http.addFilterBefore(filter, BasicAuthenticationFilter.class)` or another exact position depending on purpose.

~~~java
// Illustrative fragment in Servlet chain; customFilter must be an appropriate Filter.
http.addFilterBefore(customFilter, BasicAuthenticationFilter.class);
~~~

Do not register the same filter **twice**: both via `@Component` (causing the container to auto-register it as a Servlet filter) and via `addFilterBefore` (adding it to the Spring Security chain). That can run the filter twice or in the wrong order. If needed as a bean, create the bean and disable the corresponding servlet auto-registration.

### Reactive Custom WebFilter

A WebFlux custom filter implements `org.springframework.web.server.WebFilter` and returns `Mono<Void>`; when adding it to a Spring Security chain, specify a position from `SecurityWebFiltersOrder`:

~~~java
// Illustrative fragment in WebFlux configuration.
http.addFilterAt(customWebFilter, SecurityWebFiltersOrder.AUTHENTICATION);
~~~

The `AUTHENTICATION` position should only be used when `customWebFilter` actually performs auth and manages `SecurityContext`/errors; do not arbitrarily place every logging filter there. WebFlux filters must not call `block()`, run blocking JDBC directly on the Netty event loop, or perform blocking I/O without proper isolation.

Custom auth/filters easily introduce bugs bypassing CSRF, leaking tokens, breaking exception translation, losing context propagation, and misordering filters. Prefer built-in authentication providers, OAuth2 resource server, authorization managers, or existing Spring Security solutions over writing custom token filters when unnecessary.

## 15. `permitAll` vs `web.ignoring()` and “No Chain”

In Servlet, when a URL has a `permitAll()` rule, the request normally **still passes through the Spring Security chain**, including security headers and relevant filter mechanisms. In contrast, completely bypassing security with `web.ignoring()` can prevent requests from passing through Spring Security filters.

For public assets like `/css/**`, prefer `permitAll` whenever possible so they still receive security headers and firewall semantics. Do not ignore chains for `/actuator/**`, `/error`, `/api/**`, or broad prefixes just to reduce logging; that can expose endpoints.

Reactive is similar in intent: an authorization rule `permitAll` **does not** mean skipping the entire `WebFilterChainProxy`. However, the ignore configuration API differs from MVC; do not copy `WebSecurityCustomizer.ignoring()` from Servlet to WebFlux.

Remember that `requestMatchers("/public").permitAll()` only decides authorization. Other policies such as CSRF on unsafe requests, CORS, custom filters, or firewalls can still affect the outcome. If you genuinely need a public POST, design the filters properly rather than just slapping on `permitAll`.

## 16. Method Security Is an Additional Layer of Defense

URL rules only protect HTTP paths at the web layer. A service may be invoked by schedulers, message listeners, internal methods, or other endpoints. Method security enforces permission checks at the business boundary.

**Servlet/MVC:**

~~~java
// Illustrative fragment; class needs @Configuration with method security enabled.
@EnableMethodSecurity

// Inside a Spring-managed service:
@PreAuthorize("hasRole('ADMIN')")
public Report getPrivateReport() {
    return loadReport();
}
~~~

**Reactive/WebFlux:**

~~~java
// Illustrative fragment; class needs @EnableReactiveMethodSecurity.
@EnableReactiveMethodSecurity

@PreAuthorize("hasRole('ADMIN')")
public Mono<Report> getPrivateReport() {
    return reportRepository.findReport();
}
~~~

These snippets are **not standalone**: `Report` and `reportRepository` are hypothetical types. With reactive method security, the method returns a Publisher and context must be propagated properly to the subscription. Do not return a plain `Report` expecting Reactive Context to apply the same way as `Mono<Report>`. In both stacks, proxy self-invocation can cause annotations to be skipped in certain setups; verify method security at real boundaries.

Check both role-based authorization and **object-level access control**: a USER may be allowed to GET `/orders/{id}`, yet only be permitted to read their own or their tenant's order. `authenticated()` does not verify record ownership.

## 17. Testing Security: Do Not Just Assert 200 on Pages

A minimal test matrix:

| Test | Why it is needed | Expected |
| --- | --- | --- |
| Anonymous GET public | `permitAll` rule | 200 |
| Anonymous GET private | Auth entry point works | 401 or redirect per config |
| USER GET own endpoint | Authentication + authorization | 200 |
| USER GET admin | RBAC | 403 |
| ADMIN GET admin | Role mapping | 200 |
| Anonymous GET new unlisted route | Fallback deny/authenticated | Never defaults to 200 public |
| POST without CSRF token in cookie/session web | CSRF policy | 403 when CSRF applies |
| CORS preflight | Browser integration | Not wrongly blocked by auth |
| Paths `/admin/x` and `/admin-evil` | Matcher boundaries | No accidental permission widening |
| API paths with trailing slash/case/encoding | Path semantics | Policy matches mapping |
| Multiple chains, path matches 2 matchers | Chain priority | Only highest-priority matching chain runs |
| Expired/wrong-issuer OAuth2/JWT | Token validation | 401 or error per contract |
| Resource owned by another user | Object-level auth | 403/404 per policy without leaking data |

### Servlet Tests

Use Spring Security Test + MockMvc:

~~~java
// JUnit/MockMvc fragment, only use in projects with test starters.
mockMvc.perform(get("/public"))
    .andExpect(status().isOk());

mockMvc.perform(get("/admin").with(httpBasic("learner", "learner-demo-123")))
    .andExpect(status().isForbidden());

mockMvc.perform(get("/admin").with(httpBasic("admin", "admin-demo-123")))
    .andExpect(status().isOk());
~~~

These imports and test dependencies are not included in the minimal project in Section 7. For Boot 4.x, use WebMVC/Security Test-compatible test starters rather than blindly copying old Boot 3.x dependencies. In configuration unit tests, attach the Spring Security filter chain to MockMvc; never use `standaloneSetup` without filters and conclude an endpoint is secure.

### Reactive Tests

With WebFlux, use `WebTestClient` and `spring-security-test`/reactor-test as appropriate:

~~~java
// Illustrative fragment, requires WebTestClient bound to app security.
webTestClient.get().uri("/public")
    .exchange()
    .expectStatus().isOk();

webTestClient.get().uri("/admin")
    .headers(h -> h.setBasicAuth("learner", "learner-demo-123"))
    .exchange()
    .expectStatus().isForbidden();

webTestClient.get().uri("/admin")
    .headers(h -> h.setBasicAuth("admin", "admin-demo-123"))
    .exchange()
    .expectStatus().isOk();
~~~

If bound directly to a controller without integrating security WebFilters, results can be **false positives**. Run at least one test suite against real security auto-configuration or chain beans, verifying routes and custom filters/claims.

## 18. Debugging: Seeing 401, 403, 404, or Bean Creation Failures?

### Diagnostic Procedure

1. Is the app's **WebApplicationType** Servlet or Reactive? Check dependencies, embedded server logs, and whether `DispatcherServlet` or `DispatcherHandler` is used.
2. Was the right type of security bean created? `SecurityFilterChain` uses `HttpSecurity`, `SecurityWebFilterChain` uses `ServerHttpSecurity`.
3. Does the request match a **chain matcher**? With multiple chains, check `@Order`, prefixes, and fallback.
4. If the chain matches, which authorization rule is chosen? Are `requestMatchers`/`pathMatchers` ordered properly?
5. Which HTTP authentication mechanism is active? Basic, form login, bearer, OAuth2; are credentials/issuer/decoder configured properly?
6. Is CSRF blocking an unsafe HTTP method before the controller runs?
7. Is CORS preflight requiring auth due to misordered configuration?
8. Did the request reach the controller? A 404 may mean no route exists, not a security failure.
9. Is method security, an owner/tenant rule, or an exception handler adding a 403?
10. Are reverse proxies, gateways, TLS, forwarded headers, or multiple contexts altering URLs/paths/Authorization?

### Common Errors Table

| Symptom | Likely Cause | Resolution |
| --- | --- | --- |
| `SecurityFilterChain` bean unused in WebFlux | Wrong stack type | Use `SecurityWebFilterChain`/`ServerHttpSecurity` |
| `SecurityWebFilterChain` bean does not handle MVC | Running on Servlet | Use `SecurityFilterChain`/`HttpSecurity` |
| App added WebFlux dependency yet still runs Servlet | MVC starter present; Boot prioritizes MVC | Explicitly choose web application type and starters |
| `/admin` unexpectedly public | Broad `permitAll` rule placed first | Put specific rules first; test matchers |
| A URL bypasses Spring Security | No chain matched and fallback missing | Add an `authenticated`/`denyAll` fallback |
| `@Order(1)` API chain matched, fallback never runs | First-match behavior is expected | Place policy inside the selected API chain |
| 401 despite sending Basic | Wrong password, encoder mismatch, `httpBasic` not enabled | Check encoder, `AuthenticationProvider`, HTTPS |
| 403 on POST while GET succeeds | Missing CSRF token or authorization denied | Check CSRF config/token and permissions |
| 302 instead of 401 for anonymous | Form login entry point active | Choose auth mechanism suited to API |
| USER has `ADMIN` string yet `hasRole("ADMIN")` fails | Missing `ROLE_` prefix in authorities | Use `roles("ADMIN")` or appropriate `hasAuthority` |
| Browser reports CORS while cURL works | Preflight/CORS/headers mismatch | Configure CORS properly and test OPTIONS |
| Reactive principal empty in custom thread | Lost Reactor Context or wrong ThreadLocal use | Use `ReactiveSecurityContextHolder`/`ServerWebExchange` |
| Custom filter runs twice in MVC | Registered in both Servlet and Security | Register in only one place or disable auto-registration |
| Changed matcher yet Actuator stays public | Separate management context/chain | Check actuator exposure/security separately |
| Unit test returns 200, prod returns 403 | Test did not attach security filters | Use security-aware MockMvc/WebTestClient |
| Disabled CSRF site-wide to fix Postman | Unnecessary security trade-off | Adjust only when threat model confirms |
| Tenant data leaked despite authenticated | Missing object-level authorization | Check owner/tenant in service/repository |
| WebFlux custom filter blocks on JDBC | Blocks event loop and increases latency | Use non-blocking I/O or offload properly |

### Debug Logging

~~~properties
# Enable only in controlled test/debug environments.
logging.level.org.springframework.security=DEBUG
~~~

DEBUG can print Servlet filter lists and decision details in several layers. During deep debugging, TRACE can be expensive and leak metadata; do not leave it enabled in production. Never log Basic Authorization headers, JWTs, passwords, session cookies, or OAuth2 refresh tokens.

You can inspect Actuator beans/conditions when properly authorized, though management endpoints can leak configuration if exposed publicly. Never open `/actuator/beans` on the internet just to inspect chains.

## 19. Migrating from MVC to WebFlux: Migration Checklist

Do not treat migration as a find-and-replace from `SecurityFilterChain` to `SecurityWebFilterChain`. At a minimum, check:

1. **Actual web stack:** do not bring `jakarta.servlet.Filter` into a Reactive Netty server.
2. **URLs/matchers:** Servlet `RequestMatcher` differs from `ServerWebExchangeMatcher`; chain priorities and rules must be rewritten.
3. **Authentication:** synchronous `UserDetailsService`/provider vs `ReactiveUserDetailsService`/reactive manager; never run JDBC/blocking auth on the event loop.
4. **Sessions:** Servlet `HttpSession`/`SecurityContextRepository` differ from `WebSession`/`ServerSecurityContextRepository`.
5. **Security context:** ThreadLocal is not Reactor Context; use reactive method security and appropriate principal APIs.
6. **CSRF/CORS:** DSLs and request matchers differ; do not disable by default.
7. **Filters:** filter ordering, interfaces, exception handling, and request body access differ; custom servlet filters must be redesigned.
8. **JWT/OAuth2:** choose reactive decoders/authorization managers; verify issuer, audience, clock skew, and keys.
9. **Methods:** in WebFlux, services calling blocking repositories must offload; custom auth code must avoid `.block()`.
10. **Tests:** replace MockMvc with `WebTestClient` where appropriate, ensuring real security filters are bound.
11. **Error contract:** compare 401/403/302, headers, `WWW-Authenticate`, CSRF errors, and CORS preflight.
12. **Object-level rules:** ownership/tenant checks must remain intact regardless of stack.

If an application primarily uses blocking JDBC/JPA and Servlet MVC meets your needs, **there is no reason to switch to WebFlux just to use `SecurityWebFilterChain`**. Servlet `SecurityFilterChain` is the right choice for MVC—neither “outdated” nor less secure simply because its API is synchronous.

## 20. Self-Check Questions with Answers

**A.** Can you declare `@Bean SecurityFilterChain` in a WebFlux app running on Reactor Netty and expect Spring Security to protect the WebFilter pipeline?

**Answer:** No. Servlet `SecurityFilterChain` uses `HttpSecurity`/`jakarta.servlet.Filter`; WebFlux uses `SecurityWebFilterChain`/`ServerHttpSecurity` and `WebFilter`.

**B.** An app has Chain A with `securityMatcher("/api/**")` order=1 and fallback Chain B order=2. A user calls `/api/admin` without permission. Will B be tried?

**Answer:** No. A already matched; authorization in A rejects it and does not fall back to B. Adjust A's rules rather than relying on B.

**C.** Can `requestMatchers("/api/**").permitAll()` be placed before `requestMatchers("/api/admin/**").hasRole("ADMIN")`?

**Answer:** No, if you intend to protect admin; the broad rule will match first. Put the specific admin rule first, and the fallback last.

**D.** Which authority does `hasRole("ADMIN")` expect?

**Answer:** By convention, `ROLE_ADMIN`. `roles("ADMIN")` generates the corresponding authority; to check a different exact string, use `hasAuthority`.

**E.** Why can an HTTP POST with valid Basic username/password still fail with 403?

**Answer:** Default CSRF protection can require a token for unsafe methods; 403 does not necessarily mean wrong password or role. Check CSRF and auth rules before disabling any protection.

**F.** Should a reactive controller call `SecurityContextHolder.getContext()` inside a `flatMap` to read the user?

**Answer:** Do not rely on ThreadLocal as the source of truth in a reactive context. Use `ReactiveSecurityContextHolder.getContext()` or `ServerWebExchange.getPrincipal()`.

**G.** When adding both MVC and WebFlux starters to Spring Boot, will the app definitely use `SecurityWebFilterChain`?

**Answer:** No. Boot normally prioritizes the Servlet MVC application type when both are present; check runtime/dependencies rather than inferring from the presence of `WebClient`.

**H.** Should you use `permitAll()` for public assets instead of ignoring the security filter chain completely?

**Answer:** Usually yes. `permitAll` preserves appropriate filters/headers, whereas bypassing completely may skip other protective layers.

**I.** Why is `authenticated()` on `GET /orders/123` not enough to ensure safe data access?

**Answer:** Authentication only verifies the caller; authorization must check object/tenant permissions. User A should not automatically be able to read User B's order.

**J.** Do CORS and CSRF replace each other?

**Answer:** No. CORS governs a browser's cross-origin request/response reading permissions by policy; CSRF protects operations using automatically sent credentials. Both must be analyzed.

## 21. Official Documentation

- [Spring Security — Servlet Security Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html) — `DelegatingFilterProxy`, `FilterChainProxy`, `SecurityFilterChain`, and filter ordering.
- [Spring Security — Servlet Java Configuration](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html) — `HttpSecurity`, multiple chains, `securityMatcher`, and `requestMatchers`.
- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html) — authorization rules, `permitAll`, `hasRole`.
- [Spring Security — WebFlux Security Configuration](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html) — `ServerHttpSecurity`, `SecurityWebFilterChain`, multiple chains.
- [Spring Security — Reactive Authorization and Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html) — `ReactiveSecurityContextHolder` and `@EnableReactiveMethodSecurity`.
- [Spring Security — CSRF in Servlet Applications](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html).
- [Spring Security — CSRF in WebFlux Applications](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html).
- [Spring Security — CORS for Servlet](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html).
- [Spring Security — CORS for Reactive](https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html).
- [Spring Boot — Spring Security for Servlet and WebFlux](https://docs.spring.io/spring-boot/reference/web/spring-security.html).
- [Spring Boot — Starter and Build Systems](https://docs.spring.io/spring-boot/reference/using/build-systems.html).
- [Spring Security — Servlet Path Matching CVE-2026-22753](https://spring.io/security/cve-2026-22753/) — note that Spring Security versions 7.0.0–7.0.4 are affected under specific conditions; use a patched version.

**Conclusion:** `SecurityFilterChain` is the **Servlet MVC** mechanism and `SecurityWebFilterChain` is the **WebFlux reactive** mechanism. Both stacks share the concepts of prioritized chains, authentication, and authorization, yet their filters, matchers, contexts, and builders differ. Ensure a **fallback protects all routes**, place specific rules before broad ones, keep CSRF/CORS aligned with the right model, enforce object-level permissions, and run integration tests with real security filters.