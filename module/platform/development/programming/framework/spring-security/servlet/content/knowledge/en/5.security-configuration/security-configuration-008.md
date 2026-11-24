# AbstractHttpConfigurer and Encapsulating Reusable Security Configuration

> **Context:** Spring Security on the Servlet stack, Java 17+, Spring Boot 3, and Spring Security 6.2+ for examples using the `HttpSecurity.with(...)` API. The topic is how to create **a DSL/configurer for `HttpSecurity`** to reuse filter assembly rules and security components across multiple `SecurityFilterChain`s. This material does not apply directly to WebFlux; reactive apps use `ServerHttpSecurity` and a different configuration model.

## 1. Why is an `AbstractHttpConfigurer` needed?

In a small application, you can configure directly via `SecurityFilterChain`:

~~~java
@Bean
SecurityFilterChain chain(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(a -> a.anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults());
    return http.build();
}
~~~

This is a **code snippet inside a `@Configuration` class**; appropriate Spring Security imports are required. As a large application grows to have multiple chains, modules, or services, identical assembly snippets appear in many places: adding an internal filter, setting up shared objects, positioning filters, or packaging a configuration set according to a policy.

`AbstractHttpConfigurer` is the base class for building **configuration extensions for `HttpSecurity`**. It encapsulates that logic in a component with:

- **Clear configuration parameters:** DSL callers can invoke fluent setters before building the chain.
- **Two lifecycle phases:** `init(...)` for preparation and `configure(...)` for assembling into the builder.
- **Per-builder/per-chain reusability:** one configurer type can be instantiated separately for different chains.
- **Standard Spring Security enable/disable or integration:** fits cleanly into the `http.build()` pipeline.

It **does not replace** `SecurityFilterChain`, `AuthenticationManager`, or `SecurityContextRepository`. Nor is it a servlet filter: **the configurer runs when building configuration**, while the servlet filters it registers run **on each matching HTTP request**.

### Architectural view

~~~text
Application startup
  -> @Bean SecurityFilterChain(HttpSecurity http)
  -> http.with(new MyConfigurer(), customizer)
  -> http.build()
       -> init() of SecurityConfigurers
       -> configure() of SecurityConfigurers
       -> builds DefaultSecurityFilterChain

When an HTTP request arrives
  -> FilterChainProxy selects SecurityFilterChain by request matcher
  -> servlet Filters installed in the chain process the request
  -> controller/response
~~~

Therefore, if configuration is misordered, registers duplicate filters, or misses a chain, the bug originates from **how the chain is built**. If a filter fails while processing a request, examine both its execution position and runtime filter logic; these two issues must be distinguished.

## 2. Generic signature and key methods

For `HttpSecurity`, an extension class typically looks like:

~~~java
public final class MyConfigurer
        extends AbstractHttpConfigurer<MyConfigurer, HttpSecurity> {
    // Options and lifecycle hooks go here.
}
~~~

Meaning of the generics and methods:

| Component | Purpose |
| --- | --- |
| `MyConfigurer` | Concrete configurer type so fluent methods can return that exact type. |
| `HttpSecurity` | Builder type being extended on the Servlet stack. |
| `init(HttpSecurity http)` | Initialization phase: validate config, create and publish shared objects, apply dependent config if needed. |
| `configure(HttpSecurity http)` | Configuration phase: assemble filters or consume prepared shared objects. |
| `disable()` | Inherited API that can request removing the configurer from the builder **before build**. |
| `http.with(configurer, customizer)` | Registers the configurer and sets its options (API provided in Spring Security 6.2+ versions). |
| `http.build()` | Runs the builder lifecycle and creates a `SecurityFilterChain`. |

Both `init` and `configure` are hooks; you can override only the hooks actually needed. Not every configurer needs to create shared objects or add filters. Low-level internals inside the builder vary across versions; avoid relying on internal details instead of public API contracts.

### Two-phase ordering

During `http.build()`, Spring Security initializes configurers first and configures them afterward. Conceptually:

~~~text
Customizer of each configurer (when calling http.with(...))
            |
            v
init(A) -> init(B) -> init(C)
            |
            v
configure(A) -> configure(B) -> configure(C)
            |
            v
Built SecurityFilterChain
~~~

This diagram shows **phase boundaries**, not a guarantee that all configurers run in a fixed dependency-independent order. Never assume `configure(A)` has already run while `init(B)` is executing. Use shared objects / builder-designed APIs instead of guessing when filters exist. When ordering **filters during HTTP processing**, use the proper filter-ordering APIs; configuration method call order is not the sole measure.

## 3. Practical example: encapsulating a filter that attaches a request trace ID

Problem: multiple servlet security chains want to return a server-generated `X-Request-Trace` header to correlate logs with HTTP requests easily. This header **is solely for observability**, not an authentication token or access permission.

We create:

1. `TraceHeaderConfigurer`: holds the header name option; creates an immutable shared object in `init`; registers the filter in `configure`.
2. `TraceHeaderFilter`: generates a UUID per request and adds it to the response; this is the code running per HTTP request.
3. `SecurityConfig`: applies the DSL to `HttpSecurity` via `with(...)`.

The example uses Spring Boot 3 / Spring Security 6.2+ and the Jakarta Servlet API. The classes are in package `com.example.demo` inside a project with `spring-boot-starter-web` and `spring-boot-starter-security`. Plain `javac` without the Spring classpath cannot compile these integration examples.

### 3.1. Create `TraceHeaderConfigurer.java`

~~~java
package com.example.demo;

import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

public final class TraceHeaderConfigurer
        extends AbstractHttpConfigurer<TraceHeaderConfigurer, HttpSecurity> {

    private String headerName = "X-Request-Trace";

    // Fluent option: called before http.build().
    public TraceHeaderConfigurer headerName(String value) {
        if (value == null || !value.matches("[A-Za-z0-9-]{1,64}")) {
            throw new IllegalArgumentException("Invalid trace header name");
        }
        this.headerName = value;
        return this;
    }

    @Override
    public void init(HttpSecurity http) {
        // Shared object belongs to one HttpSecurity builder, not a JVM-wide variable.
        http.setSharedObject(
                TraceHeaderSettings.class,
                new TraceHeaderSettings(headerName)
        );
    }

    @Override
    public void configure(HttpSecurity http) {
        TraceHeaderSettings settings =
                http.getSharedObject(TraceHeaderSettings.class);
        if (settings == null) {
            throw new IllegalStateException("Trace settings were not initialized");
        }

        http.addFilterBefore(
                new TraceHeaderFilter(settings.headerName()),
                UsernamePasswordAuthenticationFilter.class
        );
    }

    public record TraceHeaderSettings(String headerName) {}
}
~~~

**Points to understand:**

- `headerName(...)` runs **when configuring the chain**, before `http.build()`. It is not called per request.
- `TraceHeaderSettings` is an immutable Java 17 record; `setSharedObject` stores it per **current builder** so other configurers (if designed compatibly) can access it. For a problem with just one filter, you could also use the `headerName` field directly in `configure` and omit the shared object; the example uses a shared object to demonstrate the role of the `init` phase.
- `configure` adds the filter at a known position in the Spring Security chain, before `UsernamePasswordAuthenticationFilter.class`. The ordering API works by reference class; you do not need to instantiate a `UsernamePasswordAuthenticationFilter` yourself.
- With the current placement, the trace filter **runs before the form-login authentication step**; therefore do not read an authenticated principal there assuming it is already populated. To run post-authentication logic, pick an appropriate anchor/design and verify the actual filter chain.
- `TraceHeaderSettings` is a dedicated shared object type for illustration. If multiple configurers write objects with the same `Class` on one builder, they can overwrite one another; keep naming and ownership clear.

### 3.2. Create `TraceHeaderFilter.java`

~~~java
package com.example.demo;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.UUID;
import org.springframework.web.filter.OncePerRequestFilter;

public final class TraceHeaderFilter extends OncePerRequestFilter {
    private final String responseHeaderName;

    public TraceHeaderFilter(String responseHeaderName) {
        this.responseHeaderName = responseHeaderName;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        // Always generate the ID on the server; do not trust client-sent header values.
        response.setHeader(responseHeaderName, UUID.randomUUID().toString());
        chain.doFilter(request, response);
    }
}
~~~

This is a minimal filter: it does not read/write `SecurityContext`, create sessions, or grant permissions. `OncePerRequestFilter` provides "once" semantics according to the filter's dispatch policy, not a guarantee that an asynchronous HTTP request runs this code once in every scenario. Behavior on `ASYNC`/`ERROR` dispatches depends on appropriate configuration/overrides.

Do not register this class a second time with `@Component` or `FilterRegistrationBean` once it is placed inside a Spring Security chain; if Spring Boot auto-registers a `Filter` as a standalone servlet filter, it can execute outside the security chain, causing duplicate processing or wrong ordering.

### 3.3. Create `SecurityConfig.java`

~~~java
package com.example.demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain appSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .with(new TraceHeaderConfigurer(), trace ->
                trace.headerName("X-Request-Trace"));

        return http.build();
    }
}
~~~

`with(new TraceHeaderConfigurer(), trace -> trace.headerName(...))` performs two steps: registering the configurer on the builder and customizing that object **before build**. Only when `http.build()` is called does Spring Security run the lifecycle hooks. The result is a `SecurityFilterChain` containing `TraceHeaderFilter` alongside the filters provided by authentication/authorization configuration.

The example uses HTTP Basic for protected endpoints to make the filter chain clear. `.requestMatchers("/public").permitAll()` only lets the public endpoint pass the **authorization step**; it **does not bypass all Spring Security filters**. Thus `/public` requests still receive the trace header.

### 3.4. Sample endpoint `PublicController.java`

~~~java
package com.example.demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PublicController {
    @GetMapping("/public")
    public String publicPage() {
        return "ok";
    }
}
~~~

Place the classes above in a package scanned by Spring Boot (for example under the package containing `@SpringBootApplication`). A normal Boot application already has a main class and build file; the files above are **additions to a project**, not a full standalone Maven/Gradle project.

After running the application with appropriate configuration, try:

~~~bash
curl -i http://localhost:8080/public
~~~

Expect HTTP `200`, body `ok`, and **one header** `X-Request-Trace` containing a server-generated UUID. The UUID changes on each call, and other headers depend on the container; do not hardcode an unrealistic fixed output. A `GET` to a path requiring authentication without sending credentials is handled by authorization/authentication per the HTTP Basic configuration; that is the chain's outcome, not the trace filter's.

## 4. How can one configurer be shared across multiple SecurityFilterChains?

In an application with both `/api/**` and a web part, you can use the **same configurer class** while **creating a new instance per chain** and configuring options independently:

~~~java
package com.example.demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class MultiChainSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(a -> a.anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .with(new TraceHeaderConfigurer(), t ->
                t.headerName("X-Api-Trace"));

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain web(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(a -> a
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .with(new TraceHeaderConfigurer(), t ->
                t.headerName("X-Web-Trace"));

        return http.build();
    }
}
~~~

**This configuration replaces `SecurityConfig` in section 3; do not enable both at the same time.** Enabling both simultaneously can cause catch-all chains and matcher order to route requests into unexpected chains.

At request time:

| Request | Selected chain in the alternative example | Generated header |
| --- | --- | --- |
| `GET /api/orders` | `api`, because `/api/**` matches and `@Order(1)` | `X-Api-Trace` |
| `GET /public` | `web`, because it does not match the API chain | `X-Web-Trace` |
| `GET /other` | `web`, because the web chain declares no dedicated `securityMatcher` | `X-Web-Trace` |

The illustrative endpoints `/api/orders` and `/other` may not be implemented yet; security filters can still process the request before Spring MVC looks up a handler. Do not confuse HTTP `404` (no controller) with the security chain not running.

**Crucial difference between the two matchers:**

- `securityMatcher(...)` decides **whether `FilterChainProxy` selects this chain**.
- `requestMatchers(...)` inside `authorizeHttpRequests(...)` decides **authorization rules inside the selected chain**.

A `permitAll` configuration does not guarantee custom filters are skipped. If a filter should run only for a subset of URLs, design matchers at the right level (chain or inside the filter), testing both permitted paths and paths requiring authentication.

## 5. Reusing code while keeping responsibilities clean

`AbstractHttpConfigurer` fits when you want to package **how a security chain is assembled**, not when you only need a plain Java helper function. Compare:

| Goal | Usually appropriate choice | Reason |
| --- | --- | --- |
| Attach a filter set and shared objects with `init/configure` hooks | `AbstractHttpConfigurer` | Participates cleanly in the `HttpSecurity` lifecycle. |
| Reuse a few simple `authorizeHttpRequests` rules | Helper/config method or a bean supplying a controlled customizer | Minimal state; may not need a new DSL. |
| Share business permission check logic | `AuthorizationManager`, method security, policy service | Separates authorization responsibility from filter wiring. |
| Reuse credential verification | `AuthenticationProvider`/authentication manager and auth components | Separates authentication from configurers. |
| Add a general servlet filter outside Spring Security | Explicit servlet filter registration | Does not mix container filter lifecycle with `SecurityFilterChain`. |
| Apply policy across multiple applications | Library/starter providing configurers, beans, and opt-in docs | Each application still controls its chains/matchers/options. |

A good configurer has a short, clearly named, safe-by-default API. For instance, `TraceHeaderConfigurer.headerName(...)` expresses a specific option; avoid vague methods like `enabled(boolean)` if the filter is still constructed in some branches, or methods that silently disable CSRF/sessions unexpectedly.

### Rules for designing a reusable DSL

1. **Choose the right scope:** supply the configurer for a specific `HttpSecurity`; never use `static` mutable fields to store header names, principals, or per-chain/per-request state.
2. **Finalize options before `build()`:** all setters should serve the configuration phase. Do not mutate the configurer after the chain is built expecting the running filter to change behavior.
3. **Keep options immutable when registering the filter:** the filter should receive values via its constructor, avoiding reading a mutable configurer at request time.
4. **Define shared object ownership:** the object type and creation/consumption timing must be clear. Never overwrite an existing `AuthenticationManager`/`SecurityContextRepository` or shared object just for "convenience".
5. **Never sneak in policy changes:** adding a tracing filter must not disable `csrf()`, `authorizeHttpRequests()`, `sessionManagement()`, or logout settings.
6. **Clarify filter execution order:** placement before/after authentication, authorization, and exception translation directly affects which data/exceptions are visible.
7. **Do not register the filter twice:** separate Servlet container registration from Spring Security chain configuration.
8. **Test each security chain independently:** multiple chains create multiple configurations and distinct filter sets.

## 6. Filter placement and relationship to other security components

APIs such as:

~~~java
http.addFilterBefore(myFilter, UsernamePasswordAuthenticationFilter.class);
http.addFilterAfter(myFilter, UsernamePasswordAuthenticationFilter.class);
http.addFilterAt(myFilter, UsernamePasswordAuthenticationFilter.class);
~~~

are **illustrative snippets**, requiring `myFilter` to be a servlet filter and placed where `HttpSecurity` is configured. They express intent to position relative to a filter class whose order is known to Spring Security.

- `addFilterBefore`: suitable when a filter needs to prepare metadata, correlation IDs, or data consumed by authentication logic.
- `addFilterAfter`: suitable when needing behavior after a reference filter's **position**, though that **does not by itself guarantee** an authenticated principal or uncommitted response.
- `addFilterAt`: adds at the **same order position**; do not assume it "replaces" the original filter. When two filters share an order, ordering between them is not a stable foundation for security mechanisms.

`HttpSecurity` knows the ordering of many standard filter types even when a given filter type has not been added to the chain. Still, actual filter presence and final order must be verified against the running security chain.

A tracing filter placed before `UsernamePasswordAuthenticationFilter` **should not** rely on `SecurityContextHolder.getContext().getAuthentication()` being a logged-in user: the authentication filter may not have run yet, the request may be anonymous, or another token mechanism may be in use. If you genuinely need to evaluate permissions, use `AuthorizationManager`/method security and test at the exact point in the chain.

## 7. `init()`, `configure()`, and shared objects: when to use which?

A helpful division of responsibility:

**Inside `init(...)`:**
- Validate that required options were provided or apply valid defaults.
- Create/publish an object shared during chain construction via `http.setSharedObject(Type.class, value)` when **genuinely needed**.
- Set up builder-level configuration dependencies if public APIs allow it.
- Avoid assuming all filters already exist, or accessing runtime requests/sessions.

**Inside `configure(...)`:**
- Read prepared shared objects via `getSharedObject(...)`, if needed.
- Instantiate and attach the final filter in the proper order.
- Finalize configuration that depends on builder-supplied components at this phase.
- Avoid running business logic for an HTTP request: no real request exists at this stage.

In the example above, `TraceHeaderSettings` is created as an immutable `record` in `init`, then used by `configure` to create `TraceHeaderFilter`. When no other component uses the shared object, you can write a simpler configurer:

~~~java
@Override
public void configure(HttpSecurity http) {
    http.addFilterBefore(
        new TraceHeaderFilter(headerName),
        UsernamePasswordAuthenticationFilter.class
    );
}
~~~

The snippet above is an **alternative to `configure(...)` in `TraceHeaderConfigurer`**, not code to add alongside it. Using this option, you can omit `init(...)` and `TraceHeaderSettings`. Do not add shared objects merely to make a DSL look complex.

### Be careful with builder mutations from multiple configurers

Other configurers can simultaneously interact with shared objects and the filter collection. If configurer A depends on an object from B, design a clear dependency contract, and test build order and missing-dependency errors. Never assume "because `with(A)` precedes `with(B)`, filter A always runs before B" or "`configure(A)` finishes before `init(B)`". The two phases and filter order are two separate axes.

## 8. Registering, reapplying, and disabling a configurer

Typical single application:

~~~java
http.with(new TraceHeaderConfigurer(),
        trace -> trace.headerName("X-Request-Trace"));
~~~

In Spring Security 6.2+, `with(configurer, customizer)` expresses intent more clearly than the older `apply(...)` call; `apply(...)` is deprecated in recent 6.x versions, so upgrading codebases should check the migration guide for their exact version.

Do not call `with(new TraceHeaderConfigurer(), ...)` multiple times on **the same `HttpSecurity`** as if two independent filters are guaranteed to be added: configurers can be keyed by class, so a later registration can modify or override an earlier one depending on builder and version. Create one configurer capable of accepting multiple options, or two distinct configurer classes if two responsibilities are genuinely needed.

A configurer inherits `disable()` to remove itself from the builder before build. Distinguish:

- **Not registering the configurer:** no behavior from that configurer.
- **Registering then disabling before `build()`:** expected not to run the removed configurer's filter-adding hooks; verify against your actual version.
- **Removing a configurer after `build()`:** not a mechanism for changing an already-built `SecurityFilterChain`.
- **`http.csrf(AbstractHttpConfigurer::disable)`:** disables the **CSRF configurer**, not the tracing DSL. Never copy from API tutorials into cookie/session web apps without understanding CSRF.

When a library offers multiple opt-in mechanisms, prefer a simple public API and documentation stating which chains it applies to. If a configurer holds custom state, instantiate a new one per builder; never keep a mutable instance as a singleton reused across chains.

## 9. Testing functionality and security boundaries

Given `SecurityConfig` and `PublicController` (section 3) in a standard Boot app, you can write Spring MVC tests using `MockMvc` and `spring-security-test`. File `SecurityConfigTest.java`:

~~~java
package com.example.demo;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityConfigTest {
    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointGoesThroughConfiguredFilter() throws Exception {
        mvc.perform(get("/public"))
           .andExpect(status().isOk())
           .andExpect(content().string("ok"))
           .andExpect(header().exists("X-Request-Trace"));
    }

    @Test
    void otherEndpointStillRequiresAuthentication() throws Exception {
        mvc.perform(get("/private"))
           .andExpect(status().isUnauthorized())
           .andExpect(header().exists("X-Request-Trace"));
    }
}
~~~

In the example, `/private` has no controller yet still returns `401` because security runs before MVC routing. The test does not prove every security policy of the application; it verifies **the filter is in the chain** and **authorization still works**. Applications customizing `AuthenticationEntryPoint` may return another status; the result above relies on section 3's `httpBasic(Customizer.withDefaults())`.

If the project has the Maven Wrapper and the listed dependencies, run:

~~~bash
./mvnw test
~~~

Depending on OS, Windows uses `mvnw.cmd test`. If not using the wrapper, run the project's build tool. These are **Spring Boot integration tests**, not a Java SE program with fixed stdout.

### Additional tests to write

| Scenario | What to verify |
| --- | --- |
| Single chain, `/public` request | Filter still runs even though authorization rule is `permitAll`. |
| Blocked path | Trace header does not accidentally grant access; security still returns `401/403` per policy. |
| Two chains `/api/**` and web | Each chain selects the right matcher, configures its corresponding header, with no chain shadowing. |
| Duplicate filter registration | Each request is processed the expected number of times; filter is not registered outside the chain by the servlet container. |
| Invalid header name | DSL rejects bad input before build; filter never emits a header with an invalid name. |
| Another request or concurrent requests | No static mutable state shared for request IDs; each request gets an independent value. |
| ERROR/ASYNC dispatches if app supports them | Understand dispatcher types; may re-filter or skip per config; never assume absolute "once per HTTP request". |
| Added filter must run after authentication | Test actual position and principal at the point of use, not only response status. |

When you need to inspect filter order, enable appropriate logging for `org.springframework.security.web.FilterChainProxy` in development or inspect the chain built by Spring Security. Avoid logging credentials, session cookies, access tokens, or full `SecurityContext`.

## 10. Common mistakes when encapsulating a DSL

### Mistake 1: Thinking `AbstractHttpConfigurer` handles requests

False: `init` and `configure` run when **building configuration**. Only the servlet filters added by the configurer run per request. If you need per-request logic, place it inside a `Filter`, `AuthorizationManager`, or appropriate runtime component.

### Mistake 2: Reusing one mutable instance across multiple chains

For example, holding `TraceHeaderConfigurer` as a static singleton and calling different `headerName(...)` values makes configuration and lifecycle unpredictable. For each `HttpSecurity`, instantiate `new TraceHeaderConfigurer()` and pass its own options. Likewise, filters sharing mutable request state across requests can cause race conditions.

### Mistake 3: Registering a filter across two layers

A filter that is both a container-registered `@Component` and passed to `http.addFilterBefore(...)` can execute twice or at a position inconsistent with the chain. Register intentionally at one layer; if you must use a bean filter inside a security chain, suppress Boot's external auto-registration with a `FilterRegistrationBean` per application design.

### Mistake 4: Confusing chain matcher with authorization rule

`securityMatcher("/api/**")` limits **chain selection**. `requestMatchers("/api/**").authenticated()` only sets a rule **inside the already-selected chain**. If a catch-all has higher `@Order` priority, the API chain may never be selected. Testing matchers is essential for reusability.

### Mistake 5: Not verifying actual filter order

Merely calling `with(...)` after `httpBasic(...)` does not mean the runtime filter sits after `BasicAuthenticationFilter`. Position it with `addFilterBefore/After/At` using an appropriate anchor and verify against the chain. If authentication uses multiple mechanisms, there is no single "post-login" filter for every path.

### Mistake 6: Using a configurer to disable general protections

A DSL that only adds a trace header must not alter `csrf`, `cors`, `headers`, session policy, or logout. Security-sensitive changes must be specified explicitly and risk-tested on the corresponding chains. Wrapping code does not automatically make a security policy better.

### Mistake 7: Reading a shared object before it is ready

`init(...)` and `configure(...)` are different phases. `getSharedObject(...)` can return `null` if the object type has not been created yet or was replaced by another configurer. Check preconditions, create shared objects in the right phase, or use appropriate public APIs; never call another configurer's `configure(...)` directly.

### Mistake 8: Believing `permitAll` disables custom filters

`permitAll` still traverses the chain. That is useful for logging/tracing, yet can cause trouble if a filter enforces credentials on every request itself. If certain routes should skip a filter, adjust matchers or `shouldNotFilter(...)` instead of assuming public routes are skipped.

### Mistake 9: Ignoring version upgrade compatibility

The `with(...)` API appeared in Spring Security 6.2; Spring Security 6.0/6.1 projects may use another API. When upgrading, consult release notes and compiler warnings. Never use tutorials from another major version to deduce exact constructors, hooks, or authorization rules for your current app.

## 11. Checklist before putting a configurer into a shared library

- Clearly identify **which modules/chains** need the configurer and which URLs those chains match.
- Design a small, typed DSL with validation and safe defaults.
- Keep request-specific state in filters/tasks, never in shared fields on the configurer.
- Use `init` for preparation/shared objects and `configure` for filter wiring; override only what is needed.
- Do not create or mutate `SecurityContext`/authentication/session if unrelated to the feature.
- Use `http.with(new CustomConfigurer(), customizer)` on supported versions, building each chain exactly once.
- Verify filter order and prevent container auto-registration outside the chain.
- Test positive/negative paths, multiple chains, and async/error if applicable.
- Document Spring Boot/Spring Security dependencies, Java requirements, and any changed defaults.

## 12. Review questions

**Q1. How does `AbstractHttpConfigurer` differ from a `Filter`?** A configurer extends the **`HttpSecurity` build phase**; a Filter processes **runtime HTTP requests** once installed in the chain.

**Q2. Why are `init` and `configure` called in two phases?** Configurers get a chance to prepare/publish shared objects before final filter assembly; that makes dependencies between components easier to control.

**Q3. How can one configurer be reused across multiple chains with different options?** Create a new instance per `HttpSecurity` and pass the appropriate `Customizer` into `with(...)`. Each builder produces an independent chain.

**Q4. Does `requestMatchers("/public").permitAll()` stop a custom filter from running?** No. The route still belongs to the matched security chain; `permitAll` only decides authorization.

**Q5. Does `addFilterAt(myFilter, SomeFilter.class)` automatically replace the original filter?** There is no such guarantee; it merely attaches at the same order position. Inspect the chain to avoid two filters sharing an order with undefined relative ordering.

**Q6. When should you use a helper instead of creating a configurer?** When only sharing a few simple configuration lines with no need to participate in `init/configure` phases, shared objects, or lifecycle packaging. Avoid adding a DSL layer that brings no value.

**Key takeaway:** `AbstractHttpConfigurer` encapsulates **how security configuration is assembled** into an `HttpSecurity`. Good design clarifies options, lifecycle, filter placement, and chain scope; authentication and authorization decisions must still use the security components responsible for them.
