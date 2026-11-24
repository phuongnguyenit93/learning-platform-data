# DelegatingFilterProxy: Bridge Between the Servlet Container and a Spring Bean

> **Scope:** Spring Security on the Servlet stack (`jakarta.servlet`, Spring MVC, Spring Framework 6 / Spring Security 6 / Spring Boot 3.x). The focus is on the **DelegatingFilterProxy** mechanism connecting the Servlet container with a `Filter` object managed by Spring, specifically the `springSecurityFilterChain` bean. This covers **filter architecture**, not Spring WebFlux's `WebFilter` mechanism.

## 1. Why is a bridge layer needed?

In a Servlet application, Tomcat/Jetty/Undertow invoke `jakarta.servlet.Filter` instances **registered with the Servlet container**. The container knows URL mappings, dispatcher types, filter ordering, and filter lifecycle according to the Servlet API.

Conversely, the Spring ApplicationContext manages **Spring beans**: object creation, dependency injection, `@Bean` configuration, and bean lifecycle management. Spring Security needs filters that use Spring beans and configuration such as `AuthenticationManager`, `SecurityContextRepository`, or authorization rules.

If you registered each security filter directly with the container, you would have to let the container decide the order, mapping, and lifecycle of many filters; this does not reflect Spring Security's mechanism for selecting `SecurityFilterChain` instances. `DelegatingFilterProxy` resolves this intersection:

- To the container, it **is a `jakarta.servlet.Filter`** registered under a specific name and URL/dispatcher mapping.
- To Spring, it looks up a **bean that also implements `Filter`** by name and delegates the `doFilter(request, response, chain)` call to that bean.
- In Spring Security, the target bean is typically named **`springSecurityFilterChain`** and has type `FilterChainProxy`. This object is what selects the `SecurityFilterChain` and executes the actual security filters.

**Key distinction:** `DelegatingFilterProxy` is the **bridge/delegate**, whereas `FilterChainProxy` is the **coordinator of security filter chains**. Both names contain "Proxy", but their roles are different.

## 2. Request diagram: container filter and Spring Security filter chain

```text
HTTP request
    |
    v
Servlet container
    |
    +--> [Container Filter before security, if any]
    |
    +--> DelegatingFilterProxy  (registered with the container)
    |       targetBeanName = "springSecurityFilterChain"
    |             |
    |             v   look up Spring WebApplicationContext
    |       Spring bean: FilterChainProxy
    |             |
    |             +--> select the first SecurityFilterChain matching the request
    |             |       |
    |             |       +--> Security Filter 1
    |             |       +--> Security Filter 2
    |             |       +--> ... authorization / exception handling
    |             |
    |             +--> invoke remaining original FilterChain if permitted
    |
    +--> [Container Filter after security, if any]
    |
    +--> DispatcherServlet (Spring MVC) / target Servlet
                 |
                 +--> HandlerMapping -> HandlerInterceptor -> Controller
    |
    v
HTTP response (filters complete along the return path)
```

The diagram shows a **nested relationship**, not a claim that every container filter has the same position. A container filter after the proxy is only invoked if the proxy and security filters allow the request to proceed; a security filter may terminate early with 401/403 or a redirect. A Spring MVC interceptor only resides inside the `DispatcherServlet` flow and does not run before the security chain.

### Four commonly confused objects

| Name | Where? | What is it responsible for? |
| --- | --- | --- |
| Servlet container `FilterChain` | Container | Chains registered servlet filters and the target servlet |
| `DelegatingFilterProxy` | A servlet filter in the container | Forwards `doFilter` to a Spring bean with a specified name |
| `FilterChainProxy` | Spring bean, the proxy's target in Security | Selects the matching chain and executes ordered security filters |
| `SecurityFilterChain` | Spring Security | Holds a request matcher and the list of security filters for a group of requests |

`SecurityFilterChain` is **not** the object directly invoked by the container on each request. It is the structure used by `FilterChainProxy` after `DelegatingFilterProxy` has handed over control.

## 3. How does DelegatingFilterProxy work?

### 3.1. Registering the filter in the container, looking up the bean by name

When invoked by the container, `DelegatingFilterProxy` has a configured target bean name, for example:

```text
Servlet filter registration:
    name       = "springSecurityFilterChain"
    filter     = DelegatingFilterProxy
    URL mapping = /*
            |
            v
Spring WebApplicationContext:
    bean name  = "springSecurityFilterChain"
    bean type  = FilterChainProxy implements jakarta.servlet.Filter
```

In the `doFilter` method, the proxy retrieves the target filter from the Spring context (if not yet resolved/cached), and then invokes `target.doFilter(request, response, chain)`. Resolution may happen when the proxy initializes if the context is ready, or lazily when a request arrives; you should not assume a fresh bean lookup is always required on every request.

Illustrating the **concept**, not Spring's internal source code:

```java
// Illustrative pseudocode; not a standalone compilable class.
Filter delegate = springContext.getBean("springSecurityFilterChain", Filter.class);
delegate.doFilter(request, response, servletContainerFilterChain);
```

The call receives the original `ServletRequest`, `ServletResponse`, and the **container's `FilterChain`**. As a result, when the target eventually calls `chain.doFilter`, execution returns to subsequent container filters and then to the target servlet.

### 3.2. What happens if the target bean does not exist?

The target name is a **configuration contract**. If the proxy registers target `springSecurityFilterChain` but the application does not create that bean or the proxy cannot find the right Spring `WebApplicationContext`, requests cannot be delegated normally and the application may fail during filter initialization or request processing. You must never silently treat the proxy as a "pass-through" filter in this scenario.

Check the bean name, whether the bean type implements `Filter`, which context contains the bean, initialization timing, and the servlet filter registration configuration. `DelegatingFilterProxy` can be constructed using a constructor that explicitly supplies the target bean name and `WebApplicationContext` when writing manual configuration.

### 3.3. Two lifecycle systems

- **The Servlet container** invokes `init(FilterConfig)` and `destroy()` on the registered `DelegatingFilterProxy`.
- **The Spring ApplicationContext** normally manages the lifecycle of the **target bean** (creating/initializing/destroying the bean). This is the default behavior when `targetFilterLifecycle` is not enabled.
- `setTargetFilterLifecycle(true)` instructs the proxy to delegate the Servlet Filter's `init`/`destroy` to the target according to the container lifecycle. This should only be used when you truly understand the lifecycle need; for filter beans managed by Spring, the default is more appropriate.

Do not manually invoke `init`/`destroy` on security beans; do not register `FilterChainProxy` a second time with the container merely because it implements `Filter`.

## 4. From DelegatingFilterProxy to springSecurityFilterChain

In a Spring Boot Servlet application using `spring-boot-starter-security`:

1. Spring Security creates a target filter bean named **`springSecurityFilterChain`** (typically a `FilterChainProxy`).
2. Spring Boot configures the registration of **`DelegatingFilterProxy`** with the Servlet container (via `DelegatingFilterProxyRegistrationBean` in the appropriate auto-configuration mechanism) to point to that bean name.
3. The container invokes the proxy when a request matches the URL/dispatcher mapping.
4. `FilterChainProxy` selects the **first `SecurityFilterChain` matching the request** in chain order, and runs the configured security filters.
5. When the request is valid and the filters continue the chain, processing proceeds to the servlet/MVC; when blocked, the controller may not run.

**Spring Boot automatically registers the proxy** in standard Servlet Security configurations. There is no need to write another separate `DelegatingFilterProxy` for `springSecurityFilterChain` just to "enable security"; duplicate registration can lead to unintended behavior.

In non-Boot applications, the proxy can be registered via `web.xml`, `ServletContext#addFilter`, or the corresponding Servlet initialization mechanism; the application must still provide the proper Spring context and target bean.

### Multiple SecurityFilterChains vs. multiple container filters

An example configuring two areas, API and web, illustrated with a Java snippet that is **syntactically self-contained but needs to be placed inside a `@Configuration` class of an application with Spring Security**:

```java
@Bean
@Order(1)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth.anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
}

@Bean
@Order(2)
SecurityFilterChain web(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/public").permitAll()
                    .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .build();
}
```

You need to import `@Bean`, `@Order`, `HttpSecurity`, `SecurityFilterChain`, `Customizer`, and have appropriate authentication beans. This is an explanatory snippet about **chain selection**, not a standalone runnable Java program.

A `/api/items` request matches the API chain first; `/public` goes through the web chain. Both can still go through **the same container `DelegatingFilterProxy`**. `securityMatcher` selects the *chain*, while `requestMatchers` inside `authorizeHttpRequests` sets *authorization rules within the selected chain*. If no chain matches, `FilterChainProxy` does not apply any chain's security filters to that request; therefore, you must design a safe fallback matcher for real-world applications.

## 5. Runnable Spring Boot example: observing the delegation boundary

The example uses Java 17+, Spring Boot 3.3.x, and Spring Security 6.x. We observe three layers: (1) an actual container filter; (2) a filter **inside** the Spring Security chain; (3) the controller. Next, we register **a separate DelegatingFilterProxy for an ordinary Spring bean** to clearly see the bridge mechanism, without depending on Spring Security internals.

### 5.1. Create the project

```text
delegating-filter-demo/
  settings.gradle
  build.gradle
  src/main/java/demo/
    DemoApplication.java
    ContainerTraceFilter.java
    SecurityTraceFilter.java
    SecurityConfig.java
    BridgeConfig.java
    DemoController.java
```

`settings.gradle`:

```groovy
rootProject.name = 'delegating-filter-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
```

`src/main/java/demo/DemoApplication.java`:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

### 5.2. First filter: container filter

`src/main/java/demo/ContainerTraceFilter.java`:

```java
package demo;

import java.io.IOException;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class ContainerTraceFilter extends OncePerRequestFilter {
    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain chain)
            throws IOException, ServletException {
        System.out.println("CONTAINER before " + request.getRequestURI());
        try {
            chain.doFilter(request, response);
        } finally {
            System.out.println("CONTAINER after status=" + response.getStatus());
        }
    }
}
```

`@Component` enables Boot to automatically register this filter with the container. `@Order` places it at the front of the container filter chain in the example. It is **not** attached to `HttpSecurity`'s list of security filters.

### 5.3. Second filter: inside Spring Security

`src/main/java/demo/SecurityTraceFilter.java`:

```java
package demo;

import java.io.IOException;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.web.filter.OncePerRequestFilter;

public class SecurityTraceFilter extends OncePerRequestFilter {
    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain chain)
            throws IOException, ServletException {
        System.out.println("SECURITY in-chain "
                + request.getMethod() + " " + request.getRequestURI());
        chain.doFilter(request, response);
    }
}
```

This class has **no `@Component` and no separate `@Bean` filter**: we instantiate it solely when configuring `HttpSecurity`. This is the simplest way to prevent Boot from automatically registering the same filter with the container a second time.

`src/main/java/demo/SecurityConfig.java`:

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.AuthorizationFilter;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public", "/bridge/ping").permitAll()
                .anyRequest().authenticated());
        http.httpBasic(Customizer.withDefaults());
        http.addFilterBefore(new SecurityTraceFilter(), AuthorizationFilter.class);
        return http.build();
    }

    @Bean
    UserDetailsService users() {
        UserDetails user = User.withUsername("learner")
                .password("{noop}study123")
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(user);
    }
}
```

`http.addFilterBefore` specifies the position **within the Spring Security chain**, without creating a container filter. `{noop}` is the unencoded password encoder syntax for local testing; real systems must use proper password hashing, such as BCrypt, and manage secrets securely.

### 5.4. Adding a manually declared DelegatingFilterProxy to observe the bridge

In addition to Spring Security's default proxy, the example creates a Spring `Filter` bean named `bridgeTarget` and registers **a proxy with its own URL mapping** `/bridge/*`. This is an independent proxy for studying the delegation mechanism, not a proxy replacing `springSecurityFilterChain`.

`src/main/java/demo/BridgeConfig.java`:

```java
package demo;

import jakarta.servlet.Filter;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.Ordered;
import org.springframework.web.context.WebApplicationContext;
import org.springframework.web.filter.DelegatingFilterProxy;

@Configuration
public class BridgeConfig {
    @Bean("bridgeTarget")
    Filter bridgeTarget() {
        return (request, response, chain) -> {
            String uri = ((HttpServletRequest) request).getRequestURI();
            System.out.println("BRIDGE TARGET before " + uri);
            try {
                chain.doFilter(request, response);
            } finally {
                System.out.println("BRIDGE TARGET after " + uri);
            }
        };
    }

    @Bean
    FilterRegistrationBean<Filter> disableDirectRegistration(
            @Qualifier("bridgeTarget") Filter target) {
        FilterRegistrationBean<Filter> registration =
                new FilterRegistrationBean<>(target);
        registration.setEnabled(false);
        return registration;
    }

    @Bean
    FilterRegistrationBean<DelegatingFilterProxy> bridgeProxyRegistration(
            WebApplicationContext context) {
        DelegatingFilterProxy proxy =
                new DelegatingFilterProxy("bridgeTarget", context);
        FilterRegistrationBean<DelegatingFilterProxy> registration =
                new FilterRegistrationBean<>(proxy);
        registration.addUrlPatterns("/bridge/*");
        registration.setOrder(Ordered.HIGHEST_PRECEDENCE + 10);
        return registration;
    }
}
```

There are **two points that must not be omitted** when using this pattern:

1. `bridgeTarget` is a Spring bean of type `Filter`. Spring Boot will normally **auto-register a Filter bean as a servlet filter** unless configured otherwise. The `disableDirectRegistration` bean uses `setEnabled(false)` to prevent the target from running directly alongside the proxy.
2. `bridgeProxyRegistration` registers **`DelegatingFilterProxy`**, matching only `/bridge/*` and looking up the target named `bridgeTarget` in `WebApplicationContext`. If you rename the bean without updating the target string, the bridge will fail. Setting the order at the container level is distinct from `HttpSecurity`'s `addFilterBefore`.

In this program, the container logging filter runs first, the manual bridge for `/bridge/*` runs next, and the Spring Security proxy runs afterward according to Boot's registration order.

### 5.5. Controller and test commands

`src/main/java/demo/DemoController.java`:

```java
package demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {
    @GetMapping("/public")
    public String open() {
        System.out.println("CONTROLLER /public");
        return "PUBLIC";
    }

    @GetMapping("/private")
    public String privatePage() {
        System.out.println("CONTROLLER /private");
        return "PRIVATE";
    }

    @GetMapping("/bridge/ping")
    public String bridgePing() {
        System.out.println("CONTROLLER /bridge/ping");
        return "PONG";
    }
}
```

Install JDK 17+ and a Gradle version compatible with Spring Boot 3.3 (e.g., Gradle 8.5), then from the `delegating-filter-demo` directory run:

```bash
gradle bootRun
```

If the project was created with a Gradle wrapper, you can run `./gradlew bootRun` on macOS/Linux or `.\gradlew.bat bootRun` on Windows.

Open another terminal and send each request one by one (so the logs are easy to read):

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/private
curl -i -u learner:study123 http://localhost:8080/private
curl -i http://localhost:8080/bridge/ping
```

**Observation 1 — `GET /public`:** HTTP 200, body `PUBLIC`. Lines produced by the application's `System.out.println` in order:

```text
CONTAINER before /public
SECURITY in-chain GET /public
CONTROLLER /public
CONTAINER after status=200
```

**Observation 2 — `GET /private` without credentials:** HTTP 401 with the HTTP Basic configuration. The controller does not run:

```text
CONTAINER before /private
SECURITY in-chain GET /private
CONTAINER after status=401
```

**Observation 3 — `GET /private` with valid HTTP Basic:** HTTP 200, body `PRIVATE`:

```text
CONTAINER before /private
SECURITY in-chain GET /private
CONTROLLER /private
CONTAINER after status=200
```

**Observation 4 — `GET /bridge/ping`:** HTTP 200, body `PONG`. The request enters the manual proxy, target bean, then security and the controller:

```text
CONTAINER before /bridge/ping
BRIDGE TARGET before /bridge/ping
SECURITY in-chain GET /bridge/ping
CONTROLLER /bridge/ping
BRIDGE TARGET after /bridge/ping
CONTAINER after status=200
```

The log examples above show the order of `System.out.println` lines for **a single synchronous request** under the stated configuration; startup logs, framework logs, and concurrent requests may interleave. Cases with **invalid** Basic credentials may be rejected by the authentication filter positioned **before** `SecurityTraceFilter`, so you should not infer that a custom trace will observe every authentication failure path.

Re-reading the `/bridge/ping` flow: container invokes `DelegatingFilterProxy("bridgeTarget")` → proxy invokes Spring bean `bridgeTarget` → bean invokes `chain.doFilter` → request passes through the container registration of the security proxy → `FilterChainProxy` and internal security filters → `DispatcherServlet`/controller → returns back through the invoked layers. This is direct evidence of the difference between **filter registration** and **implementing logic inside a Spring bean**.

## 6. Registration, ordering, and lifecycle belong at the right layer

| What you want to change | Appropriate API/configuration | Notes |
| --- | --- | --- |
| URL pattern and dispatcher types of a container filter/proxy | Servlet registration or `FilterRegistrationBean` | The container decides which requests go through the proxy |
| Order of the proxy relative to other container filters | `FilterRegistrationBean#setOrder`/registration order | Does not equate to the order of internal security filters |
| Bean to which the proxy delegates | Target bean name, `WebApplicationContext` | The bean must implement `jakarta.servlet.Filter` |
| Security chains for URL groups | Multiple `SecurityFilterChain` + `securityMatcher`/`@Order` | `FilterChainProxy` picks the first matching chain |
| Order of **security filters** within a chain | `HttpSecurity.addFilterBefore/addFilterAfter` | Use a known anchor filter from Spring Security |
| Authorization within a chain | `authorizeHttpRequests` | `permitAll` still goes through the security filter chain |
| Target bean lifecycle | Spring bean lifecycle | `targetFilterLifecycle` is disabled by default |

**Three independent kinds of "order":** (1) order of container registrations; (2) order for selecting `SecurityFilterChain`; (3) order of filters inside a chain. Adjusting one kind does not automatically adjust the other two.

**Three independent scopes of "match":** (1) URL/dispatcher mapping of the container proxy; (2) request matcher selecting the security chain; (3) authorization matcher within the selected chain. For example, if a proxy has a URL pattern of only `/api/*`, authorization rules in Spring cannot protect a request outside that mapping via that proxy.

With default Spring Boot configuration, avoid manually manipulating the `springSecurityFilterChain` proxy unless there is a clear need. `HttpSecurity` and `SecurityFilterChain` are where security policies are configured; Servlet registration is only used when changing how integration works at the container boundary.

## 7. Common mistakes and how to diagnose them

### 7.1. "I already have a `SecurityFilterChain` bean, why is the endpoint still unprotected?"

Check whether `DelegatingFilterProxy` is registered so requests enter `springSecurityFilterChain`; whether you are on the Servlet stack; whether the target bean name matches; whether the proxy's URL/dispatcher mapping covers the endpoint; whether the security chain's request matcher matches; and whether the first matching chain has the right rules. Merely having a `SecurityFilterChain` bean does not prove the container is routing requests through Spring Security.

### 7.2. "I added a filter with `http.addFilterBefore`, why does it run twice?"

A common cause is that the filter class is both a Spring `Filter` bean auto-registered by Boot with the **container**, and added to the **security chain**. Inspect both registration lists and avoid duplicate registration. The simple approach in the example is instantiating `new SecurityTraceFilter()` only inside `HttpSecurity`. If a `Filter` bean must be used, configure a disabled `FilterRegistrationBean` for the container path when needed.

In addition, `REQUEST`/`ERROR`/`ASYNC` dispatches can cause multiple dispatches; do not conclude there is duplicate registration without checking the dispatcher type.

### 7.3. "Does renaming the filter in the container automatically change the target bean?"

You should not assume the two names stay automatically synchronized across all registration styles. When constructing `new DelegatingFilterProxy("bridgeTarget", context)`, the specified target name is `bridgeTarget`; another bean name will not be used by the proxy unless reconfigured. Some constructor/registration styles may default the target name to the filter-name, so always verify how the proxy is created in your application.

### 7.4. "Does `@Order` on a custom filter change the order of security filters?"

`@Order` typically affects how Boot registers a **container filter bean**. Filters inside a `SecurityFilterChain` are ordered via Spring Security configuration, such as `addFilterBefore`. To place a filter after the authentication step, identify the appropriate anchor filter in the security chain; do not use `@Order` as a substitute.

### 7.5. "Does using `permitAll()` bypass DelegatingFilterProxy?"

No. `permitAll()` is an authorization decision for a request passing through the chain, **not** bypassing the proxy, and it does not automatically bypass authentication/CORS/CSRF or other security filters. Contrast this with excluding URLs from security via `web.ignoring()`: when excluded from security, requests do not receive standard security filter chain processing. Prefer `permitAll()` for public resources unless there is a clear technical reason.

### 7.6. "Can we rely on an MVC HandlerInterceptor for protection instead of the security proxy?"

You should not. An interceptor only runs after `DispatcherServlet` selects an MVC handler; requests blocked earlier in filters, or routed to other servlets, do not go through the same interceptor flow. Protecting HTTP endpoints should be configured with Spring Security in the security chain (and method security if needed).

### 7.7. "Do we need to call `FilterChainProxy.doFilter` manually?"

No. The container invokes `DelegatingFilterProxy`; the proxy delegates; `FilterChainProxy` executes security logic according to configuration and calls the remaining original chain when appropriate. Calling it manually can bypass lifecycle/mapping boundaries or run security logic twice.

### 7.8. "Why can't the proxy resolve the bean?"

Check specifically:
- Is the bean registered under the **exact targetBeanName** and implementing `Filter`?
- Which **WebApplicationContext** is the proxy searching? Does the application have parent/child contexts or a custom Servlet context?
- Was the proxy created too early relative to the Spring context, or does the target configuration have a broken dependency?
- Was Spring Security Servlet auto-configuration excluded, or is the application actually running WebFlux?
- Does the proxy have URL mapping/dispatcher types matching the request being tested?

Never "fix" this by silently bypassing security when the target is missing.

## 8. Checklist when designing filters for a real application

1. **Identify the right layer for the logic:** container `Filter` for processing across the whole Servlet boundary; security filter for authentication/authorization-related behavior; MVC `HandlerInterceptor` for handler-coupled logic.
2. **Confirm the registration source:** Boot auto-register? `FilterRegistrationBean`? `http.addFilterBefore`? Proxy-added? Avoid one filter having two unexpected owners.
3. **Verify the three ordering levels and three matcher levels:** container registration, `SecurityFilterChain` selection, internal filter order/authorization rules.
4. **Attach a request ID to logs** to distinguish multiple HTTP requests and `REQUEST`, `ERROR`, `ASYNC` dispatches; avoid drawing conclusions from interleaved logs.
5. **Test rejection paths:** 401, 403, CSRF denial, CORS preflight, exceptions, async dispatch; do not only test `200 OK`.
6. **Keep lifecycle safe:** Spring manages target filter beans by default; only enable `targetFilterLifecycle` when there is a verified need.

## 9. Self-check questions

1. **Does the container invoke `DelegatingFilterProxy` or `SecurityFilterChain` directly?** The container invokes the filter registered as `DelegatingFilterProxy`; the target bean is usually `FilterChainProxy`, which selects the `SecurityFilterChain`.
2. **Does the proxy authenticate users itself?** No; it only forwards calls to the target. Security filters and application configuration enforce security policies.
3. **Does an application with three `SecurityFilterChain`s require three `DelegatingFilterProxy` instances?** No; a single proxy pointing to `FilterChainProxy` can serve multiple chains.
4. **Why should you not register the `springSecurityFilterChain` proxy again in Spring Boot?** Boot usually does this automatically for Servlet Security; duplicate registration can cause repeated processing or hard-to-diagnose issues.
5. **Why is `setEnabled(false)` needed for the `bridgeTarget` bean in the example?** So Boot does not register the target `Filter` directly with the container; `/bridge/*` requests must pass through the proxy to invoke this bean.
6. **Are `http.addFilterBefore` and `FilterRegistrationBean#setOrder` on the same layer?** No; the former orders filters inside the Spring Security chain, while the latter orders the container's servlet filter registrations.

**Key takeaway:** `DelegatingFilterProxy` is a filter **registered in the container** that **delegates to a Spring bean**. In Spring Security Servlet, the key target is `springSecurityFilterChain` (a `FilterChainProxy`). From there, `FilterChainProxy` selects the matching `SecurityFilterChain` and runs the security filters; if the request is allowed to proceed, execution then reaches the servlet/MVC. Clearly distinguishing container registration, Spring bean lookup, security chain selection, and authorization is the key to configuring and debugging accurately.
