# Servlet and Reactive Execution Models in the Spring Security Ecosystem

## 1. Same Security Goals, Different HTTP Processing

Spring Security is the toolkit for authentication, authorization, and protecting Java applications. In the Spring ecosystem, a web application can run on the **Servlet stack** (typically Spring MVC) or the **reactive stack** (Spring WebFlux). Both share concepts like `Authentication`, `GrantedAuthority`, `SecurityContext`, `PasswordEncoder`, the principle of blocking unauthorized access before reaching business logic, and mechanisms such as HTTP Basic, OAuth2 Resource Server, and CSRF protection. However, **filters, configuration, how identity is retrieved, and asynchronous contracts differ**.

- **Servlet/MVC:** a processing model based on the Servlet API, using `HttpServletRequest`, `HttpServletResponse`, and `Filter` instances. Requests typically execute on a container thread across most of their synchronous lifecycle, though Spring MVC also supports asynchronous processing.
- **Reactive/WebFlux:** built on `Publisher`, `Mono`, `Flux`, `ServerWebExchange`, and `WebFilter`. Processing is a potentially asynchronous, non-blocking pipeline using fewer threads to serve many connections *when I/O components are also non-blocking*. WebFlux can run on Reactor Netty or other supported servers.

**Key point:** "Servlet" and "reactive" here are two HTTP execution models of the *same security ecosystem*, not two independent authorization systems or two ways to hash passwords. Reactive also does not automatically mean faster or more secure.

## 2. Request Flow and Where Spring Security Participates

### 2.1. Servlet Stack

~~~text
Client
  -> Servlet container (Tomcat/Jetty...)
  -> DelegatingFilterProxy
  -> FilterChainProxy (Spring Security)
  -> matching SecurityFilterChain, containing ordered Servlet Filters
  -> DispatcherServlet -> Spring MVC Controller -> Service
  -> HTTP response
~~~

`DelegatingFilterProxy` bridges the Servlet container world to a Spring bean. `FilterChainProxy` selects **the first `SecurityFilterChain` matching the request**; filters inside the chain perform tasks such as loading/saving the security context as configured, authenticating credentials, handling exceptions, and checking permissions before entering the controller. With multiple chains, order and `securityMatcher` determine which chain protects each URL. Do not treat `requestMatchers` inside authorization rules as a substitute for chain selection.

The typical configuration API is **`HttpSecurity` -> `SecurityFilterChain`**, with `authorizeHttpRequests`, `requestMatchers`, `httpBasic`, `formLogin`, `csrf`, and `oauth2ResourceServer`. For synchronous requests, code typically accesses `SecurityContextHolder`; the default strategy uses `ThreadLocal`, and Spring Security manages clearing the context after the request. Do not assume by default that this context automatically propagates to every thread spawned manually by the application.

### 2.2. Reactive Stack

~~~text
Client
  -> HTTP server (e.g., Reactor Netty)
  -> WebFilterChainProxy (Spring Security)
  -> matching SecurityWebFilterChain, containing WebFilters
  -> DispatcherHandler / WebFlux handler
  -> Mono/Flux and asynchronous I/O operations
  -> HTTP response when publisher completes
~~~

Spring Security WebFlux places `WebFilter` instances into `SecurityWebFilterChain`; these are **not** `jakarta.servlet.Filter`. The typical configuration is **`ServerHttpSecurity` -> `SecurityWebFilterChain`**, with `authorizeExchange`, `pathMatchers`, `httpBasic`, `csrf`, and reactive-specific APIs.

The authenticated identity is placed into the **Reactor Context** of the processing pipeline, accessed via `ReactiveSecurityContextHolder`. This fits the fact that `Mono`/`Flux` stages can execute on different threads; relying on `ThreadLocal` in reactive code can cause lost or wrong security contexts. Reactive Security processes the publisher chain upon subscription; simply creating a `Mono` does not mean the logic inside has run.

### 2.3. Quick Comparison

| Aspect | Servlet / Spring MVC | Reactive / Spring WebFlux |
| --- | --- | --- |
| HTTP abstraction | `HttpServletRequest` / `HttpServletResponse` | `ServerWebExchange` |
| Security filter mechanism | `FilterChainProxy`, `SecurityFilterChain`, Servlet `Filter` | `WebFilterChainProxy`, `SecurityWebFilterChain`, `WebFilter` |
| Configuration DSL | `HttpSecurity`, `authorizeHttpRequests` | `ServerHttpSecurity`, `authorizeExchange` |
| Path matching | `requestMatchers("/api/**")` | `pathMatchers("/api/**")` |
| Retrieving identity | `SecurityContextHolder` (default `ThreadLocal`) | `ReactiveSecurityContextHolder` (Reactor Context) |
| User lookup service | `UserDetailsService` | `ReactiveUserDetailsService` |
| Authentication manager | `AuthenticationManager` / `AuthenticationProvider` | `ReactiveAuthenticationManager` |
| Method-level permissions | `@EnableMethodSecurity`, `@PreAuthorize` | `@EnableReactiveMethodSecurity`, `@PreAuthorize` on publishers |
| Common web testing | `MockMvc` | `WebTestClient` |
| I/O fit | Traditional blocking JDBC/JPA, APIs, and SDKs | End-to-end reactive I/O such as `WebClient`, R2DBC, reactive drivers |

The table describes typical APIs. Servlet also has async mechanisms; WebFlux does not guarantee non-blocking behavior if code inside still calls JDBC, `Thread.sleep`, or `block()`.

## 3. Shared Parts: Authentication, Authorization, and Context

1. **Authentication** describes the subject and authorities after verification; for instance, user "alice" has `ROLE_USER`. `hasRole("ADMIN")` checks for authority `ROLE_ADMIN` by default.
2. **Authentication** answers "Who is calling?". **Authorization** answers "Is that person allowed to perform this operation?". Authentication can succeed and still produce HTTP 403.
3. **SecurityContext** holds the active `Authentication`; how the context is *stored and propagated* differs by stack. Do not use `SecurityContextHolder.getContext()` as a general way to read identity inside a reactive pipeline.
4. **401 Unauthorized** usually means the client lacks valid authentication credentials; **403 Forbidden** means access is denied despite authentication or due to another defense like CSRF. Challenge headers and response bodies vary by configured mechanism.
5. Both stacks support sessions and can implement stateless token-based APIs. Servlet typically integrates `HttpSession`, while WebFlux has `WebSession`; **choosing stateless vs. session is a separate architectural decision**, not dictated automatically by the stack name.

Example of reading identity in a Servlet service already inside a security context:

~~~java
String username = SecurityContextHolder.getContext()
    .getAuthentication()
    .getName();
~~~

This is an excerpt placed inside an authenticated method; to compile it requires importing `org.springframework.security.core.context.SecurityContextHolder`. In WebFlux, the corresponding representation is a publisher:

~~~java
Mono<String> username = ReactiveSecurityContextHolder.getContext()
    .map(context -> context.getAuthentication().getName());
~~~

This is also an excerpt, requiring imports for `reactor.core.publisher.Mono` and `org.springframework.security.core.context.ReactiveSecurityContextHolder`; the publisher must be returned or chained into a pipeline carrying the security context. Calling `subscribe()` manually to extract a value and assign an external variable is a common design mistake.

## 4. Hands-On: The Same Security Policy on Two Runtimes

We build **two separate Spring Boot projects**, both having three endpoints: `GET /public` requiring no login, `GET /me` requiring login, and `GET /admin` requiring the ADMIN role. To stay focused on the runtime, both projects use HTTP Basic and in-memory accounts. Only use the example passwords below when running locally for study; real deployments must store secure hashes, enforce HTTPS, and choose an appropriate user store.

Requirements: **JDK 17+**, **Maven 3.9+**. The example uses Spring Boot **3.3.5**, part of the Spring Security 6.x line. Create two independent directories `servlet-demo` and `reactive-demo`. Each directory has one `pom.xml` and one Java file as instructed.

### 4.1. Maven for Servlet

Create `servlet-demo/pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>security-runtime-demo</artifactId>
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

Create `servlet-demo/src/main/java/demo/servlet/ServletApp.java`:

~~~java
package demo.servlet;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ServletApp {
    public static void main(String[] args) {
        SpringApplication.run(ServletApp.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
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
                .password(encoder.encode("secret"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin-secret"))
                .roles("ADMIN")
                .build()
        );
    }
}

@RestController
class ServletEndpoints {
    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/me")
    String me() {
        return SecurityContextHolder.getContext()
            .getAuthentication().getName();
    }

    @GetMapping("/admin")
    String adminPage() {
        return "admin";
    }
}
~~~

In `servlet-demo`, run `mvn spring-boot:run`. `SecurityFilterChain` is the security configuration bean used by Spring Boot for the Servlet runtime. Here `/public` permits anonymous access; `/admin` checks the role; remaining paths require a valid user. `httpBasic` reads credentials from the request; `formLogin` is intentionally disabled so API responses are easy to observe. CSRF stays at Spring Security's default and the demo only uses GET.

### 4.2. Maven for WebFlux

Create `reactive-demo/pom.xml` using **the entire** Maven content from section 4.1, replacing **only** the `spring-boot-starter-web` artifact with `spring-boot-starter-webflux`. Keep `spring-boot-starter-security`. That gives an isolated WebFlux project without mixing both web starters in the same application.

Create `reactive-demo/src/main/java/demo/reactive/ReactiveApp.java`:

~~~java
package demo.reactive;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class ReactiveApp {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveApp.class, args);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/public").permitAll()
                .pathMatchers("/admin").hasRole("ADMIN")
                .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
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
                .password(encoder.encode("secret"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin-secret"))
                .roles("ADMIN")
                .build()
        );
    }
}

@RestController
class ReactiveEndpoints {
    @GetMapping("/public")
    Mono<String> publicPage() {
        return Mono.just("public");
    }

    @GetMapping("/me")
    Mono<String> me() {
        return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication().getName());
    }

    @GetMapping("/admin")
    Mono<String> adminPage() {
        return Mono.just("admin");
    }
}
~~~

In `reactive-demo`, run `mvn spring-boot:run` once the Servlet app has stopped (both use the default port 8080). The authorization policy matches Servlet, but configuration goes through `ServerHttpSecurity`, `SecurityWebFilterChain`, and identity comes from Reactor Context. `MapReactiveUserDetailsService` serves the learning example with in-memory reactive lookup; using a real reactive database requires that repositories, connections, and participating libraries also support non-blocking execution.

### 4.3. Test Requests and Compare Results

Run the same set of commands against **each** application on port 8080:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/me
curl -i -u alice:secret http://localhost:8080/me
curl -i -u alice:secret http://localhost:8080/admin
curl -i -u admin:admin-secret http://localhost:8080/admin
~~~

| Request | Expected HTTP status | Response content on success |
| --- | --- | --- |
| `GET /public`, no credentials | 200 | `public` |
| `GET /me`, no credentials | 401 | May have empty body or error body depending on config |
| `GET /me`, Alice | 200 | `alice` |
| `GET /admin`, Alice with only USER | 403 | Error body depends on config |
| `GET /admin`, Admin with ADMIN | 200 | `admin` |

Server-generated headers (date, content type, `WWW-Authenticate` challenge, etc.) may differ; **what must be verified is the status and body listed in the table**. The security behavior is equivalent, even though Servlet processes over a Servlet Filter chain while WebFlux uses a reactive WebFilter chain.

## 5. When to Use Which API and Pattern?

**Path-based authorization.** Use `authorizeHttpRequests`/`requestMatchers` for Servlet, and `authorizeExchange`/`pathMatchers` for WebFlux. With multiple chains, declare chain-selection matchers and ordering explicitly; always verify that a chain covers remaining endpoints so no security gaps arise.

**Service-level authorization.** Spring Security supports annotations such as `@PreAuthorize("hasAuthority('SCOPE_read')")` in both stacks, but the right mechanism must be enabled: `@EnableMethodSecurity` for Servlet/imperative and `@EnableReactiveMethodSecurity` for reactive. In reactive apps, apply checks on services returning `Mono`/`Flux` and use the reactive context. Do not confuse method security with automatically protecting every URL; combine it with HTTP security.

**Authentication integration.** Servlet typically uses `UserDetailsService` and `AuthenticationManager`; reactive uses `ReactiveUserDetailsService` and `ReactiveAuthenticationManager`. OAuth2/OIDC/JWT capabilities exist on both stacks, yet classes, signatures, and chain wiring must match the stack. Running a blocking authentication library directly on the event loop negates reactive benefits.

**CSRF and state.** CSRF is specifically an issue for requests using browser-auto-attached credentials (such as cookies/sessions). HTTP Basic in a browser can also be sent automatically, so **do not disable CSRF merely because endpoints return JSON or use HTTP Basic**. For APIs genuinely using bearer tokens placed in the Authorization header by the client without auto-sent credentials, you can evaluate CSRF policy per threat model. Both Servlet and WebFlux support configuring this; the learning apps above keep default CSRF and only expose GET.

**CORS, HTTPS, sessions, exception handling.** Both stacks require explicit decisions on cross-origin callers, TLS, sessions/tokens, 401/403 handling, and safe logging. CORS does not replace authentication or authorization. If using bearer JWTs, clearly define issuer, audience, algorithm, token lifecycle, and server-side permission handling; switching stacks does not solve those decisions.

## 6. Choosing a Stack Based on Your System's I/O Flow

- Choose **Servlet/MVC** when the system uses many blocking libraries (typically JPA/JDBC), already has MVC controllers/filters, and the team is comfortable with imperative processing. This fits many CRUD applications well; you do not need reactive just to serve many users.
- Choose **WebFlux** when the flow from HTTP through external APIs, databases, and message clients is predominantly non-blocking, needs to handle high concurrent connections, and requires control over asynchronous pipelines. Measure latency/throughput under realistic workloads, including CPU demand and backpressure.
- If a blocking library must be called from WebFlux, offloading to a dedicated scheduler can prevent blocking the event loop in certain cases, but **does not turn a blocking library into a non-blocking one**; measure resources and avoid overuse.
- Adding `spring-boot-starter-webflux` to an app that already has `spring-boot-starter-web` **usually causes Spring Boot to still auto-configure Spring MVC**, since the WebFlux starter can also be included solely for `WebClient`. To run an actual reactive HTTP application, set web application type and dependencies intentionally.
- A controller returning `Mono` in MVC, or calling `WebClient` from an MVC service, **does not convert the Servlet security chain into a reactive chain**.

## 7. Common Mistakes and How to Check

1. **Using the wrong DSL/filter for the runtime:** A `SecurityFilterChain(HttpSecurity)` bean does not replace `SecurityWebFilterChain(ServerHttpSecurity)`. When rules appear not to run, check which starter is used and whether Boot starts MVC or WebFlux.
2. **Reading the user via ThreadLocal in WebFlux:** `SecurityContextHolder` may be empty or hold the wrong context after asynchronous steps. Use `ReactiveSecurityContextHolder` inside the pipeline, or inject the principal via WebFlux-appropriate mechanisms.
3. **Blocking the event loop:** `block()`, `Thread.sleep()`, and blocking JDBC inside WebFlux can stall throughput even when controllers return `Mono`. Inspect I/O call stacks, threads, and real wait times.
4. **Confusing 401 with 403:** missing credentials or wrong passwords typically yield 401; valid credentials lacking a role typically yield 403. Inspect both the authentication path and permission rules before changing config.
5. **Blanket-disabling CSRF:** retain defenses matching how browsers/clients send credentials, especially with cookies/sessions.
6. **Configuring multiple chains and missing URLs:** matchers and order determine which chain is chosen. Write tests for public URLs, protected URLs, admin URLs, and URLs matching no specific rule.
7. **Relying on @PreAuthorize without enabling method security:** annotations can silently have no effect if `@EnableMethodSecurity` / `@EnableReactiveMethodSecurity` is missing.
8. **Comparing performance by buzzwords:** WebFlux carries costs in building, observing, and debugging pipelines; effectiveness must be verified against load, I/O, memory, and concrete deployment needs.

## 8. Post-Lesson Self-Check

- Describe the path of a request before reaching a controller on Servlet and on WebFlux; name both security chain types.
- Explain why Reactor Context is suitable for storing identity in a pipeline instead of relying solely on `ThreadLocal`.
- From the test table, state the difference between an unauthenticated request and an authenticated request lacking the ADMIN role.
- If an application uses Spring MVC, JPA, and `WebClient`, explain why that application has not become a reactive web server.
- When migrating from MVC to WebFlux, list the configuration APIs, security context accessors, user services, and I/O types that must be reviewed.

## 9. Official Documentation

- Spring Security — Servlet architecture: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security — Servlet authentication architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — WebFlux security configuration: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security — Reactive method security: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
- Spring Boot — Reactive Web Applications: https://docs.spring.io/spring-boot/reference/web/reactive.html
