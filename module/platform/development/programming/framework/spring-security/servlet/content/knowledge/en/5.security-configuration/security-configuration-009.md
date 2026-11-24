# ObjectPostProcessor and Component-Level Extension Choices in Spring Security Servlet

## Learning objectives

In Spring Security Servlet, `HttpSecurity` builds a `SecurityFilterChain` from many components: filters, authentication objects, authorization managers, session/CSRF handling, and auxiliary configurations. When you need to adjust an **object created during security construction**, `ObjectPostProcessor` is an object/component-level extension mechanism. It differs from choosing which endpoints are accessible or adding a new filter to the chain.

After this lesson, you will be able to:

- Explain what `ObjectPostProcessor<T>` receives, returns, and at which stage it is invoked.
- Distinguish modifying a framework-created component from configuring the entire `SecurityFilterChain`.
- Understand the relationship among `ObjectPostProcessor`, `HttpSecurity`, `AbstractHttpConfigurer`/`SecurityConfigurer`, Spring `BeanFactory`, and dependency injection.
- Choose among public extension points: `Customizer`/DSL, `@Bean`, custom `AuthenticationProvider`/`AuthorizationManager`, `addFilterBefore`/`addFilterAfter`, `AbstractHttpConfigurer`, and `ObjectPostProcessor`.
- Write a Spring Boot Servlet example using `postProcess(...)` to complete a custom filter with injected dependencies, then verify it via HTTP responses and tests.
- Recognize the risks of reaching too deep into internals, misordering filters, or registering a filter twice.

The scope of this lesson is Spring Boot 3.x and Spring Security 6.x on the **Servlet stack**. Examples use Java 17+ and require only the APIs shown in each example. Do not mechanically apply Servlet syntax to WebFlux `SecurityWebFilterChain`.

## 1. What is ObjectPostProcessor?

Spring Security's core interface lives in package `org.springframework.security.config.annotation`:

~~~java
public interface ObjectPostProcessor<T> {
    <O extends T> O postProcess(O object);
}
~~~

This is an **abbreviated API interface signature**, not the library's complete source file. In a program, import `ObjectPostProcessor` from Spring Security.

`ObjectPostProcessor` accepts an already-created object and allows an additional processing step before that object is used. The method must return an object compatible with the received type. The common usage is finalizing/injecting/configuring the object and returning it.

Example of the workflow:

1. The framework/configurer instantiates a filter or security component.
2. The post-processing mechanism is invoked on that component.
3. The post-processor can inject dependencies, run initialization steps, or configure a property exposed by the current extension point.
4. The post-processed component is placed into the security configuration and used later.

**Post-processing runs during configuration construction**, typically at startup when building `SecurityFilterChain` via `http.build()`. It is not a callback running per HTTP request. A post-processed filter may be called repeatedly per request, but `postProcess(...)` itself does not run repeatedly at that frequency by default.

Do not assume that "every `@Component` object or every Spring bean automatically passes through Spring Security's `ObjectPostProcessor`". This is a mechanism belonging to security building, called via builders/configurers or at specific extension points. Spring Framework's `BeanPostProcessor` is a related concept with a different scope.

## 2. Where does ObjectPostProcessor sit in the configuration lifecycle?

A typical path when Spring Boot initializes Spring Security Servlet:

~~~text
Spring ApplicationContext
    |
    +-- creates/provides HttpSecurity and related dependencies
    |
@Bean SecurityFilterChain securityFilterChain(HttpSecurity http)
    |
    +-- applies authorizeHttpRequests, formLogin, httpBasic...
    +-- registers required SecurityConfigurers
    |
http.build()
    |
    +-- init and configure phases of SecurityConfigurers
    +-- creates/configures filters and security objects
    +-- calls ObjectPostProcessor when builder/configurer requests
    +-- sorts filters and constructs DefaultSecurityFilterChain
    |
FilterChainProxy uses the built SecurityFilterChain
    |
HTTP request --> select chain --> run filters --> controller or error response
~~~

The diagram describes responsibilities, not an assertion that all objects are created in a single step or have a fixed `postProcess` call count.

**`HttpSecurity`** is the builder for a `SecurityFilterChain`. **`AbstractHttpConfigurer`** is a builder extension point allowing configuration logic to be encapsulated. **`ObjectPostProcessor`** operates on a specific instance created during this process or fed into configuration. Spring Security provides infrastructure to autowire/initialize many security objects it creates; the default mechanism typically ties into `BeanFactory` via `AutowireBeanFactoryObjectPostProcessor`.

Two distinct phases must be separated:

| Phase | Work performed | Example |
| --- | --- | --- |
| Spring context initialization | Creating beans, injecting dependencies, applying `BeanPostProcessor` to beans | `@Bean AuditLabelProvider` |
| Building `SecurityFilterChain` | Running configurers, creating filters, calling `postProcess` on suitable objects, ordering the filter chain | `postProcess(new AuditHeaderFilter())` |
| HTTP request | Filters and `AuthorizationManager` process real requests | `doFilterInternal`, checking `Authentication` |

An object instantiated with `new` in a custom configurer **does not automatically become a Spring bean**. Explicitly calling `postProcess(...)` routes the object through Spring Security's object-processing infrastructure; depending on the implementation, that infrastructure can use `BeanFactory` to autowire and initialize it. That does not mean the object is automatically registered in the entire Servlet filter chain.

## 3. What ObjectPostProcessor solves and what should not be delegated to it

### Appropriate

`ObjectPostProcessor` is useful when a configurer/framework **already creates the object**, yet you need to act on that object at a supported processing point. For example:

- Completing dependencies and lifecycle of a filter created with `new` inside a custom `SecurityConfigurer`.
- Adjusting a property on a specific security object that a builder/configurer deliberately passes through post-processing.
- Inserting extra logic at a post-processor extension point exposed and documented by the current API.
- Inspecting or recording configuration details of an object at chain-build time, with appropriate cost and log hygiene.

### Not its default purpose

- Not a mechanism to run after every HTTP request; use a `Filter`, `HandlerInterceptor`, or appropriate event for request logic.
- Does not replace `authorizeHttpRequests`, `hasRole`/`hasAuthority`, `SecurityContext`, or `AuthenticationProvider`.
- Does not automatically modify all filters or beans in the application merely because you declare a class implementing `ObjectPostProcessor<T>`.
- Does not replace Spring Framework's `BeanPostProcessor` to intercept every bean's lifecycle.
- Not an API for safely mutating a `SecurityFilterChain` after the application is running and serving requests.
- Does not itself guarantee filter order. Filter order is still decided by `HttpSecurity` configuration and `addFilterBefore`/`addFilterAfter`/`addFilterAt`.

**Selection principle:** use the highest-level public configuration API that meets your need. Use `ObjectPostProcessor` only when you genuinely need to customize/complete an instance during security building and a supported extension point exists.

## 4. Choosing the right extension point

| Need | Usually appropriate option | Why |
| --- | --- | --- |
| Specify which URLs require login or authority | `authorizeHttpRequests`, `requestMatchers`, `securityMatcher` | Endpoint scope/permissions express chain config intent |
| Enable HTTP Basic, form login, session, CSRF, headers | `HttpSecurity` DSL/`Customizer` | Uses official support with minimal implementation coupling |
| Replace user/password source or `AuthenticationProvider` | `UserDetailsService`, `AuthenticationProvider`, `AuthenticationManager` when needed | Handles authentication logic at the right responsibility layer |
| Dynamic permission rules, custom policy checks | `AuthorizationManager` / method security | Authorization based on request or business rules |
| Add real request/response processing | Servlet `Filter`, `OncePerRequestFilter`, and `http.addFilterBefore`/`After` | Per-request execution logic with explicit placement |
| Encapsulate a reusable configuration set | `AbstractHttpConfigurer` and `http.with(...)` in Spring Security 6.2+ | Groups interacting settings into dedicated config |
| Finalize a security object being created by a configurer | `ObjectPostProcessor` / `postProcess(...)` | Acts on a specific instance at build time |
| Process all Spring beans along general lifecycle | `BeanPostProcessor` / `@Bean` / dependency injection | Belongs to Spring container scope, not security-specific |

### Design priority order

If you want `/api/private` to require a read permission, use `authorizeHttpRequests` first. If you want to attach a trace ID per request, use a filter. If you want to inject a helper bean into a filter you explicitly construct with `new` inside a custom configurer, `postProcess(...)` may be the needed step. If you want to share a security configuration across multiple chains, encapsulate it in an `AbstractHttpConfigurer` or a clear configuration method.

**Do not use `ObjectPostProcessor` to bypass `securityMatcher` rules or replace request authorization.** Every `SecurityFilterChain` must still be properly selected; post-processing will not make a filter run in a chain that a request never enters.

## 5. Complete example: post-processing a custom filter to inject a dependency

We will build a minimal Spring Boot Servlet app with `GET /public/hello`. A custom filter will add the header `X-Demo-Audit: component-extended` to the response. The filter requires a Spring-managed `AuditLabelProvider` dependency.

The main learning point is inside `AuditConfigurer`'s `configure` method:

~~~java
AuditHeaderFilter filter = postProcess(new AuditHeaderFilter());
http.addFilterBefore(filter, AuthorizationFilter.class);
~~~

The first line creates the filter and then **asks the Security configuration infrastructure's default `ObjectPostProcessor` to process the object**, including autowiring dependencies under standard Spring configuration. Only the second line inserts the filter into `SecurityFilterChain` at an explicit position. If you simply construct with `new` and call `addFilterBefore` without a corresponding dependency injection mechanism, the new instance's `@Autowired` field may remain uninitialized.

### 5.1. Dependencies and project structure

The app uses Spring Boot 3.2+ with Spring Security 6.2+ for the `http.with(...)` call in the example. In a Spring Boot project that already has matching plugins and dependency management, two starters are required:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

The example uses Gradle Groovy DSL; if the learning module already declares these dependencies, do not duplicate them. You cannot compile these files with plain `javac` without Spring libraries on the classpath.

File structure:

~~~text
src/main/java/dev/example/securityextension/
    SecurityExtensionApplication.java
    AuditLabelProvider.java
    AuditHeaderFilter.java
    AuditConfigurer.java
    SecurityConfig.java
    HelloController.java
src/test/java/dev/example/securityextension/
    SecurityExtensionTest.java
~~~

### 5.2. Spring Boot entry point

File `SecurityExtensionApplication.java`:

~~~java
package dev.example.securityextension;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityExtensionApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityExtensionApplication.class, args);
    }
}
~~~

### 5.3. Spring-managed dependency

File `AuditLabelProvider.java`:

~~~java
package dev.example.securityextension;

import org.springframework.stereotype.Component;

@Component
public class AuditLabelProvider {
    public String getLabel() {
        return "component-extended";
    }
}
~~~

`AuditLabelProvider` is a normal `ApplicationContext` bean. In this example it returns a fixed label for easy verification. A real system can use a service/logging component or concrete audit rules; never put passwords, tokens, or session IDs into headers or logs.

### 5.4. Filter instantiated with `new`

File `AuditHeaderFilter.java`:

~~~java
package dev.example.securityextension;

import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.filter.OncePerRequestFilter;

public class AuditHeaderFilter extends OncePerRequestFilter {

    @Autowired
    private AuditLabelProvider labelProvider;

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {
        response.setHeader("X-Demo-Audit", labelProvider.getLabel());
        chain.doFilter(request, response);
    }
}
~~~

The filter has no `@Component` and is not declared as a `@Bean` in this example. It is explicitly created via `new AuditHeaderFilter()` inside the custom configurer and then passed through `postProcess(...)`.

Characteristics:

- `OncePerRequestFilter` avoids re-executing the same filter logic multiple times within one request dispatch per its contract; async/error dispatch behavior must be examined separately if the application requires it.
- The filter must call `chain.doFilter(...)` so the request continues. Subsequent filters can still reject the request.
- `X-Demo-Audit` is a demonstration header, not a standard security header, and provides no actual protection.
- Never use an audit header to grant access: access permissions belong to `AuthorizationManager` and security rules.

### 5.5. AbstractHttpConfigurer calling postProcess

File `AuditConfigurer.java`:

~~~java
package dev.example.securityextension;

import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.web.access.intercept.AuthorizationFilter;

public class AuditConfigurer
        extends AbstractHttpConfigurer<AuditConfigurer, HttpSecurity> {

    @Override
    public void configure(HttpSecurity http) {
        AuditHeaderFilter filter = postProcess(new AuditHeaderFilter());
        http.addFilterBefore(filter, AuthorizationFilter.class);
    }
}
~~~

`AbstractHttpConfigurer` inherits the ability to `postProcess` objects within the `SecurityConfigurer` mechanism. Calling `postProcess(...)` here serves to **complete the custom filter instance at chain-build time**, before `addFilterBefore` places the filter in the right position.

If the class only needs constructor injection, you can also pass an existing dependency into the filter's constructor instead of using field injection. For custom code you own yourself, constructor injection is usually clearer and easier to unit-test. The example chooses an `@Autowired` field so learners can clearly see the effect of post-processing on an object created with `new`.

### 5.6. Registering the configurer on HttpSecurity

File `SecurityConfig.java`:

~~~java
package dev.example.securityextension;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public/hello").permitAll()
                        .anyRequest().authenticated())
                .httpBasic(withDefaults())
                .with(new AuditConfigurer(), withDefaults())
                .build();
    }
}
~~~

Here:

1. `authorizeHttpRequests` specifies `/public/hello` is public and other paths require authentication.
2. `httpBasic` enables HTTP Basic for requests requiring authentication. Since the example only tests public GET, no demo account is needed.
3. `http.with(...)` attaches `AuditConfigurer`. This syntax applies to Spring Security 6.2+; older versions had `apply(...)` with deprecation/support differences. When upgrading, use the current API of your running version.
4. `http.build()` triggers the configuration lifecycle, during which `AuditConfigurer.configure(...)` creates the filter and calls `postProcess(...)`.
5. `AuditHeaderFilter` sits **before `AuthorizationFilter`** in the chain due to `http.addFilterBefore`. It can still run on `permitAll` endpoints because `permitAll` is an authorization decision, not a request to skip all filters.

This is a single chain with a default matcher covering all requests; no other chains are added in the example to avoid priority bugs unrelated to this lesson.

### 5.7. Endpoint

File `HelloController.java`:

~~~java
package dev.example.securityextension;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping("/public/hello")
    public String hello() {
        return "HELLO";
    }
}
~~~

### 5.8. Running and observing

In the Spring Boot project directory configured with the Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

In a standard Windows PowerShell environment, use `./gradlew.bat bootRun` if the wrapper is saved as `gradlew.bat`. Once the application starts on default port 8080, try:

~~~bash
curl -i http://localhost:8080/public/hello
~~~

Key result to look for in the response (ignoring headers added automatically by the container or Spring Boot, as well as dynamic dates/times):

~~~http
HTTP/1.1 200
X-Demo-Audit: component-extended

HELLO
~~~

`HTTP/1.1 200` and the header/body above are an **expected illustration** of the endpoint, not a claim that this is the exact byte-for-byte response of every container. To view only the body with `curl` in an environment without conflicting aliases:

~~~bash
curl -s http://localhost:8080/public/hello
~~~

The body is strictly `HELLO`, with no extra newline added by the controller.

Why does the header appear? Because the filter received an injected `AuditLabelProvider` after `postProcess(...)` and was added to the `SecurityFilterChain`; requests to `/public/hello` traverse the filter before reaching the controller. When testing one specific chain, do not assume this header will appear in other chains if the application has multiple `SecurityFilterChain`s.

**Do not send HTTP Basic with real credentials over plain HTTP outside localhost.** In networked environments, always use HTTPS and control headers/logs containing sensitive info.

### 5.9. Automated tests

Add `SecurityExtensionTest.java` at `src/test/java/dev/example/securityextension/`:

~~~java
package dev.example.securityextension;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityExtensionTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointUsesPostProcessedFilter() throws Exception {
        mvc.perform(get("/public/hello"))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        "X-Demo-Audit", "component-extended"))
                .andExpect(content().string("HELLO"));
    }
}
~~~

Run:

~~~bash
./gradlew test
~~~

The test verifies observable behavior: the public request still passes through the custom filter and the filter's dependency is ready. If you remove `postProcess(new AuditHeaderFilter())` and replace it with an instance created via `new` without passing/injecting `AuditLabelProvider`, the test can fail due to a null dependency. Never deliberately push a configuration missing injection to a real environment.

Note: this test case verifies **final request behavior**, not the count of times the framework called `postProcess` or that every filter went through the same callback. To verify post-processing of a specific object, use build-time configuration/inspection or unit tests dedicated to that component.

## 6. If you only want a custom filter, do you need ObjectPostProcessor?

Not always. If you own the filter and already have the dependencies, constructor injection or making the filter a suitable bean are also good options.

Conceptual constructor injection example (an excerpt, not a complete class):

~~~java
public AuditHeaderFilter(AuditLabelProvider labelProvider) {
    this.labelProvider = labelProvider;
}
~~~

When building the configurer, you can pass an already-available `AuditLabelProvider` into the constructor instead of relying on field autowiring through `ObjectPostProcessor`. That makes dependencies explicit in the constructor and usually easier to test. When framework code itself builds a component whose constructor you do not call directly, post-processing becomes more useful if the configurer's extension point allows it.

If you turn a filter into a Spring bean and also add that bean into a Spring Security chain, remember **Spring Boot can auto-register `Filter` beans in the Servlet container**. Adding the same filter to `HttpSecurity` risks executing the filter at two layers. When you want a filter bean to run only inside the security chain, use `FilterRegistrationBean` with `setEnabled(false)` to disable automatic Servlet container registration and add it in the right place in `HttpSecurity`.

Some filters need to run **before or after security filters**; `addFilterBefore`/`addFilterAfter` specify relative position. `ObjectPostProcessor` is not a tool for adjusting that order. Filters that apply application-wide and are unrelated to security may belong as container-level Servlet Filters rather than being forced into `SecurityFilterChain`.

## 7. Customizing a component created by Spring Security itself

The previous section illustrated a custom configurer creating an object and calling `postProcess(...)`. Another scenario is when the framework/configurer creates a component and you want to change its properties.

Three things must be clear:

1. **Exact object type**: `ObjectPostProcessor<AuthorizationFilter>` can only process objects of type `AuthorizationFilter` per its contract. It does not magically become a processor for `BasicAuthenticationFilter` or every Spring bean.
2. **Exact lifecycle attachment point**: merely creating a processor variable or marking the processor class with `@Component` **is not enough** to make the framework apply it to your target object. You must register it via an extension point supported by the running version's builder/configurer, or call `postProcess` at the site that truly owns the object's lifecycle.
3. **Exact component API**: do not modify private fields or rely on unguaranteed internal ordering. When the framework replaces a filter class or changes extension points between versions, old custom processors may stop running.

Example implementing a specialized processor's contract (this class only demonstrates the callback and **is not yet registered in any `SecurityFilterChain`**):

~~~java
package dev.example.securityextension;

import org.springframework.security.authorization.AuthorizationEventPublisher;
import org.springframework.security.config.annotation.ObjectPostProcessor;
import org.springframework.security.web.access.intercept.AuthorizationFilter;

public final class AuthorizationEventsProcessor
        implements ObjectPostProcessor<AuthorizationFilter> {

    private final AuthorizationEventPublisher publisher;

    public AuthorizationEventsProcessor(AuthorizationEventPublisher publisher) {
        this.publisher = publisher;
    }

    @Override
    public <O extends AuthorizationFilter> O postProcess(O filter) {
        filter.setAuthorizationEventPublisher(publisher);
        return filter;
    }
}
~~~

The purpose of the example is reading the generic signature properly: `O` must be a subtype of `AuthorizationFilter`, and the callback sets the publisher and returns that same object. Code using `AuthorizationFilter` APIs may need re-verification on upgrades; **do not merely drop this standalone class into a project assuming it will be called automatically**. When wanting to apply it to an `AuthorizationFilter` created by a configurer, locate the official extension point for your exact Spring Security version and verify with a test that the callback actually executes.

`AuthorizationEventPublisher` serves to observe authorization decision events; it is not a place to replace `AuthorizationManager` or arbitrarily alter access decisions. Logging every success/failure in a large system can produce heavy event volume and overhead, so choose an appropriate observability policy.

### Watch out for legacy FilterSecurityInterceptor examples

Many guides use `ObjectPostProcessor<FilterSecurityInterceptor>` alongside `authorizeRequests(...)` or `ExpressionUrlAuthorizationConfigurer`. That is the older authorization model. With modern `authorizeHttpRequests`, the typical components are **`AuthorizationFilter`** and `AuthorizationManager`. Do not mechanically copy `FilterSecurityInterceptor` hooks expecting them to modify `AuthorizationFilter`; the two objects have different types and configuration mechanisms.

When you need to change permission policies, prefer `authorizeHttpRequests` or a dedicated `AuthorizationManager`. When you need auditing, prefer supported public events/hooks. Only use component-deep processors when the current version's supported API genuinely provides that path.

## 8. Distinguishing ObjectPostProcessor from BeanPostProcessor

Their similar names make them easy to confuse.

| Mechanism | Scope | Who calls it? | When |
| --- | --- | --- | --- |
| Spring Security's `ObjectPostProcessor<T>` | Specific objects during security construction | Security builder/configurer or code calling `postProcess` | When configuring/assembling security objects |
| Spring Framework's `BeanPostProcessor` | Beans created by the Spring container per bean lifecycle | `BeanFactory`/`ApplicationContext` | Around bean initialization |
| `@Bean` / `@Component` | Declares Spring-managed objects | Spring container | During bean creation |
| Servlet `Filter#doFilter` | Actual request/response | Servlet container/`FilterChainProxy` | Each matching request/dispatch |

Framework-created objects are not always direct application beans. The default `ObjectPostProcessor` can use `BeanFactory` capabilities to autowire and initialize an object created by Spring Security. This is an important **lifecycle bridge**, yet it does not make `ObjectPostProcessor` and `BeanPostProcessor` identical.

Avoid declaring a global `ObjectPostProcessor<Object>` and trying to mutate every object via `instanceof` when a more targeted mechanism suffices. An overly broad processor can produce unintended side effects across multiple `SecurityFilterChain`s or break when Spring Security updates internal object types.

## 9. Relationship to SecurityFilterChain and multiple chains

Spring Security Servlet typically has one or more `SecurityFilterChain`s. A request is routed by `FilterChainProxy` into the **first matching chain** in priority order. A custom configurer and its post-processing only affect the chains where that configuration is applied as designed.

Scope illustration:

~~~text
@Order(1) /api/** -> API chain (has AuditConfigurer)
@Order(2) all remaining requests -> Web chain (no AuditConfigurer)

GET /api/orders -> API chain -> audit filter
GET /web/home   -> Web chain -> no audit filter from API
~~~

This illustrates a two-chain configuration, not the bean list of section 5's sample app. If a configurer is attached to the API chain, its filter does not automatically appear in the web chain. A processor with a different global/contextual scope must be checked separately because it may affect multiple objects; never assume scope from class names alone.

To add a configurer to multiple chains, do so intentionally and test each `SecurityFilterChain`. Understand that `securityMatcher`, `@Order`, filter order, and `authorizeHttpRequests` rules are independent decisions from object post-processing.

## 10. How to verify which component was extended

Evaluate an `ObjectPostProcessor`-level change through both configuration and behavior:

- **Test public API output:** `/public/hello` returns HTTP 200, exact `X-Demo-Audit` header, and body `HELLO`. Section 5's test fits here.
- **Inspect object/lifecycle when needed:** use logs or tests to observe the `postProcess` callback being invoked and returning the expected object, rather than guessing from the processor class's existence.
- **Verify the right chain:** make sure real requests match the chain carrying the custom configurer/filter, especially when multiple `securityMatcher`s exist.
- **Inspect filter lists:** `FilterChainProxy.getFilterChains()` and `SecurityFilterChain.getFilters()` show the constructed filter list, which differs from the container's Servlet Filter list.
- **Check injection:** dependencies in the filter must be present before processing requests; when using a custom processor, verify types and lifecycle timing.
- **Check security:** protected endpoints still require authentication/authorization, CSRF/session are not accidentally disabled, and custom filters do not log credentials.

Enable DEBUG/TRACE for `org.springframework.security` only in development when needed. Logs can show which filters protect requests, though formats vary across versions; avoid logging tokens, session IDs, or `Authorization` headers.

Example logging config for observation in dev:

~~~yaml
logging:
  level:
    org.springframework.security: DEBUG
    org.springframework.security.web.FilterChainProxy: TRACE
~~~

Do not read one log line and conclude `postProcess(...)` ran if the log only shows the filter is present. Inspect the created object directly or test outputs like headers for stronger evidence.

## 11. Common mistakes and fixes

### Mistake 1: Thinking implementing ObjectPostProcessor takes effect automatically

A class implementing `ObjectPostProcessor<T>` without being hooked into the proper lifecycle is merely an uninvoked callback object. Find the exact configuration/builder site creating the object and the extension point where the callback is registered; verify with tests.

### Mistake 2: Using ObjectPostProcessor to drive request handling

Code that needs to inspect URLs, headers, or security context per request belongs in a `Filter` or `AuthorizationManager` with the right responsibility. `postProcess(...)` executes at build time, holds no per-call Request/Response, and must not store request data in singleton state.

### Mistake 3: Confusing postProcess with full Spring bean machinery

Calling `new AuditHeaderFilter()` and placing it directly in a chain does not automatically guarantee `@Autowired` processing like a Spring-created bean. If using field injection on a newly instantiated object, you need `postProcess(...)` or another valid injection mechanism. For code you own, constructor injection minimizes surprises.

### Mistake 4: Using the wrong processor type or generic error

`ObjectPostProcessor<AuthorizationFilter>` does not substitute for `ObjectPostProcessor<FilterSecurityInterceptor>`. Keep the exact generic method `<O extends T> O postProcess(O object)` and return a compatible object. Arbitrary raw types or casts lose compile-time type checking.

### Mistake 5: Adding a filter to the wrong chain or wrong position

`ObjectPostProcessor` does not decide which chain `FilterChainProxy` selects. Check `securityMatcher` and `@Order`. To position a filter before/after an existing filter, use `addFilterBefore`/`addFilterAfter` per contract; do not assume a processor will fix ordering.

### Mistake 6: Registering a filter twice

A filter marked `@Component` or `@Bean` while also passed to `HttpSecurity` can be registered once by the Servlet container and used again by `SecurityFilterChain`. Inspect registration and, if needed, use `FilterRegistrationBean.setEnabled(false)` to disable auto-registration at the Servlet layer.

### Mistake 7: Deeply modifying internal objects when better extension points exist

Trying to mutate private fields, relying on legacy filter classes, or using reflection can break on upgrades. Prefer DSL/`Customizer`, `AuthenticationProvider`, `AuthorizationManager`, filters, or `SecurityConfigurer` first. Verify the current version's API when using `ObjectPostProcessor`.

### Mistake 8: Forgetting to check security impact

A custom audit filter must not accidentally return 200 for protected requests, skip `chain.doFilter`, or swallow `AuthenticationException`/`AccessDeniedException`. Never disable CSRF just to quick-test a component. If a filter holds state, make it thread-safe; Spring Security filters can serve multiple requests concurrently.

### Mistake 9: Keeping request state inside a post-processor

`postProcess(...)` serves object configuration and may run at Spring startup when creating multiple chains. Never use mutable fields on a post-processor as a store for sessions or `Authentication` across requests. Request data must be managed via `SecurityContext`, request scope, or an appropriate mechanism.

### Mistake 10: Ignoring differences across Spring Security versions

`http.with(...)` applies in Spring Security 6.2+; many older guides use `http.apply(...)`. Legacy `authorizeRequests`/`FilterSecurityInterceptor` are not fully equivalent to `authorizeHttpRequests`/`AuthorizationFilter`. Read the API of the exact running version and maintain integration tests before upgrading.

## 12. Selection and self-check checklist

Before introducing a new extension into Spring Security Servlet, answer:

1. Does this need run at configuration initialization time or on every HTTP request?
2. Who owns the object being modified: your code, the Spring container, or the framework/configurer?
3. Does DSL/`Customizer`/`@Bean`/`AuthenticationProvider`/`AuthorizationManager` support it directly?
4. If using `ObjectPostProcessor`, at what exact location is the callback registered/invoked, and with what generic type?
5. Does the returned object have the right dependencies, avoid duplicate registration, and land in the right `SecurityFilterChain`?
6. When multiple chains exist, do key requests hit the expected chain and filter order?
7. Which test proves safe behavior rather than merely proving the class was created?

Practice questions:

- How does `ObjectPostProcessor<T>` differ from `BeanPostProcessor` in scope and invocation timing?
- In `AuditConfigurer.configure(...)`, why call `postProcess(new AuditHeaderFilter())` before `addFilterBefore`?
- If a filter is both a `@Component` and inside a `SecurityFilterChain`, what is the duplicate-execution risk?
- Why does simply creating `AuthorizationEventsProcessor` not yet alter `AuthorizationFilter`?
- If you want to change access permissions for `GET /admin`, should you use `ObjectPostProcessor` or `authorizeHttpRequests`?
- Why does a filter from the `/api/**` chain not run for a `/web/home` request?
- When migrating from legacy `authorizeRequests` to `authorizeHttpRequests`, why might a processor targeting `FilterSecurityInterceptor` no longer fit?

**Key takeaway:** `ObjectPostProcessor` is an extension mechanism for **individual security objects at configuration build time**. Identify the true owner, object type, and `postProcess` call site; use higher-level configuration APIs when appropriate; and always prove results through `SecurityFilterChain` and real requests.