# Distinguishing Reactive Security Filters from Servlet Filters in Spring Security

## 1. Lesson Objectives

Spring Security has two different HTTP integration models:

- **Servlet stack (typically Spring MVC)**: requests pass through a Servlet Filter managed by the Servlet container. Spring Security hooks in via DelegatingFilterProxy and FilterChainProxy; SecurityFilterChain is configured with HttpSecurity.
- **Reactive stack (Spring WebFlux)**: requests pass through a WebFilter in a Publisher-based processing chain. Spring Security hooks in via WebFilterChainProxy and SecurityWebFilterChain; configured with ServerHttpSecurity.

Both models can handle authentication, authorization, CSRF/CORS protection, adding security headers, and 401/403 error handling. However, they **do not share the same filter interfaces, request/response types, context propagation, or configuration DSL**.

This lesson helps you:

1. Identify whether you are running Servlet or WebFlux.
2. Read the filter execution flow in each stack.
3. Distinguish ordinary HTTP filters from Spring Security filters.
4. Configure reactive security chains properly.
5. Read Authentication from the Reactor Context instead of relying on ThreadLocal.
6. Migrate a Servlet Filter to a WebFilter without blocking the event loop.
7. Verify ordering, 401/403 responses, CORS/CSRF, and access control with WebTestClient.
8. Avoid pitfalls around double registration, context loss, blocking, and filter order.

## 2. Two HTTP Processing Architectures

### 2.1. Servlet: Requests Flow Through FilterChain

Typical model with Spring MVC:

~~~text
HTTP request
    |
    v
Servlet container (Tomcat/Jetty/Undertow)
    |
    v
jakarta.servlet.Filter(s)
    |
    v
DelegatingFilterProxy
    |
    v
Spring Security FilterChainProxy
    |
    v
Select a matching SecurityFilterChain
    |
    v
Configured security Filters in order
    |
    v
DispatcherServlet -> Controller
    |
    v
HTTP response returns through the filter chain
~~~

The Servlet container is responsible for calling Filter#doFilter. A filter can process before/after chain.doFilter or short-circuit the request by not invoking the chain.

Spring Security does not require each security filter to be registered directly with the container. DelegatingFilterProxy bridges the Servlet container lifecycle to a Spring-managed Filter bean; FilterChainProxy selects the security chain and runs the filters inside it.

### 2.2. WebFlux: Requests Flow Through WebFilterChain

WebFlux model (for example running on Reactor Netty):

~~~text
HTTP request
    |
    v
Reactive HTTP server -> HttpHandler
    |
    v
WebFilter(s) + WebFilterChain
    |
    v
Spring Security WebFilterChainProxy
    |
    v
Select a matching SecurityWebFilterChain
    |
    v
Configured security WebFilters in order
    |
    v
DispatcherHandler -> Handler/Controller/RouterFunction
    |
    v
Mono<Void> completes or emits an error
~~~

There is no requirement to go through a Servlet container or DispatcherServlet. WebFilter receives a ServerWebExchange and returns a Mono<Void>, so execution can continue asynchronously upon subscription.

**Core point:** Servlet Filter and WebFilter share the idea of intercepting before/after a request, but belong to two different execution models. You cannot swap interface names and keep the same threading/context management.

## 3. Key Comparison Table

| Aspect | Servlet / Spring MVC | Reactive / Spring WebFlux |
| --- | --- | --- |
| HTTP entry point | Servlet container, DispatcherServlet | HttpHandler, DispatcherHandler |
| HTTP filter | jakarta.servlet.Filter | org.springframework.web.server.WebFilter |
| Method | void doFilter(ServletRequest, ServletResponse, FilterChain) | Mono<Void> filter(ServerWebExchange, WebFilterChain) |
| Invoke next step | chain.doFilter(request, response) | chain.filter(exchange) |
| Request object | HttpServletRequest | ServerHttpRequest via ServerWebExchange |
| Response object | HttpServletResponse | ServerHttpResponse via ServerWebExchange |
| Security proxy | FilterChainProxy | WebFilterChainProxy |
| Proxy bridge | DelegatingFilterProxy | Does not use Servlet DelegatingFilterProxy |
| Security chain | SecurityFilterChain | SecurityWebFilterChain |
| Configuration DSL | HttpSecurity | ServerHttpSecurity |
| URL authorization | authorizeHttpRequests / requestMatchers | authorizeExchange / pathMatchers |
| Chain selection | RequestMatcher / securityMatcher | ServerWebExchangeMatcher / securityMatcher |
| Authentication service | AuthenticationManager, AuthenticationProvider | ReactiveAuthenticationManager and reactive adapters |
| Security context | SecurityContextHolder, typically ThreadLocal | ReactiveSecurityContextHolder, Reactor Context |
| Security context repository | SecurityContextRepository | ServerSecurityContextRepository |
| HTTP entry point when unauthenticated | AuthenticationEntryPoint | ServerAuthenticationEntryPoint |
| Access denied handler | AccessDeniedHandler | ServerAccessDeniedHandler |
| HTTP testing | MockMvc or HTTP client | WebTestClient |
| Threading | Typically request thread; Servlet async depending on config | Non-blocking Publisher; execution may switch threads |
| Blocking I/O | May fit depending on pool design | Avoid blocking event loop; requires reactive driver or isolated blocking |

Clues in code:

- HttpSecurity and SecurityFilterChain present → configuring security for **Servlet**.
- ServerHttpSecurity and SecurityWebFilterChain present → configuring security for **WebFlux**.
- javax.servlet.Filter from very old code → review packages when upgrading to Jakarta (Spring Framework 6+ uses jakarta.servlet).
- WebClient's ExchangeFilterFunction present → that is a **client-side filter for outgoing HTTP requests**, not a WebFilter protecting incoming server requests.

## 4. Two Interfaces with Different Contracts

### 4.1. Servlet Filter

Servlet API interface:

~~~java
import java.io.IOException;

import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;

public final class TraceServletFilter implements Filter {

    @Override
    public void doFilter(
        ServletRequest request,
        ServletResponse response,
        FilterChain chain
    ) throws IOException, ServletException {
        long startedAt = System.nanoTime();

        try {
            chain.doFilter(request, response);
        }
        finally {
            long elapsedMs =
                (System.nanoTime() - startedAt) / 1_000_000;

            System.out.println("Servlet elapsedMs=" + elapsedMs);
        }
    }
}
~~~

This is a standalone example of a Servlet Filter, **not a class to add to the WebFlux project in section 11**.

chain.doFilter proceeds to the next filter or the target servlet. When downstream returns or throws an exception, the finally block runs on the corresponding call stack. With Servlet async, the lifecycle of the whole request may extend beyond this synchronous execution window, so measuring total duration requires AsyncListener or a corresponding mechanism.

### 4.2. Reactive WebFilter

In WebFlux:

~~~java
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

public final class TraceReactiveWebFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
        ServerWebExchange exchange,
        WebFilterChain chain
    ) {
        return Mono.defer(() -> {
            long startedAt = System.nanoTime();

            return chain.filter(exchange)
                .doFinally(signal -> {
                    long elapsedMs =
                        (System.nanoTime() - startedAt)
                            / 1_000_000;

                    System.out.println(
                        "WebFlux " + signal
                            + " elapsedMs=" + elapsedMs
                    );
                });
        });
    }
}
~~~

Mono.defer ensures timing starts when the pipeline is subscribed; doFinally tracks COMPLETE, ERROR, or CANCEL of the subscription. Do not wrap chain.filter(exchange) in a synchronous try/finally block and assume the response has been measured: the method may merely return an unexecuted Mono.

### 4.3. Rejecting Requests in a WebFilter

If handling the response directly without calling chain.filter(exchange), a filter can terminate the pipeline:

~~~java
public Mono<Void> filter(
    ServerWebExchange exchange,
    WebFilterChain chain
) {
    if (mustReject(exchange)) {
        exchange.getResponse()
            .setStatusCode(HttpStatus.TOO_MANY_REQUESTS);

        return exchange.getResponse().setComplete();
    }

    return chain.filter(exchange);
}
~~~

This is an illustrative snippet requiring mustReject and the HttpStatus import. For **authentication, authorization, or complex rate limiting**, prefer Spring Security mechanisms and battle-tested libraries over writing an ad-hoc filter.

## 5. Servlet Spring Security: DelegatingFilterProxy and FilterChainProxy

In the Servlet stack:

1. The container sees DelegatingFilterProxy as a Servlet Filter.
2. The proxy delegates the request to a Spring-managed Filter bean, typically named springSecurityFilterChain.
3. FilterChainProxy selects a SecurityFilterChain based on RequestMatcher.
4. It runs the security Filters in the selected chain.
5. When permitted, the request proceeds to DispatcherServlet/controller.

Example configuration **only for Servlet/Spring MVC applications**:

~~~java
@Configuration
@EnableWebSecurity
public class ServletSecurityConfiguration {

    @Bean
    SecurityFilterChain servletChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

Typical imports:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.config.Customizer;
~~~

Declaring a Servlet SecurityFilterChain does not protect a WebFlux server running purely on Reactor Netty. They are two different bean types; Spring Boot chooses auto-configuration based on the web application type and classpath.

### 5.1. A Servlet Filter Is Not a Spring Security Filter

A Filter you register with the Servlet container may run **outside** FilterChainProxy. Therefore, @Order or FilterRegistrationBean does not equate to filter ordering **inside** SecurityFilterChain.

In Servlet Security, insert a security Filter into the chain using HttpSecurity.addFilterBefore, addFilterAfter, or addFilterAt at the appropriate position. Avoid both registering a security Filter as a container Filter and inserting it into FilterChainProxy, as it may run twice.

## 6. Reactive Spring Security: WebFilterChainProxy and SecurityWebFilterChain

In WebFlux, Spring Security provides **WebFilterChainProxy**, a WebFilter responsible for selecting a matching SecurityWebFilterChain. Each chain consists of WebFilters handling authentication, authorization, CSRF protection, and other security needs.

Typical configuration:

~~~java
@Configuration
@EnableWebFluxSecurity
public class ReactiveSecurityConfiguration {

    @Bean
    SecurityWebFilterChain security(
        ServerHttpSecurity http
    ) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/public").permitAll()
                .pathMatchers("/admin").hasRole("ADMIN")
                .anyExchange().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

Important classes:

- EnableWebFluxSecurity enables security integration for WebFlux.
- ServerHttpSecurity is the reactive DSL, analogous in role to HttpSecurity in Servlet.
- SecurityWebFilterChain is the chain built for reactive requests.
- WebFilterChainProxy selects a chain based on ServerWebExchangeMatcher.
- AuthenticationWebFilter and AuthorizationWebFilter participate in authentication/authorization steps when the corresponding mechanisms are configured.

A request only goes through **the first matching chain**, not cumulatively through all SecurityWebFilterChain beans. If you want all APIs to apply a common policy, configure that policy in each relevant chain or structure matchers/chains explicitly.

### 6.1. Chain Selection vs. Authorization Rule Selection

~~~java
http.securityMatcher(
    new PathPatternParserServerWebExchangeMatcher("/api/**")
);
~~~

securityMatcher decides **whether this chain applies to the request**.

~~~java
http.authorizeExchange(auth -> auth
    .pathMatchers("/api/public").permitAll()
    .pathMatchers("/api/admin").hasRole("ADMIN")
    .anyExchange().authenticated()
);
~~~

pathMatchers decides **access permissions inside the selected chain**.

Confusing these two levels often causes requests to fall into a fallback chain or accidentally bypass policies. Test at least one URL matching each chain, one non-matching URL, and paths with different permissions.

### 6.2. @Order Exists at Multiple Levels

In WebFlux there are three ordering concepts:

| Level | Controlled by | Purpose |
| --- | --- | --- |
| Application-wide WebFilter | @Order or Ordered on WebFilter bean | Order in the outer WebFilterChain |
| Multiple SecurityWebFilterChains | @Order on the security chain bean | Priority of which chain's matcher is evaluated first |
| WebFilter inside a security chain | SecurityWebFiltersOrder + addFilterAt/Before/After | Relative position of a security WebFilter |

Do not use @Order on a WebFilter bean and assume it sits right after the AUTHENTICATION step inside the security chain. If you need access to the established Authentication, place the filter at the proper position in the security chain or handle it in the service/controller once the Reactor Context is ready.

## 7. SecurityContextHolder vs. ReactiveSecurityContextHolder

This is the most common source of bugs when migrating from Spring MVC to WebFlux.

### 7.1. Servlet: SecurityContextHolder

A typical Servlet application can read:

~~~java
Authentication authentication =
    SecurityContextHolder.getContext()
        .getAuthentication();

String username = authentication.getName();
~~~

By default, SecurityContextHolder uses a ThreadLocal strategy; Spring Security manages attaching and clearing context per request. When code switches threads or uses Servlet async, context propagation still must be handled properly rather than assuming ThreadLocal crosses every executor automatically.

### 7.2. WebFlux: Reactor Context

A reactive pipeline can execute across multiple threads. Spring Security stores SecurityContext in the **Reactor Context** so it travels with the subscription rather than relying solely on ThreadLocal.

Proper way to read it:

~~~java
Mono<String> username =
    ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);
~~~

In a WebFlux controller:

~~~java
@GetMapping("/me")
public Mono<String> me() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);
}
~~~

Do not use SecurityContextHolder.getContext() in WebFlux to infer the current user. It may be empty or hold a value unrelated to the active subscription.

### 7.3. Attaching Context in Reactive Unit Tests

Standalone example:

~~~java
Authentication auth =
    new TestingAuthenticationToken(
        "learner",
        "not-used",
        "ROLE_USER"
    );

Mono<String> name =
    ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(auth)
        );

StepVerifier.create(name)
    .expectNext("learner")
    .verifyComplete();
~~~

This snippet requires imports from Spring Security, Reactor, and reactor-test. contextWrite attaches the SecurityContext to the subscription at the right point in the pipeline.

### 7.4. Do Not Drop the Context

Common mistakes:

- Calling a manual subscribe() inside a filter and returning Mono.empty().
- Offloading work to a CompletableFuture/raw Thread without a context propagation mechanism.
- Using a custom ThreadLocal to store user identity across requests.
- Caching a Mono containing one user's context and reusing it across users.
- Retrieving Authentication during singleton bean initialization instead of inside the request pipeline.

Compose using flatMap, map, defer, and contextWrite in the right places. When bridging to another async library is unavoidable, evaluate context propagation and test with concurrent requests.

## 8. Placing a Custom Security WebFilter Properly

When a custom security step is required, a WebFilter can be added to SecurityWebFilterChain:

~~~java
@Bean
SecurityWebFilterChain security(
    ServerHttpSecurity http
) {
    WebFilter audit = (exchange, chain) ->
        ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .doOnNext(auth ->
                logger.debug(
                    "Authenticated principal={}",
                    auth.getName()
                )
            )
            .then(chain.filter(exchange));

    return http
        .authorizeExchange(auth -> auth
            .anyExchange().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .addFilterAfter(
            audit,
            SecurityWebFiltersOrder.AUTHENTICATION
        )
        .build();
}
~~~

This is an **illustrative snippet**: it requires a logger and imports, and does not replace the complete configuration class in section 11. Here, audit lives inside the security chain after the AUTHENTICATION position. It is not a global WebFilter bean.

In production:

- Do not log tokens, passwords, or sensitive principal data.
- Do not manually construct an Authentication with authenticated=true just because an arbitrary header is present.
- If custom authentication is needed, use ReactiveAuthenticationManager, ServerAuthenticationConverter/AuthenticationWebFilter, and standard error handling.
- If authorization is needed, use authorizeExchange/ReactiveAuthorizationManager or reactive method security instead of an arbitrary custom if check.
- Do not register the same filter both as a global WebFilter bean and via addFilterAt/After; the filter may execute twice.

### 8.1. A Custom Global WebFilter Is a Different Concept

A global WebFilter bean is useful for request IDs, logging, CORS, metrics, or basic limits. It wraps handlers according to its order, but **does not automatically run after Spring Security authentication**.

To read the authenticated Authentication from a filter, do not assume context exists at an arbitrary @Order. Use a custom security WebFilter at the right position or handle it in the service layer with ReactiveSecurityContextHolder.

### 8.2. WebFilter vs. HandlerFilterFunction

In WebFlux.fn, **HandlerFilterFunction** applies only within the RouterFunction/functional handler to which that filter is attached. **WebFilter** belongs to the WebFlux HTTP pipeline and can apply broadly across routes. Do not use HandlerFilterFunction to replace full Spring Security protection across all routes.

## 9. Authentication, Authorization, CSRF, CORS, and Errors

### 9.1. Authentication and Authorization

- **Authentication** answers "Who is calling?".
- **Authorization** answers "Is the caller permitted to access this resource?".

In the reactive stack, authentication can be performed asynchronously via ReactiveAuthenticationManager, ReactiveUserDetailsService, or resource server JWT support. Authorization uses the Authentication in the Reactor Context and the security chain's policy.

HTTP Basic is only a demo mechanism. In production, consider OAuth 2.0 Resource Server/JWT, OIDC, session login, or a mechanism suited to your threat model.

### 9.2. HTTP 401 vs. 403

- **401 Unauthorized**: typically occurs when a request requires authentication without valid credentials; the server may return WWW-Authenticate.
- **403 Forbidden**: the principal is authenticated but lacks sufficient permissions, or the request was rejected by another protection rule such as CSRF.

Do not assume every blocked request returns 403. The status depends on the authentication entry point, access-denied handler, and configured policy.

### 9.3. CSRF

Spring Security **enables CSRF protection by default** for unsafe methods, which is especially critical for browser applications using cookies/sessions.

For stateless APIs using bearer tokens actively sent via the Authorization header, a different CSRF policy may be designed after analyzing any credentials automatically attached by browsers. Never disable CSRF by default merely because the application uses WebFlux.

The demo in section 11 only uses GET, so disabling CSRF is unnecessary. If POST/PUT/PATCH/DELETE are added, include CSRF tokens or adjust according to the system's authentication design.

### 9.4. CORS

Browsers send an OPTIONS preflight before certain cross-origin requests. Preflights usually do not carry login cookies. If security blocks the preflight before CORS handles it, the browser may report a CORS error instead of a clear authentication error.

WebFlux provides CorsWebFilter and WebFlux CORS configuration; Spring Security has integrated CORS configuration support. Handle CORS properly before authentication and validate allowed origins, headers, methods, and credentials.

Never use a wildcard origin with credentialed requests. CORS does not replace authentication or authorization.

### 9.5. Security Headers

Spring Security provides defaults for several HTTP security headers, such as nosniff, cache headers, and frame options. When writing custom filters or permitAll routes, avoid inadvertently bypassing security defaults. **permitAll** allows URL access while the request still traverses the security chain; bypassing the entire security chain is a different behavior.

### 9.6. Exception Handling

Servlet uses AuthenticationEntryPoint and AccessDeniedHandler; reactive uses ServerAuthenticationEntryPoint and ServerAccessDeniedHandler. WebFlux can produce responses asynchronously, so errors occurring after the response has committed cannot naturally be turned into a new 401/403 response.

Do not swallow AccessDeniedException or AuthenticationException with onErrorResume(... -> Mono.empty()) when doing so would lose the expected security response.

## 10. Mistakes When Porting a Servlet Filter to WebFlux

### 10.1. Copying a Servlet Filter Verbatim into WebFlux

Incorrect at runtime:

~~~java
@Component
public class LegacySecurityFilter implements jakarta.servlet.Filter {
    // ...
}
~~~

Such a Filter is not part of the pure reactive WebFlux WebFilterChain. Spring Boot running Netty with WebFlux will not invoke Filter#doFilter like a Servlet container. Implement WebFilter when you want to filter incoming WebFlux requests.

### 10.2. Blocking the Event Loop

Do not do this in a WebFilter:

~~~java
public Mono<Void> filter(
    ServerWebExchange exchange,
    WebFilterChain chain
) {
    User user = userRepository.findBlockingUser(); // blocking I/O
    Thread.sleep(100);
    return chain.filter(exchange);
}
~~~

This is an **intentionally wrong** example; the code would also need checked exception handling. Use reactive repositories/drivers:

~~~java
return reactiveUserRepository.findById(userId)
    .flatMap(user -> authorize(user, exchange))
    .then(chain.filter(exchange));
~~~

If a blocking library must be integrated temporarily, you can isolate it with Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic()) and limit concurrency; this workaround does not make blocking I/O non-blocking and does not replace load control.

### 10.3. Calling subscribe() Manually in a Filter

Wrong:

~~~java
public Mono<Void> filter(
    ServerWebExchange exchange,
    WebFilterChain chain
) {
    verifyCredential(exchange).subscribe();
    return chain.filter(exchange);
}
~~~

Verification runs outside the chain and may finish **after** the request has already been allowed through. Errors and cancellations are also disconnected from the main lifecycle.

Proper composition:

~~~java
return verifyCredential(exchange)
    .then(chain.filter(exchange));
~~~

This is an illustrative snippet; ensure verifyCredential actually emits an error or returns a rejection when credentials are invalid. In Spring Security, prefer AuthenticationWebFilter/ReactiveAuthenticationManager over building a custom verification chain.

### 10.4. Attempting to Read Servlet HttpSession

In WebFlux, use ServerWebExchange.getSession() (Mono<WebSession>) when WebSession is needed. Spring Security reactive provides ServerSecurityContextRepository. Do not assume HttpServletRequest, HttpSession, or ServletContext exist on a Netty WebFlux server.

### 10.5. Writing Valid-Looking Config for the Wrong Stack

A SecurityFilterChain(HttpSecurity) does not replace SecurityWebFilterChain(ServerHttpSecurity). When both Spring MVC starter and WebFlux starter are present, Spring Boot typically selects **Servlet MVC** by default; adding WebFlux just to use WebClient does not mean your server is reactive.

Check dependencies and the actual web application type. Do not "add both starters" as a workaround to fix filter issues.

## 11. Runnable Java 17+ Project: Spring WebFlux Security

The example uses **Spring Boot 4.1.2**, Java 17+, Spring WebFlux, and Spring Security. Its purpose is to demonstrate:

- A reactive chain selected for /api/**.
- GET /api/public permitted via permitAll.
- GET /api/me requiring authentication.
- GET /api/admin requiring ROLE_ADMIN.
- Username read from the Reactor Context.
- A global WebFilter used for timing, not replacing Spring Security filters.
- WebTestClient verifying statuses and responses.

The project uses HTTP Basic with demo users and {noop} passwords **for learning purposes only**. Production must use proper password hashing and secret management, HTTPS, real authentication, rate limits, and monitoring.

### 11.1. Structure

~~~text
reactive-security-filters-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/com/example/securityfilters/
    │       ├── SecurityFiltersApplication.java
    │       ├── SecurityConfiguration.java
    │       ├── ApiController.java
    │       └── RequestMetricsWebFilter.java
    └── test/
        └── java/com/example/securityfilters/
            └── SecurityIntegrationTest.java
~~~

### 11.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>reactive-security-filters-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

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
            <artifactId>spring-boot-starter-webflux-test</artifactId>
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

### 11.3. SecurityFiltersApplication.java

~~~java
package com.example.securityfilters;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityFiltersApplication {

    public static void main(String[] args) {
        SpringApplication.run(
            SecurityFiltersApplication.class,
            args
        );
    }
}
~~~

### 11.4. SecurityConfiguration.java

~~~java
package com.example.securityfilters;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfiguration {

    @Bean
    @Order(1)
    SecurityWebFilterChain apiSecurity(
        ServerHttpSecurity http
    ) {
        return http
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher(
                    "/api/**"
                )
            )
            .authorizeExchange(auth -> auth
                .pathMatchers(
                    HttpMethod.GET,
                    "/api/public"
                ).permitAll()
                .pathMatchers(
                    HttpMethod.GET,
                    "/api/admin"
                ).hasRole("ADMIN")
                .anyExchange().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain fallbackSecurity(
        ServerHttpSecurity http
    ) {
        return http
            .authorizeExchange(auth -> auth
                .anyExchange().denyAll()
            )
            .build();
    }

    @Bean
    ReactiveUserDetailsService users() {
        UserDetails learner = User.withUsername("learner")
            .password("{noop}demo-password")
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password("{noop}demo-admin")
            .roles("ADMIN")
            .build();

        return new MapReactiveUserDetailsService(
            learner,
            admin
        );
    }
}
~~~

Explanation:

1. @EnableWebFluxSecurity configures Spring Security WebFlux integration.
2. apiSecurity has @Order(1), matching only /api/** URLs.
3. Inside apiSecurity, /api/public is publicly accessible; /api/admin requires ROLE_ADMIN; remaining /api/** paths require login.
4. fallbackSecurity with @Order(2) applies denyAll to requests outside /api/**.
5. HTTP Basic provides the credential verification mechanism for the demo.
6. In-memory UserDetails is only for unit/integration testing; {noop} passwords are unencrypted and must never be used in production.
7. CSRF is not disabled; the demo application only exposes GET.

Note: hasRole("ADMIN") corresponds to authority ROLE_ADMIN. If using hasAuthority("ADMIN"), the authority must match the exact string ADMIN; do not mix the two approaches without understanding the ROLE_ prefix.

### 11.5. ApiController.java

~~~java
package com.example.securityfilters;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class ApiController {

    @GetMapping("/public")
    public Mono<String> publicMessage() {
        return Mono.just("public");
    }

    @GetMapping("/me")
    public Mono<String> currentUser() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName);
    }

    @GetMapping("/admin")
    public Mono<String> adminMessage() {
        return Mono.just("admin-only");
    }
}
~~~

At the /api/me endpoint, Authentication is read from the Reactor Context inside the Mono pipeline. Servlet's ThreadLocal SecurityContextHolder is not used.

### 11.6. RequestMetricsWebFilter.java

~~~java
package com.example.securityfilters;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class RequestMetricsWebFilter implements WebFilter {

    private static final Logger log =
        LoggerFactory.getLogger(
            RequestMetricsWebFilter.class
        );

    @Override
    public Mono<Void> filter(
        ServerWebExchange exchange,
        WebFilterChain chain
    ) {
        return Mono.defer(() -> {
            long startedAt = System.nanoTime();
            String path =
                exchange.getRequest().getPath().value();

            return chain.filter(exchange)
                .doFinally(signal -> {
                    long elapsedMs =
                        (System.nanoTime() - startedAt)
                            / 1_000_000;

                    log.info(
                        "path={} signal={} elapsedMs={}",
                        path,
                        signal,
                        elapsedMs
                    );
                });
        });
    }
}
~~~

This filter measures HTTP processing time and runs as a global WebFilter. It **does not authenticate users** and does not access the Reactor SecurityContext. Do not log the Authorization header, passwords, raw bodies, or sensitive information.

### 11.7. SecurityIntegrationTest.java

~~~java
package com.example.securityfilters;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webflux.test.autoconfigure.AutoConfigureWebTestClient;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class SecurityIntegrationTest {

    @Autowired
    WebTestClient client;

    @Test
    void publicEndpointAllowsAnonymous() {
        client.get()
            .uri("/api/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public");
    }

    @Test
    void privateEndpointRejectsAnonymousWith401() {
        client.get()
            .uri("/api/me")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void authenticatedLearnerReadsTheirIdentity() {
        client.get()
            .uri("/api/me")
            .headers(headers ->
                headers.setBasicAuth(
                    "learner",
                    "demo-password"
                )
            )
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("learner");
    }

    @Test
    void learnerCannotAccessAdminEndpoint() {
        client.get()
            .uri("/api/admin")
            .headers(headers ->
                headers.setBasicAuth(
                    "learner",
                    "demo-password"
                )
            )
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void adminCanAccessAdminEndpoint() {
        client.get()
            .uri("/api/admin")
            .headers(headers ->
                headers.setBasicAuth(
                    "admin",
                    "demo-admin"
                )
            )
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo(
                "admin-only"
            );
    }
}
~~~

All tests use real HTTP on a random port created by SpringBootTest. This verifies the reactive security chain and HTTP Basic integration end-to-end.

WebTestClient also supports mockUser(), mockJwt(), and csrf() via Spring Security test utilities when bindToApplicationContext or a MockServer exchange has springSecurity() applied. In the end-to-end HTTP tests here, sending real Basic auth credentials to the server is the simplest way to exercise the filter chain.

### 11.8. Running the Project

Requires JDK 17+ and Maven:

~~~bash
mvn clean test
mvn spring-boot:run
~~~

Open another terminal:

~~~bash
curl -i http://localhost:8080/api/public
~~~

Expected output: HTTP 200, body public.

~~~bash
curl -i http://localhost:8080/api/me
~~~

Expected output: HTTP 401 and HTTP Basic challenge.

~~~bash
curl -i -u learner:demo-password \
  http://localhost:8080/api/me
~~~

Expected output: HTTP 200, body learner.

~~~bash
curl -i -u learner:demo-password \
  http://localhost:8080/api/admin
~~~

Expected output: HTTP 403 because learner does not have ROLE_ADMIN.

~~~bash
curl -i -u admin:demo-admin \
  http://localhost:8080/api/admin
~~~

Expected output: HTTP 200, body admin-only.

Additional headers and logs may vary by configuration. The example intentionally does not implement POST writes so CSRF token handling is not needed in these curl commands.

## 12. Testing Security WebFilters Without Starting a Real Server

When you only need to test a SecurityWebFilterChain or controller as a slice, you can use WebTestClient bindToApplicationContext with Spring Security test support:

~~~java
WebTestClient client = WebTestClient
    .bindToApplicationContext(applicationContext)
    .apply(
        SecurityMockServerConfigurers.springSecurity()
    )
    .configureClient()
    .build();
~~~

Then:

~~~java
client.mutateWith(
        SecurityMockServerConfigurers
            .mockUser()
            .roles("ADMIN")
    )
    .get()
    .uri("/api/admin")
    .exchange()
    .expectStatus().isOk();
~~~

This snippet requires a valid test context and the SecurityMockServerConfigurers import. **mockUser() does not execute the real Basic authentication mechanism**; it injects a simulated Authentication into the test pipeline. Use mockUser to test authorization, and use real HTTP credentials in integration tests when you need to test authentication.

Additional important tests:

- Anonymous users cannot enter routes requiring authentication.
- Regular users cannot enter admin routes.
- Admins can access permitted routes.
- The /api/** matcher selects the right chain, and URLs outside the pattern fall into the fallback chain.
- Specific rule ordering before anyExchange is preserved.
- Custom filters are not registered twice.
- POST requests require CSRF with or without a token per the policy.
- OPTIONS preflights are handled per CORS config.
- Authentication inside Mono is not lost across publishOn/flatMap.

## 13. Multi-Chain Setup and Matcher/Order Pitfalls

A WebFlux app may have one chain for APIs and another for web pages:

~~~java
@Bean
@Order(1)
SecurityWebFilterChain api(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            new PathPatternParserServerWebExchangeMatcher(
                "/api/**"
            )
        )
        .authorizeExchange(auth -> auth
            .anyExchange().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}

@Bean
@Order(2)
SecurityWebFilterChain web(ServerHttpSecurity http) {
    return http
        .authorizeExchange(auth -> auth
            .pathMatchers("/", "/login").permitAll()
            .anyExchange().authenticated()
        )
        .formLogin(Customizer.withDefaults())
        .build();
}
~~~

**Only one chain is selected per request.** A request to /api/orders matches api, and does not additionally run through the web chain even though web has a catch-all matcher. If the api chain lacks an appropriate fallback rule, unexpected paths may exist. Therefore, place anyExchange at the end of each chain.

A SecurityWebFilterChain bean is annotated with @Order, whereas using @Order on a global WebFilter does not alter chain selection order. Those two levels are independent.

### 13.1. If You Need to Insert at the Authentication Position

Use the methods on ServerHttpSecurity:

~~~java
http.addFilterBefore(
    customFilter,
    SecurityWebFiltersOrder.AUTHORIZATION
);
~~~

or:

~~~java
http.addFilterAfter(
    customFilter,
    SecurityWebFiltersOrder.AUTHENTICATION
);
~~~

This is a snippet: customFilter must be a WebFilter and registered in only one place. Analyze the purpose before picking an order: a filter needing the authenticated identity must go after the authentication step; a filter making authorization decisions should integrate with standard authorization mechanisms rather than arbitrarily splicing into the chain.

## 14. Debugging and Observing the Security Chain Properly

Steps when encountering puzzling 401/403 errors:

1. Confirm whether the application is truly WebFlux or Servlet.
2. Check whether a SecurityWebFilterChain or SecurityFilterChain bean is active.
3. Confirm which matcher selects the chain; inspect @Order.
4. Inspect authorizeExchange and pathMatchers ordering.
5. Check the authentication method (Basic, bearer, session).
6. Check ReactiveUserDetailsService or ReactiveAuthenticationManager.
7. Check the Reactor Context in Mono/Flux; do not infer from ThreadLocal.
8. Inspect security CSRF/CORS and preflight behavior.
9. Check whether a global WebFilter runs before or after the security proxy.
10. Check whether the response was already committed before an exception handler attempted to change the status.

Enable debug logging only locally in a controlled environment:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Do not enable indiscriminate body/token logging; never log passwords or the Authorization header.

### 14.1. Observing Filter Order

Spring Boot WebFlux auto-configures Spring Security's WebFilterChainProxy at around order -100. A WebFilter bean with @Order(Ordered.HIGHEST_PRECEDENCE) generally runs outside/around this proxy, **not as a security filter after AuthenticationWebFilter**.

If you want to measure the entire request, a global WebFilter is appropriate. If you want to inspect the authenticated principal, use a custom security WebFilter at the right position, a controller, or a reactive service.

### 14.2. Can You Use WebFlux While Still Seeing Servlet Dependencies?

A project can have Servlet-related libraries in its dependency tree while the application actually chooses the reactive web application type. Conversely, when both Spring MVC and WebFlux starters are present, Spring Boot usually prioritizes MVC. Verify the actual web application type rather than guessing from a single dependency.

## 15. Comparing How the Same Security Requirement Is Written

Requirement: all /admin/** requests require role ADMIN, /health is public, and remaining URLs require login.

### 15.1. Servlet

~~~java
@Bean
SecurityFilterChain servletSecurity(HttpSecurity http)
        throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/health").permitAll()
            .requestMatchers("/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

### 15.2. Reactive

~~~java
@Bean
SecurityWebFilterChain reactiveSecurity(
    ServerHttpSecurity http
) {
    return http
        .authorizeExchange(auth -> auth
            .pathMatchers("/health").permitAll()
            .pathMatchers("/admin/**").hasRole("ADMIN")
            .anyExchange().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

The two snippets have similar authorization intent, but **their bean types, DSLs, and runtimes are not the same**. Do not copy a Servlet solution into WebFlux and try to cast types or add Servlet adapters arbitrarily.

## 16. Common Errors and Fixes

| Symptom | Cause | Fix |
| --- | --- | --- |
| jakarta.servlet.Filter does not run on Netty | WebFlux does not use the Servlet filter chain | Implement WebFilter |
| SecurityFilterChain bean does not protect WebFlux requests | Valid API config for the wrong stack | Use SecurityWebFilterChain and ServerHttpSecurity |
| SecurityWebFilterChain bean has no effect in MVC | Application runs on Servlet stack | Use SecurityFilterChain and HttpSecurity |
| SecurityContextHolder returns null in Mono | Using ThreadLocal instead of Reactor Context | Use ReactiveSecurityContextHolder |
| Custom filter does not see principal | Runs too early or outside the security chain | Insert at the right SecurityWebFiltersOrder |
| Filter runs twice | Both global @Component and addFilterAt/After | Register in only one place |
| Request permitted but returns 404 | Security allows it through, but controller/route does not exist | Check handler mapping |
| Regular user can access admin | Wrong matcher/order or missing hasRole | Test ROLE_ADMIN and rules |
| 401 on browser OPTIONS preflight | CORS handled after security | Configure CORS properly before security |
| 403 on POST using cookies | Missing CSRF token | Send token or configure appropriate policy |
| Slow WebFilter slows down other requests | Blocking I/O on the event loop | Use reactive APIs or isolate blocking with concurrency limits |
| Exceptions are lost | Manual subscribe outside the pipeline | Return Mono composition |
| Audit log not written after response | Synchronous try/finally wrong for lifecycle | Use doFinally |
| Strange filter order | Confusing bean @Order with SecurityWebFiltersOrder | Distinguish the three ordering levels |
| Security bypassed on /api/** | securityMatcher does not match and fallback is missing | Check chain matcher/fallback |
| /api/** runs the wrong chain | @Order puts wildcard before specific pattern | Place specific matchers with higher priority |
| User contexts bleed into each other | Broken caching/context propagation | Never store request Authentication in a singleton/ThreadLocal |
| Added both spring-boot-starter-web and webflux and filter does not run | Boot chooses MVC as default server | Choose the stack intentionally and verify web application type |
| 403 turned into 200 | onErrorResume swallows access-denied errors | Let Spring Security handle it or map errors intentionally |
| 401/403 bugs only appear on real server | mockUser tests bypass real authentication | Add integration tests with Basic/JWT/cookies |

## 17. Checklist for Migrating from Servlet to WebFlux

- [ ] Confirm the server runs WebFlux, not MVC.
- [ ] Replace jakarta.servlet.Filter with WebFilter when a reactive HTTP filter is needed.
- [ ] Replace SecurityFilterChain/HttpSecurity with SecurityWebFilterChain/ServerHttpSecurity.
- [ ] Replace DelegatingFilterProxy/FilterChainProxy thinking with the WebFilterChainProxy architecture.
- [ ] Replace RequestMatcher with ServerWebExchangeMatcher at the chain selection level.
- [ ] Use authorizeExchange and pathMatchers, distinguishing them from securityMatcher.
- [ ] Verify @Order across security chains.
- [ ] Place custom security WebFilters using the appropriate SecurityWebFiltersOrder.
- [ ] Do not double-register a global WebFilter as an internal security filter.
- [ ] Replace ThreadLocal SecurityContextHolder with ReactiveSecurityContextHolder.
- [ ] Do not block, sleep, or manually subscribe on the request pipeline.
- [ ] Migrate authentication repositories/services to reactive APIs.
- [ ] Verify 401, 403, CSRF, CORS, and security headers.
- [ ] Verify mockUser tests separately from real HTTP authentication tests.
- [ ] Protect all routes beyond explicitly permitAll URLs.
- [ ] Review resource server/session policies for real deployment.
- [ ] Never keep {noop} demo passwords in production.
- [ ] Write integration tests and ensure logs/metrics contain no secrets.

## 18. Practice Exercises

**Exercise 1 — Identify the stack:** Write a table classifying Filter/HttpSecurity and WebFilter/ServerHttpSecurity into MVC or WebFlux.

**Exercise 2 — Global WebFilter:** Create a WebFilter measuring duration with Mono.defer and doFinally. Check logs when requests return 200, 401, or 403.

**Exercise 3 — SecurityWebFilterChain:** Protect /api/** with HTTP Basic and permit /api/public. Test anonymous and authenticated requests.

**Exercise 4 — Roles:** Create USER and ADMIN, restrict /api/admin with hasRole("ADMIN"). Test 200 and 403.

**Exercise 5 — Reactor Context:** In a controller returning Mono<String>, read the username using ReactiveSecurityContextHolder.

**Exercise 6 — Multi-chain:** Configure @Order(1) for /api/** and @Order(2) for all other URLs. Verify which chain is selected.

**Exercise 7 — Custom security filter:** Place an audit WebFilter after AUTHENTICATION and verify the principal is recorded properly without logging secrets.

**Exercise 8 — Non-blocking:** Replace a blocking lookup in a filter with ReactiveUserDetailsService or a reactive service; verify the pipeline has no block().

**Exercise 9 — CSRF:** Add a POST endpoint relying on cookie sessions, test without and with a CSRF token. Explain why WebFlux does not automatically eliminate CSRF risk.

**Exercise 10 — CORS:** Create an OPTIONS preflight for a cross-origin request with Authorization. Configure CorsWebFilter with proper origin/method/header settings.

**Exercise 11 — mockUser test:** Use WebTestClient mutateWith(mockUser()) to test access rules; compare with HTTP Basic integration tests.

**Exercise 12 — Wrong stack:** Add a jakarta.servlet.Filter to a WebFlux-Netty demo and verify it does not become a WebFilter in the pipeline.

## 19. Key Takeaways

**Servlet security filter ≠ Reactive security filter.** Servlet uses jakarta.servlet.Filter, FilterChainProxy, SecurityFilterChain, and HttpSecurity. WebFlux uses org.springframework.web.server.WebFilter, WebFilterChainProxy, SecurityWebFilterChain, and ServerHttpSecurity.

WebFlux security does not rely on Servlet DelegatingFilterProxy. Each request is matched to **one suitable SecurityWebFilterChain**. securityMatcher selects the chain; pathMatchers/authorizeExchange decides permissions inside the chain. Global WebFilter @Order, security chain @Order, and SecurityWebFiltersOrder are three distinct levels.

In a reactive pipeline, Authentication belongs to the **Reactor Context**. Read it with ReactiveSecurityContextHolder; do not rely on Servlet ThreadLocal as a global assumption. Always return Mono/Flux instead of calling block() or subscribing manually. CSRF, CORS, security headers, 401/403, and authorization remain just as important as in Servlet.

## 20. References

- Spring Security Reference — WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security Reference — Getting Started with WebFlux: https://docs.spring.io/spring-security/reference/reactive/getting-started.html
- Spring Security Reference — Servlet Architecture: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security Reference — Servlet Authorization: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security Reference — Reactive CSRF: https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html
- Spring Security Reference — Reactive Web Tests: https://docs.spring.io/spring-security/reference/reactive/test/web/authentication.html
- Spring Security API — ReactiveSecurityContextHolder: https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/core/context/ReactiveSecurityContextHolder.html
- Spring Security API — WebFilterChainProxy: https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/web/server/WebFilterChainProxy.html
- Spring Framework API — WebFilter: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/WebFilter.html
- Spring Framework API — WebFilterChain: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/WebFilterChain.html
- Spring Boot Reference — Security: https://docs.spring.io/spring-boot/reference/web/spring-security.html
- Spring Boot Reference — Reactive Web Applications: https://docs.spring.io/spring-boot/reference/web/reactive.html
- Spring Boot Reference — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html
- Spring Security API — ServerHttpSecurity: https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/config/web/server/ServerHttpSecurity.html
