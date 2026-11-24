# WebFilter, WebFilterChainProxy, and SecurityWebFilterChain in Spring Security WebFlux

## 1. The Big Picture

In a **Spring WebFlux** application, intercepting, processing, and securing HTTP requests happens on a reactive pipeline. Three commonly confused components have distinct roles:

| Component | Type | Primary Responsibility |
| --- | --- | --- |
| **WebFilter** | Spring WebFlux interface (org.springframework.web.server.WebFilter) | Intercepts before/after processing a ServerWebExchange; the unit of filter execution. |
| **WebFilterChainProxy** | A WebFilter provided by Spring Security (org.springframework.security.web.server.WebFilterChainProxy) | The entry point into Spring Security in the WebFlux pipeline; holds SecurityWebFilterChains, selects the chain matching the request, and runs that chain's security filters. |
| **SecurityWebFilterChain** | Spring Security reactive interface (org.springframework.security.web.server.SecurityWebFilterChain) | Describes the *matching condition* and the *set of security WebFilters* corresponding to that condition; typically created by ServerHttpSecurity.build(). |

**Key takeaway:** WebFilterChainProxy **is a WebFilter**; SecurityWebFilterChain **is not a single WebFilter**. SecurityWebFilterChain is the configuration/list of filters selected by the proxy. A normal request passes through **the first matching SecurityWebFilterChain**, even when multiple chains are registered.

### Conceptual Processing Diagram

~~~text
HTTP request
    |
    v
Spring WebFlux (ServerWebExchange)
    |
    v
Global WebFilter chain (may include application filters)
    |
    v
WebFilterChainProxy  <-- also a WebFilter in the global chain
    |
    +--> try SecurityWebFilterChains in priority order
    |        |
    |        +--> first chain whose matcher matches
    |                 |
    |                 v
    |             Security WebFilters of that chain
    |             (authentication, security context, authorization, ...)
    |                 |
    +-----------------+--> If allowed to continue:
                              Remaining WebFilters -> WebHandler/Controller
    |
    +--> If denied: handle 401/403/redirect per configuration;
         controller is not invoked
~~~

The diagram omits some adapter/handler layers to focus on the relationship among the three components. Global WebFilters can sit before or after the proxy depending on registration order.

## 2. WebFilter: Spring WebFlux's Extension Point

Spring WebFlux's core contract:

~~~java
public interface WebFilter {
    Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain);
}
~~~

- **ServerWebExchange** holds the request, response, attributes, and HTTP context currently being processed.
- **WebFilterChain** represents the rest of the processing chain. Call **chain.filter(exchange)** to pass the request to the next filter/handler.
- **Mono<Void>** represents *asynchronous* completion. A filter method typically returns a publisher for WebFlux to subscribe and execute. Do not treat returning the publisher as the moment the request has finished processing.
- A filter can read headers, attach a correlation ID, add response headers, run checks, or observe outcomes. If it intentionally terminates the request, it can return a completed publisher without calling chain.filter(exchange); it must then take responsibility for writing an appropriate response.

Example of a simple **global WebFilter** (a fragment used inside a @Configuration class, not a standalone program):

~~~java
@Bean
WebFilter demoHeaderFilter() {
    return (exchange, chain) -> {
        exchange.getResponse().getHeaders().add("X-Demo-WebFilter", "global");
        return chain.filter(exchange);
    };
}
~~~

This filter can run for both public routes and routes requiring authentication because it belongs to the **global WebFlux pipeline**, not to a specific SecurityWebFilterChain. If you want to perform work *after downstream completes*, you can attach reactive operators such as **doFinally(...)** to the returned publisher. Avoid **block()**, heavy synchronous I/O, or storing per-request state in instance fields of a singleton filter.

## 3. WebFilterChainProxy: The Bridge Between WebFlux and Spring Security

**org.springframework.security.web.server.WebFilterChainProxy** implements WebFilter, but does not replace the entire WebFlux WebFilter chain. It receives a list of SecurityWebFilterChains built by Spring Security configuration and does the following:

1. Receives the ServerWebExchange and the current WebFilterChain.
2. Iterates through SecurityWebFilterChains in priority order, asking each chain's matcher whether it matches the request.
3. Picks the **first matching chain** and executes the security WebFilters belonging to that chain.
4. If the filters do not halt processing, continues the original WebFilterChain to reach the remaining WebFlux components.
5. If no chain matches, none of those chains' security filters are applied; the rest of WebFlux can still process the request. That is why applications usually need a **fallback chain** covering remaining URLs.

In normal application configuration, **@EnableWebFluxSecurity** or the appropriate Spring Boot auto-configuration wires up this infrastructure. Developers mainly declare SecurityWebFilterChain beans; they rarely instantiate WebFilterChainProxy directly.

**Distinguish packages to avoid configuring the wrong stack:**

| WebFlux/reactive | Servlet/MVC |
| --- | --- |
| org.springframework.web.server.WebFilter | jakarta.servlet.Filter |
| org.springframework.security.web.server.WebFilterChainProxy | org.springframework.security.web.FilterChainProxy |
| SecurityWebFilterChain | SecurityFilterChain |
| ServerHttpSecurity | HttpSecurity |
| ServerWebExchangeMatcher | RequestMatcher |

The similarly named classes **WebFilterChainProxy** and **FilterChainProxy** belong to two different architectures. Do not copy servlet Filter/HttpSecurity examples directly into WebFlux.

## 4. SecurityWebFilterChain: Scoping and Controlling Security

A SecurityWebFilterChain has two main parts:

- **Chain-level matcher:** Which requests are handled by this set of security filters? Configured via **ServerHttpSecurity.securityMatcher(...)**. If unspecified, the default matcher typically matches every request.
- **WebFilters within the chain:** Which security mechanisms are enabled, such as SecurityContext restoration, HTTP Basic, CSRF checks, authorization, or exception handling? Configured via the **ServerHttpSecurity** DSL followed by **build()**.

Example partitioning: APIs use HTTP Basic; other URLs use a separate fallback configuration. A **GET /api/private** request matches the API chain; it does not continue to run the fallback chain once the API chain has been selected.

### securityMatcher vs. authorizeExchange.pathMatchers

These two configurations do not replace each other:

| Configuration | Question Answered | Effect |
| --- | --- | --- |
| **securityMatcher("/api/**")** | Should this chain be selected for the request? | Decides which *set of security filters* participates. |
| **authorizeExchange(...pathMatchers("/api/public").permitAll())** | Inside the selected chain, which paths are allowed? | Decides *access permission*; does not disable all security filters. |
| **authorizeExchange(...anyExchange().authenticated())** | Do other requests in this chain require authentication? | Serves as the catch-all authorization rule *within that same chain*. |

**permitAll does not mean bypassing WebFilterChainProxy.** Other relevant filters in the chain may still run, such as security headers or security context handling.

### Three Levels of Ordering to Distinguish

1. **Global WebFilter order:** determines a WebFilter's position relative to other WebFlux WebFilters; usually controlled with Ordered or @Order on the appropriate bean/filter.
2. **SecurityWebFilterChain order:** determines which chain the proxy tries first; apply @Order to SecurityWebFilterChain beans. Specific chains should precede a catch-all chain.
3. **WebFilter order inside a security chain:** organized by Spring Security configuration; when adding a custom security filter to a chain, use positions defined by **SecurityWebFiltersOrder** via APIs like **ServerHttpSecurity.addFilterAt(...)**, depending on the goal.

@Order on **a global WebFilter bean** is not the same as @Order on **a SecurityWebFilterChain bean**. And declaring a @Bean WebFilter does not automatically place that filter inside the API chain's private filter list.

## 5. Runnable Example: Two SecurityWebFilterChains and One Global WebFilter

**Environment:** Java 17+, a Spring Boot 3.x Maven project using **Spring Reactive Web** (spring-boot-starter-webflux) and **Spring Security** (spring-boot-starter-security). You can generate this project with Spring Initializr; keep the generated Maven wrapper and Maven structure. Do not add spring-boot-starter-web for this WebFlux demo.

Create **src/main/java/com/example/demo/DemoApplication.java** with the **entire** contents below:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.WebFilter;

import static org.springframework.security.config.Customizer.withDefaults;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}

@Configuration
@EnableWebFluxSecurity
class ReactiveSecurityConfig {

    @Bean
    ReactiveUserDetailsService users() {
        UserDetails user = User.withUsername("learner")
                .password("{noop}demo123")
                .roles("USER")
                .build();
        return new MapReactiveUserDetailsService(user);
    }

    // Application-wide WebFilter, not limited to /api/**.
    @Bean
    WebFilter globalHeaderFilter() {
        return (exchange, chain) -> {
            exchange.getResponse().getHeaders()
                    .add("X-Demo-WebFilter", "global");
            return chain.filter(exchange);
        };
    }

    // Prioritize the API chain before the fallback chain.
    @Bean
    @Order(1)
    SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
        return http
                .securityMatcher(
                        new PathPatternParserServerWebExchangeMatcher("/api/**"))
                .authorizeExchange(auth -> auth
                        .pathMatchers("/api/public").permitAll()
                        .anyExchange().authenticated())
                .httpBasic(withDefaults())
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .build();
    }

    // No securityMatcher declared: fallback chain for remaining URLs.
    @Bean
    @Order(2)
    SecurityWebFilterChain fallbackChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(auth -> auth
                        .pathMatchers("/").permitAll()
                        .anyExchange().authenticated())
                .httpBasic(withDefaults())
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .build();
    }
}

@RestController
class DemoEndpoints {

    @GetMapping("/")
    String home() {
        return "home";
    }

    @GetMapping("/api/public")
    String publicApi() {
        return "public";
    }

    @GetMapping("/api/private")
    String privateApi() {
        return "private";
    }

    @GetMapping("/account")
    String account() {
        return "account";
    }
}
~~~

**Run** from the Maven project root directory (with the Maven wrapper):

~~~bash
./mvnw spring-boot:run
~~~

On Windows you can use **mvnw.cmd spring-boot:run**. In another terminal, send the following requests:

~~~bash
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/private
curl -i -u learner:demo123 http://localhost:8080/api/private
curl -i http://localhost:8080/
curl -i http://localhost:8080/account
~~~

**Expected HTTP results** when running the example with the Basic configuration above:

| Request | Selected Chain | HTTP status | Response body (when 200) |
| --- | --- | --- | --- |
| GET /api/public, no credentials | apiChain | **200** | public |
| GET /api/private, no credentials | apiChain | **401** | — |
| GET /api/private with Basic learner:demo123 | apiChain | **200** | private |
| GET /, no credentials | fallbackChain | **200** | home |
| GET /account, no credentials | fallbackChain | **401** | — |

The **X-Demo-WebFilter: global** header added by the global filter demonstrates that a regular WebFilter operates independently of whether the proxy selects the API chain or the fallback chain. Other headers and error response bodies may vary by version/configuration; the table only asserts the status codes and success bodies tied to the example's logic.

Path-by-path explanation:

- **GET /api/public:** the proxy encounters apiChain first and /api/** matches; the /api/public rule permits unauthenticated access; the handler returns “public”.
- **GET /api/private** without credentials: apiChain is still selected; the authenticated requirement fails, so the security layer produces a 401 response without reaching privateApi().
- **GET /api/private** with Basic: the authentication mechanism looks up the user in MapReactiveUserDetailsService; since it is valid, authorization lets it pass and the handler returns “private”.
- **GET /** and **GET /account:** neither matches /api/**, so the proxy selects fallbackChain. Only / is permitted for all, while /account requires authentication.

**Security limitations of the example:** the {noop} password prefix is used so the lesson is easy to run locally and is **not suitable for production**. In real systems, use a secure PasswordEncoder and a proper user store. The example only tests GET requests; Spring Security enables CSRF protection by default for state-changing methods. Do not disable CSRF mechanically, especially for applications using cookies/sessions in browsers.

## 6. When You Need a Custom Filter: Where Should It Go?

**Need A — logging/tracing/response headers for every route:** create a global **WebFilter** bean and control its ordering relative to other filters if needed. Always preserve reactive properties and handle errors/cancellation properly.

**Need B — logic belonging only to one security chain:** create a custom WebFilter and register it via **ServerHttpSecurity.addFilterAt(...)** with the appropriate **SecurityWebFiltersOrder**. That is the API for adding a filter *into a SecurityWebFilterChain*, rather than merely declaring a global bean. Guiding fragment (assuming mySecurityFilter already exists):

~~~java
http.addFilterAt(mySecurityFilter, SecurityWebFiltersOrder.AUTHENTICATION);
~~~

This fragment only illustrates where to configure it; choose the actual position based on the filter's responsibility and existing security filters, and do not insert arbitrarily at AUTHENTICATION. If the filter performs authentication, distinguish it from the already-configured AuthenticationWebFilter and avoid duplicate authentication mechanisms.

**Need C — distinct API/web policies:** create multiple SecurityWebFilterChain beans with explicit matchers and explicit priority orders. For example, APIs can use HTTP Basic or JWT while web pages use form login; each request selects the appropriate chain via its matcher.

### SecurityContext in Reactive Applications

In WebFlux, processing can switch threads between Reactor steps. Spring Security reactive integrates **ReactiveSecurityContextHolder** and Reactor Context to propagate SecurityContext along the reactive stream. Do not rely solely on ThreadLocal or assume “a request always runs on one thread.” When writing a custom filter that needs to read user information, use the reactive APIs (such as ReactiveSecurityContextHolder.getContext()) and chain the publisher into the pipeline.

## 7. Common Configuration Mistakes

| Symptom | Common Cause | Solution |
| --- | --- | --- |
| API chain is never used | A catch-all chain precedes the /api/** chain | Use @Order so specific chains precede the fallback. |
| A URL outside /api/** is unprotected | Only a chain with securityMatcher /api/** is declared without a fallback | Add a default chain; configure safe authorization for remaining paths. |
| Configured permitAll but filters still run | permitAll is an authorization rule, not a mechanism to skip the entire chain | Separate chain selection from access grants; inspect which filters actually need to be skipped. |
| Custom filter runs on unintended routes | Declared as a global @Bean WebFilter | If it is security logic meant for only one chain, add it directly to that chain's ServerHttpSecurity. |
| Attempting to use HttpSecurity/SecurityFilterChain or servlet Filter | Confusing Spring MVC with Spring WebFlux | Use ServerHttpSecurity, SecurityWebFilterChain, and WebFilter from the right packages. |
| Unauthenticated request returns 302 instead of 401 | Form login / redirect entry point is enabled | Check authentication entry point and Basic/form login settings per chain. |
| Authenticated request gets 403 | Insufficient authorities, or a policy like CSRF denied it | Check authorization/CSRF policies; do not assume 403 means a login failure. |
| Filter hangs or blocks the event loop | Calling block(), sleep, or synchronous I/O in the pipeline | Use Mono/Flux and appropriate asynchronous mechanisms. |
| SecurityContext “disappears” after a thread switch | Using ThreadLocal or subscribing detached from the pipeline | Use ReactiveSecurityContextHolder/Reactor Context and preserve reactive composition. |

To investigate which chain a request enters, you can temporarily enable Spring Security logging in development:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Observe the matchers, security filters, authentication/authorization decisions, and actual HTTP statuses. Avoid overly verbose sensitive logging in production, and remember to turn off debug settings after diagnosing.

## 8. Self-Check Questions

1. Why is WebFilterChainProxy a WebFilter while SecurityWebFilterChain is not?
2. If two chains are declared whose matchers both match /api/orders, which chain runs? What determines the choice?
3. At which step in the request flow does **securityMatcher("/api/**")** differ from **pathMatchers("/api/public").permitAll()**?
4. Why does declaring a logging WebFilter bean not mean that filter runs only inside apiChain?
5. When adding a filter to perform custom authentication for an API, why must you choose **SecurityWebFiltersOrder** carefully?
6. What happens if none of the SecurityWebFilterChains match a URL? How do you avoid a security “gap” caused by a missing fallback?
7. Why should you not use ThreadLocal or block() with Servlet-style thinking when handling WebFlux requests?

**Summary:** WebFilter is WebFlux's request-processing unit; WebFilterChainProxy is the entry point into reactive Spring Security and the chain selector; SecurityWebFilterChain pairs a matcher with its corresponding security WebFilters. Understanding these three roles and three ordering levels accurately is the foundation for designing multiple security zones in a WebFlux application.

## Official References

- Spring Security, WebFlux Security and Multiple Chains: https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html
- Spring Security, Authorize ServerHttpRequest: https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/authorize-http-requests.html
- Spring Security API, Reactive WebFilterChainProxy: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/WebFilterChainProxy.html
- Spring Framework, Reactive Core / WebFilter: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
