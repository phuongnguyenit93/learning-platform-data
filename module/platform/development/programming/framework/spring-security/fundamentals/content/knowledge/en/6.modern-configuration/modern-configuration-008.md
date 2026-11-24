# Role of @EnableWebSecurity, @EnableWebFluxSecurity, and Auto-Configuration

> **Key takeaway:** `@EnableWebSecurity` and `@EnableWebFluxSecurity` activate **Spring Security**'s web security configuration infrastructure for two different runtime models. **Spring Boot auto-configuration** detects dependencies, creates default beans when appropriate, and registers security mechanisms. Meanwhile, the **`SecurityFilterChain`/`SecurityWebFilterChain` written by the developer** is where you define concrete policies such as which URLs are public, which URLs need which permissions, and which authentication method is used. These three layers are related, not synonymous.

This lesson belongs to the **Modern Configuration** group in the **Spring Security – fundamentals** module. Primary scope: Spring Boot 3.5.x, Spring Security 6.5.x, Java 17 and above, Servlet/Spring MVC and Reactive/Spring WebFlux applications. For Spring Boot 4.x / Spring Security 7.x, re-check starters, DSLs, and migration docs before copying code verbatim.

## 1. Learning Objectives

After this lesson, you can:

1. State precisely what `@EnableWebSecurity` does in a Servlet application and what `@EnableWebFluxSecurity` does in a WebFlux application.
2. Distinguish **enabling security infrastructure**, **Spring Boot auto-configuration**, **developer-declared filter chain beans**, and the **user/credential system**.
3. Explain why a Spring Boot app that merely adds `spring-boot-starter-security` already prompts for login without manually adding annotations.
4. Understand bean-conditional "back off": declaring a `SecurityFilterChain` differs from declaring a `UserDetailsService`; WebFlux has corresponding bean types.
5. Identify the right stack when a project contains both `spring-boot-starter-web` and `spring-boot-starter-webflux`.
6. Write and test two independent small projects, one using `HttpSecurity`/`MockMvc` and one using `ServerHttpSecurity`/`WebTestClient`.
7. Avoid misconceptions such as "adding the annotation permits APIs automatically," "defining users defines HTTP permissions," "`@EnableWebFlux` equals `@EnableWebFluxSecurity`," or "SecurityFilterChain enables method security automatically."

## 2. Four Layers of Responsibility, from the Outside In

```text
pom.xml / classpath
  |
  +-- spring-boot-starter-web          -> Servlet/Spring MVC application
  |               or
  +-- spring-boot-starter-webflux      -> WebFlux/reactive application
  |
  +-- spring-boot-starter-security
             |
             v
    SPRING BOOT AUTO-CONFIGURATION
    - detects web application type and existing beans
    - enables/integrates Spring Security config when conditions match
    - supplies default web security and default user if missing
             |
             v
    SPRING SECURITY WEB INFRASTRUCTURE
    Servlet: @EnableWebSecurity
       -> FilterChainProxy, HttpSecurity, SecurityFilterChain
    Reactive: @EnableWebFluxSecurity
       -> WebFilterChainProxy, ServerHttpSecurity, SecurityWebFilterChain
             |
             v
    APPLICATION SECURITY POLICY
    - SecurityFilterChain / SecurityWebFilterChain @Bean
    - authorizeHttpRequests / authorizeExchange
    - formLogin, httpBasic, oauth2ResourceServer, csrf, cors...
    - UserDetailsService / ReactiveUserDetailsService / custom providers
             |
             v
    REQUEST -> filters -> controller/handler -> service/domain policy
```

This diagram separates responsibilities; it is **not** the exact order of every class created by Spring at runtime. Both Spring Boot and Spring Security use conditional configuration, so the same dependency can yield different beans once you declare custom beans or add OAuth2, actuator, or a session manager.

### 2.1. "Who Is Responsible for What?" Table

| Component | Primary role | What it does NOT do for you |
| --- | --- | --- |
| `@EnableWebSecurity` | Activates Spring Security's **Servlet** web security configuration, integrating `SecurityFilterChain`s | Does not define business permissions, user databases, or JWT issuers |
| `@EnableWebFluxSecurity` | Activates **reactive WebFlux** security configuration, integrating `SecurityWebFilterChain`s | Does not convert Servlet filters to WebFilters or create resource policies |
| Spring Boot `SecurityAutoConfiguration` and related web config | Conditionally imports configuration and provides Servlet **defaults** when appropriate | Does not keep the default chain once you explicitly replace web security configuration |
| Spring Boot `ReactiveSecurityAutoConfiguration` | Conditionally configures Spring Security for WebFlux | Does not turn an MVC app into WebFlux |
| `UserDetailsServiceAutoConfiguration` | Can create an in-memory user `user` with a random password in Servlet | Does not grant business permissions or generate production accounts |
| `ReactiveUserDetailsServiceAutoConfiguration` | Can create a default reactive in-memory user for WebFlux | Does not replace a configured OAuth2/JWT authentication provider |
| `SecurityFilterChain` | Filter set and web policy for **Servlet requests** | Does not protect message listeners/jobs outside web filters |
| `SecurityWebFilterChain` | Reactive `WebFilter` set/web policy for WebFlux exchanges | Cannot be used as a `SecurityFilterChain` in a Servlet app |
| `@EnableMethodSecurity` | Enables imperative method authorization such as `@PreAuthorize` | Does not take effect merely because `@EnableWebSecurity` is enabled |
| `@EnableReactiveMethodSecurity` | Enables reactive method authorization suited to publishers | Does not replace `@EnableWebFluxSecurity` for the HTTP boundary |

**Tip to avoid mixing them up:** "enable" annotations decide **framework infrastructure**; "chain" beans decide **how HTTP is protected**; user stores/providers decide **how identities are verified**; method/domain policies decide **which operations on objects are allowed**.

## 3. @EnableWebSecurity: Activating Servlet Web Configuration

### 3.1. Mechanism in Spring Security

`@EnableWebSecurity` belongs to the package:

```java
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
```

When placed on a `@Configuration` class in a Servlet application, the annotation imports the configurations needed for Spring Security to create and manage web filters, typically registering the Servlet filter named `springSecurityFilterChain`. Internally, `FilterChainProxy` selects a `SecurityFilterChain` for each request; each chain contains filters matching the mechanisms you configured.

```text
Servlet container / DispatcherServlet
    ^
    |
    +-- Servlet FilterChain
          |
          +-- DelegatingFilterProxy (springSecurityFilterChain)
                  |
                  +-- FilterChainProxy
                        |
                        +-- SecurityFilterChain #1 (matcher...)
                        +-- SecurityFilterChain #2 (matcher...)
                        |
                        +-- actual filters of the selected chain
```

Explicit configuration example:

```java
@Configuration
@EnableWebSecurity
class SecurityConfig {
    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

This is a **snippet**: imports, Spring Boot app, and other beans are omitted; complete code is in Section 8. In Servlet, `HttpSecurity` is the builder; `http.build()` creates `SecurityFilterChain`. The annotation **does not define the `/public` rule**; the `authorizeHttpRequests(...)` call does that.

### 3.2. With Spring Boot, Must You Write the Annotation?

In a standard **Spring Boot Servlet** application, simply having `spring-boot-starter-security` on the classpath makes Boot enable default Spring Security configuration when auto-configuration conditions are met. Thus **you do not need to add `@EnableWebSecurity` yourself just to get default web protection**. Placing the annotation when writing explicit Java configuration can signal the class's purpose to readers, but its absence does not mean "without this annotation Boot runs no security at all."

A quick exercise:

1. Create a Boot MVC app with only Spring Web + Spring Security starters and one `@GetMapping("/hello")`.
2. **Do not declare `SecurityFilterChain`, `UserDetailsService`, or `@EnableWebSecurity` yet.**
3. Run the app; if Boot's default conditions hold, anonymous `GET /hello` requires login, and logs may print a generated password for user `user`.
4. Add a `SecurityFilterChain` bean and test behavior per your rules; this affects **web security defaults**.
5. Add a custom `UserDetailsService` bean if you want to replace the user source; this affects **authentication defaults**.

**In a Spring Framework application without Boot**, you must set up the security infrastructure and register the filter with the Servlet container yourself, for example via `@EnableWebSecurity` and `AbstractSecurityWebApplicationInitializer` or an equivalent registration mechanism. Do not treat Boot's convenience as an absolute rule for all Spring applications.

### 3.3. Does the Annotation Replace the Filter Chain Bean?

No. When web security configuration is enabled, Spring Security can provide a default security policy if no custom chain is defined. Yet if you need **custom `permitAll`**, **`hasRole` for admin**, **Bearer tokens for APIs**, or **different CSRF/session settings**, you must configure the chain and required components. The annotation does not infer that `/api/payments` requires `PAYMENT_WRITE`.

Similarly, `@EnableWebSecurity` **does not activate `@PreAuthorize` in place of `@EnableMethodSecurity`**. In Spring Security 6, method security is enabled separately:

```java
@Configuration
@EnableMethodSecurity
class MethodAuthorizationConfig {
    // Methods annotated with @PreAuthorize, @PostAuthorize...
}
```

`@EnableMethodSecurity` does not make every method restricted automatically. Methods need explicit policies, calls must pass through the proper interceptor/proxy, and per-owner/tenant logic remains the domain layer's responsibility.

## 4. @EnableWebFluxSecurity: Activating Reactive Security Configuration

### 4.1. How Does It Differ from @EnableWebSecurity?

`@EnableWebFluxSecurity` belongs to the package:

```java
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
```

It imports Spring Security **WebFlux** infrastructure, letting you build one or more `SecurityWebFilterChain`s from `ServerHttpSecurity`. Never use `HttpSecurity`/`SecurityFilterChain` as a substitute for WebFlux security.

```text
WebFlux HTTP handler
    |
    v
WebFilterChainProxy
    |
    +-- Select matching SecurityWebFilterChain
    |
    +-- Reactive WebFilters
    |      authentication, CSRF, security context,
    |      authorization, headers, ...
    |
    v
DispatcherHandler / RouterFunction
    |
    v
Reactive Controller / Handler -> Mono / Flux
```

Explicit configuration:

```java
@Configuration
@EnableWebFluxSecurity
class ReactiveSecurityConfig {
    @Bean
    SecurityWebFilterChain filterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public").permitAll()
                .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

This too is a **snippet**; the complete app is in Section 9. `authorizeExchange(...)`/`pathMatchers(...)` replace Servlet's `authorizeHttpRequests(...)`/`requestMatchers(...)` DSL. With multiple chains, reactive uses `ServerWebExchangeMatcher`, whereas Servlet uses `RequestMatcher`.

### 4.2. Reactive SecurityContext Is Not the Same as Servlet's ThreadLocal

Servlet typically uses `SecurityContextHolder` backed by a request thread's `ThreadLocal`. In WebFlux, execution can switch threads; security information is retrieved via `ReactiveSecurityContextHolder` in **Reactor Context**. Writing custom reactive code relying on Servlet-style `SecurityContextHolder.getContext()` easily loses the identity. Reactive services should use publisher-aware APIs or accept verified identities from the right boundary.

### 4.3. WebFlux Auto-Configuration in Spring Boot

Boot has separate `ReactiveSecurityAutoConfiguration` and `ReactiveUserDetailsServiceAutoConfiguration`. When you use `spring-boot-starter-webflux` + the security starter, Boot can supply default reactive web security and a generated account if no custom configuration exists. `@EnableWebFluxSecurity` is useful when configuring explicitly or running without Boot, yet **it is not the sole condition for a Boot WebFlux application to have security**.

Furthermore:

- WebFlux Spring Security is built on `WebFilter` and can run on Reactor Netty or Servlet-based servers in WebFlux mode; the name WebFlux refers to the **reactive programming model**, not merely the web server name.
- `@EnableWebFlux` belongs to **Spring Framework**, enabling WebFlux's MVC-equivalent configuration; it **does not replace** `@EnableWebFluxSecurity`, and using it carelessly can cause Boot's WebFlux auto-configuration to back off.
- `@EnableWebMvc` likewise belongs to Spring MVC; it is **not** how you enable Servlet Spring Security.
- Reactive method authorization requires `@EnableReactiveMethodSecurity`; never take enabled web filters as proof that method policies are running.

## 5. Boot Auto-Configuration: What Comes Out of the Box?

### 5.1. Servlet/MVC Defaults

With Spring Boot 3.5, if Spring Security is on the classpath, web applications are usually protected even with no custom configuration. Per Boot documentation, defaults can include:

- An in-memory `UserDetailsService` containing user `user` with a randomly generated password, logged at WARN on startup; for development only.
- Form login or HTTP Basic depending on how clients send requests (e.g., `Accept`), requiring authentication for the web app.
- `DefaultAuthenticationEventPublisher` for authentication events.
- HTTP protective filters configured by Spring Security (CSRF, security headers, session behavior...) with appropriate defaults.

These behaviors are subject to **auto-configuration conditions**: if OAuth2/SAML libraries, custom beans, test profiles, or properties change, the actual set can differ. Do not treat a single log line as complete proof of the security chain; write HTTP tests.

A quick lesson on defaults:

```java
// Simple Boot MVC app with only @SpringBootApplication
// + spring-boot-starter-web + spring-boot-starter-security.
// No need to add @EnableWebSecurity manually to see default web security.
@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

Without other chains/users/providers, Boot creates the appropriate components. However, compiling the snippet standalone requires package/imports and a `pom.xml`; complete examples appear in the hands-on sections.

### 5.2. WebFlux Defaults

In WebFlux, Boot can create a `ReactiveUserDetailsService` and a reactive security pipeline with a default user and login requirement. Bean types to distinguish include:

- `SecurityWebFilterChain`: policy and filters for each reactive exchange.
- `WebFilterChainProxy`: dispatches across reactive chains.
- `ReactiveUserDetailsService` / `ReactiveAuthenticationManager`: authenticates users in the reactive world.
- `ServerHttpSecurity`: builder for the chain.

Do not substitute Servlet's `UserDetailsService` for `ReactiveUserDetailsService` and assume Boot wired reactive authentication properly. When using a JWT Resource Server, reactive decoders and `ReactiveAuthenticationManager` have their own requirements; never treat the generated user as a production model.

### 5.3. Default User Can Be Configured via Properties, Not as an ACL

In labs using the default user, you can configure:

```properties
spring.security.user.name=student
spring.security.user.password=local-demo-password
spring.security.user.roles=USER
```

**For local development/testing only.** Once you provide your own `UserDetailsService` or reactive equivalent, Boot may stop creating the default user. These properties **do not configure URL authorization**. Setting `roles=ADMIN` on a user only grants that authority in the default user store; it does not create admin APIs or alter HTTP rules.

In production, storing configured plaintext passwords in Git is unsafe; use an identity provider/secret management and protect credentials over HTTPS.

## 6. What Is "Back Off," and Which Beans Change the Defaults?

Spring Boot uses conditions like `@ConditionalOnMissingBean` to provide a component **only when the application has not defined one itself**. Therefore, "I customized Spring Security" can mean very different things.

| What the app does | What typically changes | What you must **NOT** infer automatically |
| --- | --- | --- |
| Adds only the security starter | Boot enables web security defaults when conditions hold | Business users are already integrated |
| Adds only `@EnableWebSecurity` in Boot MVC | Requests loading Servlet security infrastructure (already supported by Boot in standard setup) | APIs are public or custom permissions exist |
| Adds only `@EnableWebFluxSecurity` in Boot WebFlux | Requests loading reactive security infrastructure | This is a Servlet chain or URLs have specific roles |
| Declares `SecurityFilterChain` | Boot backs off **default web security policy** in Servlet | Boot also turns off the default `UserDetailsService` |
| Declares `UserDetailsService`, `AuthenticationProvider`, or `AuthenticationManager` | Can prevent Servlet's **default user** from being created | Default web chain is definitely disabled |
| Declares `SecurityWebFilterChain` | Customizes WebFlux rules/filters | Reactive default user definitely disappears |
| Declares `ReactiveUserDetailsService` or `ReactiveAuthenticationManager` | Can prevent the reactive generated user from being created | WebFlux HTTP chain was modified |
| Adds OAuth2 Client / Resource Server / SAML dependency | Can change default user/identity conditions | Issuer, audience, and token validation can be skipped |
| Adds `@EnableMethodSecurity`/`@EnableReactiveMethodSecurity` | Enables the corresponding method authorization infrastructure | All service methods are blocked by default |

**Technical details in Spring Boot 3.5:**

- Servlet: Boot docs state explicitly that **declaring a `SecurityFilterChain` bean** replaces the default web security configuration, **without automatically disabling** `UserDetailsService`. The default user store has its own conditions; `UserDetailsService`, `AuthenticationProvider`, `AuthenticationManager` beans, or certain security modules on the classpath can cause it to back off.
- WebFlux: Boot uses `ReactiveSecurityAutoConfiguration` for web security and `ReactiveUserDetailsServiceAutoConfiguration` for the user store. The docs describe disabling default web security configuration entirely with a `WebFilterChainProxy` bean vs. **customizing access rules with `SecurityWebFilterChain`**. Those are two distinct bean types; do not mechanically assume a custom `SecurityWebFilterChain` removes all reactive infrastructure.
- For both: condition evaluation order in auto-config and existing beans determine which beans are created. Use logs, `ConditionEvaluationReport`, and real tests to verify rather than guessing from one annotation.

An important illustration:

```text
Case A: Custom chain, no custom UserDetailsService
   -> Web policy changes
   -> Generated user may still appear

Case B: Custom UserDetailsService, no custom chain
   -> User source changes
   -> Default web policy may still require authentication

Case C: Custom both chain and user store
   -> Explicitly defines both HTTP rules and authentication
```

This illustrates separation of concerns, not an absolute promise across every classpath combination.

## 7. Choose the Right Web Stack Before Choosing Annotations

### 7.1. Comparing Servlet and WebFlux

| Comparison point | Servlet/MVC | WebFlux/reactive |
| --- | --- | --- |
| Primary web starter | `spring-boot-starter-web` | `spring-boot-starter-webflux` |
| Manual security annotation | `@EnableWebSecurity` | `@EnableWebFluxSecurity` |
| Builder | `HttpSecurity` | `ServerHttpSecurity` |
| Rule/filter chain bean | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Web request dispatch proxy | `FilterChainProxy` + Servlet filter integration | `WebFilterChainProxy` |
| Request rules | `authorizeHttpRequests` | `authorizeExchange` |
| Endpoint matching | `requestMatchers(...)` | `pathMatchers(...)` |
| Default user store | `UserDetailsService` / `InMemoryUserDetailsManager` | `ReactiveUserDetailsService` / `MapReactiveUserDetailsService` |
| Context | Typically `SecurityContextHolder` and Servlet thread | `ReactiveSecurityContextHolder` and Reactor Context |
| HTTP testing | `MockMvc` | `WebTestClient` |
| Dedicated method security | `@EnableMethodSecurity` | `@EnableReactiveMethodSecurity` |

When both `spring-boot-starter-web` and `spring-boot-starter-webflux` are present, Spring Boot **defaults to Spring MVC** rather than WebFlux; many MVC apps add the WebFlux starter solely to use `WebClient`. If you truly want reactive mode when both are on the classpath, set `WebApplicationType.REACTIVE` explicitly and ensure auto-configs remain compatible. Learning security configuration is easier using **two independent projects** without mixing both starters.

### 7.2. Easily Confused Name Pairs

- `@EnableWebSecurity` != `@EnableWebMvc`. One enables Servlet Spring Security; the other controls Spring Framework's web MVC infrastructure.
- `@EnableWebFluxSecurity` != `@EnableWebFlux`. One enables reactive Spring Security; the other controls base WebFlux configuration.
- `@EnableWebSecurity` != `@EnableMethodSecurity`. Protecting the HTTP boundary differs from intercepting service calls via annotations.
- `SecurityFilterChain` != `SecurityWebFilterChain`. Two filter pipeline interfaces for two web models.
- Servlet ThreadLocal `SecurityContextHolder` != Reactor Context-based `ReactiveSecurityContextHolder`.
- `spring-boot-starter-security` does **not** mean an application already has an OAuth2 Authorization Server, JWT issuer, or production identity system.

## 8. Demo A: Spring Boot MVC with Explicit @EnableWebSecurity

We build an app using HTTP Basic to test authentication and rules. The annotation's purpose here is to clarify Spring Security's Servlet infrastructure. **When keeping the custom chain and running on Boot with default auto-configuration, the demo does not strictly require this annotation; Boot already provides the integration.** Never treat the annotation as an endpoint permission declaration.

The example pins **Spring Boot 3.5.16** for consistent Java 17 source and tests. That is the final OSS release of the 3.5.x line, released June 25, 2026; new production deployments should use a supported Boot line with active patches.

### 8.1. Directory Layout

```text
servlet-enable-demo/
├── pom.xml
└── src/
    ├── main/java/demo/servlet/ServletSecurityApplication.java
    └── test/java/demo/servlet/ServletSecurityTests.java
```

### 8.2. Maven POM

```xml
<!-- pom.xml -->
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
    <artifactId>servlet-enable-demo</artifactId>
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

### 8.3. Complete Java Code

Create `src/main/java/demo/servlet/ServletSecurityApplication.java`:

```java
package demo.servlet;

import jakarta.servlet.DispatcherType;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
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
public class ServletSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(ServletSecurityApplication.class, args);
    }
}

@Configuration(proxyBeanMethods = false)
@EnableWebSecurity
class ServletSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/me").authenticated()
                .requestMatchers(HttpMethod.GET, "/admin")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.POST, "/notes")
                    .hasAuthority("NOTES_WRITE")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .csrf(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("demo-pass"))
                .authorities("ROLE_USER", "NOTES_WRITE")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("demo-pass"))
                .roles("ADMIN")
                .build()
        );
    }
}

@RestController
class ServletRoutes {
    @GetMapping("/public")
    String publicMessage() {
        return "public";
    }

    @GetMapping("/me")
    String me(Authentication authentication) {
        return "me:" + authentication.getName();
    }

    @GetMapping("/admin")
    String admin() {
        return "admin";
    }

    @PostMapping("/notes")
    String createNote(Authentication authentication) {
        // Demo: writes no real data, only illustrates permission + CSRF.
        return "created:" + authentication.getName();
    }
}
```

**Explaining the boundaries:**

1. `@EnableWebSecurity` activates Servlet web security infrastructure; Spring Boot also has matching auto-configuration. The annotation **does not declare `/admin` as an admin endpoint**.
2. `SecurityFilterChain` is the bean holding current filters/rules. `authorizeHttpRequests` declares the request policy; `anyRequest().denyAll()` blocks unlisted paths in **this chain**.
3. `UserDetailsService` defines the user source and authorities. Because this bean exists, Boot does not need to generate user `user`; password `demo-pass` is local test data.
4. `httpBasic` is the authentication mechanism. It **does not encrypt** passwords by itself: HTTPS is required when transmitting credentials over real networks.
5. `csrf` remains enabled; a POST lacking a valid token receives `403` even when Alice holds `NOTES_WRITE`.
6. `DispatcherType.ERROR` allows the container to render an appropriate error page on error dispatches; it does not make an initial request to an undeclared URL public.
7. `@EnableMethodSecurity` is absent because the demo focuses on the HTTP boundary; to protect services with `@PreAuthorize`, add policies and enable method security separately.

### 8.4. Integration Test with MockMvc

Create `src/test/java/demo/servlet/ServletSecurityTests.java`:

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
class ServletSecurityTests {

    @Autowired
    MockMvc mvc;

    @Test
    void requestPolicyAndCsrfAreApplied() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));

        mvc.perform(get("/me"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/me").with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("me:alice"));

        mvc.perform(get("/me").with(httpBasic("alice", "wrong")))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/admin").with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/admin").with(httpBasic("admin", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin"));

        // Has NOTES_WRITE permission, but POST lacks CSRF token.
        mvc.perform(post("/notes").with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isForbidden());

        // Has CSRF + NOTES_WRITE permission, controller is invoked.
        mvc.perform(post("/notes")
                .with(httpBasic("alice", "demo-pass"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("created:alice"));

        // Admin has ROLE_ADMIN but lacks NOTES_WRITE.
        mvc.perform(post("/notes")
                .with(httpBasic("admin", "demo-pass"))
                .with(csrf()))
            .andExpect(status().isForbidden());

        // A new unlisted path is denied.
        mvc.perform(get("/unknown")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isForbidden());
    }
}
```

The test uses a real HTTP Basic header via `httpBasic(...)`, letting the security framework authenticate against the test context's `UserDetailsService`; `csrf()` generates a valid token via MockMvc. No open server socket is needed to verify these rules. If a test uses only `@WithMockUser`, passwords are not verified; that is a different kind of authorization test.

### 8.5. Running

From `servlet-enable-demo` with JDK 17+ and Maven:

```bash
mvn test
mvn spring-boot:run
```

Once the server is running:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/me
curl -i -u alice http://localhost:8080/me
curl -i -u alice http://localhost:8080/admin
curl -i -u admin http://localhost:8080/admin
```

Curl prompts interactively for the password with `-u alice`/`-u admin`; enter `demo-pass` **on the lab machine only**. Expected results in order are typically `200 public`, `401`, `200 me:alice`, `403`, `200 admin`. To test a successful POST with CSRF enabled, a valid token for the session/request is needed; this lesson uses `MockMvc.csrf()` to test that condition. Do not disable CSRF just because a curl POST returned 403.

**A conceptual experiment:** With the same Boot app and chain/user beans above, removing `@EnableWebSecurity` while keeping `SecurityFilterChain` may still run identically thanks to Boot's web security auto-configuration; this is why you should never treat the annotation as a way to assign permissions. Verify with tests in your active Boot/version environment during practice.

## 9. Demo B: Spring Boot WebFlux with @EnableWebFluxSecurity

This is an **independent project**, using only `spring-boot-starter-webflux` without mixing in the MVC starter. Spring Boot 3.5.16, Java 17. WebFlux uses `WebFilterChainProxy` and `SecurityWebFilterChain`, not Servlet `SecurityFilterChain`.

### 9.1. Structure

```text
webflux-enable-demo/
├── pom.xml
└── src/
    ├── main/java/demo/reactive/ReactiveSecurityApplication.java
    └── test/java/demo/reactive/ReactiveSecurityTests.java
```

### 9.2. Maven POM

```xml
<!-- pom.xml -->
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>webflux-enable-demo</artifactId>
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

### 9.3. Complete WebFlux Java Code

Create `src/main/java/demo/reactive/ReactiveSecurityApplication.java`:

```java
package demo.reactive;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class ReactiveSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveSecurityApplication.class, args);
    }
}

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/public").permitAll()
                .pathMatchers(HttpMethod.GET, "/me").authenticated()
                .pathMatchers(HttpMethod.GET, "/admin")
                    .hasRole("ADMIN")
                .pathMatchers(HttpMethod.POST, "/notes")
                    .hasAuthority("NOTES_WRITE")
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .csrf(Customizer.withDefaults())
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
                .authorities("ROLE_USER", "NOTES_WRITE")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("demo-pass"))
                .roles("ADMIN")
                .build()
        );
    }
}

@RestController
class ReactiveRoutes {

    @GetMapping("/public")
    Mono<String> publicMessage() {
        return Mono.just("public");
    }

    @GetMapping("/me")
    Mono<String> me() {
        return Mono.just("authenticated");
    }

    @GetMapping("/admin")
    Mono<String> admin() {
        return Mono.just("admin");
    }

    @PostMapping("/notes")
    Mono<String> createNote() {
        return Mono.just("created");
    }
}
```

In this demo, `@EnableWebFluxSecurity` requests Spring Security's reactive web infrastructure, `SecurityWebFilterChain` defines HTTP permissions, and `MapReactiveUserDetailsService` defines the custom user store. A reactive user store bean replaces the default user store when Boot's auto-configuration condition backs off. **Do not use Servlet's `InMemoryUserDetailsManager`** in its place in this configuration.

Even though controllers return `Mono`, Spring Security does not automatically protect entities in the database. If `GET /me` later serves sensitive data, services must verify the right principal/owner/tenant and pass context via reactive APIs. Do not force `Mono.block()` on the event loop to read the user.

### 9.4. Testing with WebTestClient

Create `src/test/java/demo/reactive/ReactiveSecurityTests.java`:

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
class ReactiveSecurityTests {

    @Autowired
    ApplicationContext applicationContext;

    WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient.bindToApplicationContext(applicationContext)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void webFilterChainEnforcesRulesAndCsrf() {
        client.get().uri("/public").exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public");

        client.get().uri("/me").exchange()
            .expectStatus().isUnauthorized();

        client.get().uri("/me")
            .headers(h -> h.setBasicAuth("alice", "demo-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("authenticated");

        client.get().uri("/me")
            .headers(h -> h.setBasicAuth("alice", "wrong"))
            .exchange()
            .expectStatus().isUnauthorized();

        client.get().uri("/admin")
            .headers(h -> h.setBasicAuth("alice", "demo-pass"))
            .exchange()
            .expectStatus().isForbidden();

        client.get().uri("/admin")
            .headers(h -> h.setBasicAuth("admin", "demo-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("admin");

        // Alice has NOTES_WRITE, but lacks CSRF.
        client.post().uri("/notes")
            .headers(h -> h.setBasicAuth("alice", "demo-pass"))
            .exchange()
            .expectStatus().isForbidden();

        // Alice has permission and valid test CSRF token.
        client.mutateWith(csrf()).post().uri("/notes")
            .headers(h -> h.setBasicAuth("alice", "demo-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("created");

        // Admin lacks NOTES_WRITE, even with CSRF.
        client.mutateWith(csrf()).post().uri("/notes")
            .headers(h -> h.setBasicAuth("admin", "demo-pass"))
            .exchange()
            .expectStatus().isForbidden();

        client.get().uri("/unknown")
            .headers(h -> h.setBasicAuth("alice", "demo-pass"))
            .exchange()
            .expectStatus().isForbidden();
    }
}
```

`WebTestClient.bindToApplicationContext(...)` combines with `springSecurity()` to run through WebFlux + Spring Security test support. `setBasicAuth` sends HTTP Basic credentials for reactive authentication; `mutateWith(csrf())` adds a valid token via Spring Security Test infrastructure. No real server port is needed for this test.

### 9.5. Run Commands and Behavior

In `webflux-enable-demo`:

```bash
mvn test
mvn spring-boot:run
```

In another terminal:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/me
curl -i -u alice http://localhost:8080/me
curl -i -u alice http://localhost:8080/admin
curl -i -u admin http://localhost:8080/admin
```

Expected: `200 public`, `401`, `200 authenticated`, `403`, and `200 admin`. With `-u`, enter `demo-pass` only when curl prompts; avoid leaving passwords in command history. HTTP does not encrypt passwords; these `localhost` commands are for the lab only. Production must run HTTPS/TLS.

**Comparing with Servlet:** Status expectations match because **the HTTP business rules are written equivalently**, yet Spring Security executes them with **different** filters and contexts. Never conclude that the two stacks share filter classes or method-security annotations.

## 10. A "Baseline -> Custom" Experiment to See Boot Auto-Configuration Clearly

To avoid confusing an annotation's effect with a chain bean's effect, try these stages in order.

### Stage A — Starter Only

1. Use Spring Boot MVC or WebFlux independently.
2. Include the Spring Security starter, **without declaring any chain/user store yet**.
3. Run and inspect the generated security password log if a default user is created; default username is typically `user`.
4. Try `GET /public` without credentials. By default it usually demands authentication even though the endpoint is named public.
5. Try `GET /public` with the right Basic user: allowed in. With a browser accepting HTML, it may redirect to the login page.

**Observation:** Spring Boot enabled web security defaults without any custom security configuration Java code.

### Stage B — Add Only the Annotation

1. Add a `@Configuration @EnableWebSecurity` class for MVC, or `@Configuration @EnableWebFluxSecurity` for WebFlux.
2. Do not define any chain bean or user provider yet.
3. Observe and test default behavior. In a Boot app on the right stack, the annotation usually does not alter actual authorization policies if infrastructure was already enabled by Boot.
4. Do not use "no more generated password" as a guaranteed assumption; default user creation is a separate auto-configuration.

**Observation:** The annotation represents activating infrastructure. It cannot substitute for the contents of `authorizeHttpRequests`/`authorizeExchange`.

### Stage C — Add the Chain Bean

1. Create `SecurityFilterChain`/`SecurityWebFilterChain`.
2. Explicitly allow `GET /public` and require authentication for `GET /me`; add `ROLE_ADMIN` for `GET /admin`.
3. Re-run tests: anonymous `GET /public` flips from blocked to `200`; `/me` still requires login; users lacking the admin role receive `403`.
4. Without declaring a user store, the default user may still appear per Boot conditions.

**Observation:** The **chain bean** changes HTTP policy; it **neither creates nor removes** user identities by itself.

### Stage D — Add a Custom User/Provider

1. Create `UserDetailsService` or `MapReactiveUserDetailsService` as in the demos.
2. Use `alice`/`admin` with hashed passwords and defined authorities.
3. Test valid/wrong passwords and right/wrong roles.
4. Check the generated user log: it may disappear because the default user configuration backed off.

**Observation:** The **authentication source** is customized independently of **authorization rules**. Production apps must deploy a real identity provider and account lifecycle policies.

### Stage E — Enable Method Security When Needed

1. If services use `@PreAuthorize`, add `@EnableMethodSecurity` for imperative/Servlet; reactive services need `@EnableReactiveMethodSecurity` aligned with Reactor.
2. Write tests calling methods through the real proxy/bean, not calling `this.method()` internally and assuming the interceptor ran.
3. Test a user permitted to call the URL yet **lacking permission on the object** to verify owner/tenant policies in the service/repository.

**Observation:** Request authorization at the web boundary is one layer. Method and domain authorization are another layer.

## 11. Behavior Matrix to Confirm

| Scenario | Servlet + app-defined chain | WebFlux + app-defined chain |
| --- | --- | --- |
| Anonymous calls `GET /public` | `200` | `200` |
| Anonymous calls `GET /me` | `401` when using HTTP Basic | `401` when using HTTP Basic |
| Alice with right password calls `GET /me` | `200`, `me:alice` | `200`, `authenticated` |
| Alice sends wrong password | `401` | `401` |
| Alice calls admin | `403` due to missing role | `403` due to missing role |
| Admin calls admin | `200` | `200` |
| Alice POSTs notes without CSRF | `403` | `403` |
| Alice POSTs notes with CSRF | `200` | `200` |
| Admin POSTs notes with CSRF, lacking NOTES_WRITE | `403` | `403` |
| Alice calls an unlisted URL | `403` with `denyAll` | `403` with `denyAll` |

This is the contract **of the demos above**, not a claim that all Spring Security apps always return these exact codes. With form login, browsers may be redirected; with a JWT Resource Server, entry points and claims/authorities behave differently. When a reverse proxy rewrites responses, error routes, or custom CORS/CSRF are configured, test against your actual deployment.

## 12. Common Mistakes

### 12.1. "There Is No @EnableWebSecurity, So Boot Does Not Protect URLs"

**False:** Servlet Spring Boot normally auto-configures Spring Security when the starter is present. Endpoints can require login even when source code has no annotation.

**Fix:** check dependencies, whether a `SecurityFilterChain` bean exists, startup logs, unauthenticated request responses, and the auto-configuration condition report.

### 12.2. "Having @EnableWebSecurity Means Admin Rules Already Exist"

**False:** The annotation enables infrastructure; it does not know `/admin` is special. Business-role protection requires `authorizeHttpRequests` and data-level permissions in services.

**Fix:** declare `requestMatchers(HttpMethod.GET, "/admin").hasRole("ADMIN")` and test both non-admin and admin.

### 12.3. "Creating a UserDetailsService Disables Default Web Security"

**False:** Replacing the user store is a separate auto-configuration condition branch from replacing the chain.

**Fix:** separate authentication and URL authorization tests. Never assume swapping the user store alone makes `/public` public.

### 12.4. "Creating a SecurityFilterChain Guarantees the Default User Disappears"

**False:** Boot Servlet docs explicitly note that a custom chain **does not automatically disable** the default `UserDetailsService`.

**Fix:** if you want custom identities, supply an appropriate `UserDetailsService`, provider, or manager and verify that the generated user backed off.

### 12.5. "WebFlux Uses HttpSecurity Because It Is Also a Web App"

**False:** WebFlux uses reactive `ServerHttpSecurity`/`SecurityWebFilterChain` and `@EnableWebFluxSecurity`. Using the Servlet API causes config not to apply to the reactive pipeline.

**Fix:** use the right starter/framework; test WebFlux with `WebTestClient` and verify bean/runtime types.

### 12.6. "Both Starters Are Present, So Boot Automatically Picks WebFlux"

**False:** When both `spring-boot-starter-web` and `spring-boot-starter-webflux` are on the classpath, Boot defaults to Spring MVC; the WebFlux starter may have been added solely for `WebClient`.

**Fix:** use one web starter for demos; for products with special needs, set `WebApplicationType` explicitly and inspect Spring Boot's condition report.

### 12.7. "Using @EnableWebFlux Instead of @EnableWebFluxSecurity"

**False:** `@EnableWebFlux` controls Spring WebFlux configuration, not reactive Spring Security.

**Fix:** distinguish Spring Framework web annotations from Spring Security annotations; never swap them carelessly because of similar names.

### 12.8. "Adding the Annotation Already Enabled @PreAuthorize"

**False:** Method security is not enabled automatically when web security is enabled.

**Fix:** use `@EnableMethodSecurity` / `@EnableReactiveMethodSecurity` per model and test method interception.

### 12.9. "Disabling CSRF Fixes All 403 POST Errors"

**False:** In browsers with auto-attached cookies/sessions/Basic credentials, CSRF is an independent risk from authentication/roles. Disabling it arbitrarily can introduce vulnerabilities.

**Fix:** test with valid tokens and design CSRF around credentials and the threat model. An API strictly using client-added Bearer headers needs separate evaluation rather than copying lab settings blindly.

### 12.10. "SecurityFilterChain Matches Only /api/**, Yet anyRequest Blocks the Whole App"

**False:** `anyRequest` affects only requests **already selected by that chain**. Outside `/api/**`, there may be no chain at all, leaving URLs unprotected by Spring Security.

**Fix:** add a catch-all fallback chain or use a single chain with multiple `requestMatchers`, and test URLs outside the API. This is a chain coverage bug, not an annotation bug.

### 12.11. "Putting Roles in Tokens/Users Is Enough to Protect Every Object"

**False:** Roles grant functional access; services still must verify owner, tenant, state, limits, and ACLs. Web security filters do not understand business data automatically.

**Fix:** enforce policies by actor + action + resource + context, test swapping IDs and tenants, and rely on trustworthy server-side data.

### 12.12. "Added @EnableWebSecurity, So Checking Bean Existence Is Enough"

**False:** A bean existing does not prove CSRF, URL matching, login flows, sessions, and exception handling work properly.

**Fix:** maintain integration tests for anonymous, wrong password, insufficient authority, CSRF, valid users, and fallback requests; run realistic network tests when verifying HTTPS/reverse proxies.

## 13. Debugging Auto-Configuration and Chains in Real Projects

### 13.1. What to Inspect First

1. **Classpath:** which web starter is present? Are both web + webflux present? Does an OAuth2 client/resource server/SAML starter change user store conditions?
2. **WebApplicationType:** is the app actually Servlet or Reactive?
3. **Created beans:** which `SecurityFilterChain`/`SecurityWebFilterChain`, `UserDetailsService`/`ReactiveUserDetailsService`, authentication manager/provider/decoder exist?
4. **Annotations:** are `@EnableWebSecurity` or `@EnableWebFluxSecurity` present? In Spring Boot, were they auto-enabled via configuration?
5. **Conditions:** which auto-configuration classes applied or backed off, and because of which bean/classpath entry?
6. **Filter chain coverage:** which URLs do chains match, in what order, and do any URLs match no chain?
7. **Authorization rules:** are anonymous, authenticated, role/authority, HTTP method, CSRF, and CORS aligned with intent?
8. **Identity source:** does the generated user still exist, or was it replaced by a real service/provider/IdP?
9. **Transport:** do real requests enforce HTTPS, cookie flags, and proper proxy/header trust?

### 13.2. Local Logging

You can enable Spring Security logging:

```properties
logging.level.org.springframework.security=DEBUG
```

And pass Spring Boot's `--debug` flag at startup to view the **condition evaluation report** (contents vary by version):

```bash
mvn spring-boot:run -Dspring-boot.run.arguments=--debug
```

Not every log line alone lets you conclude "the annotation applied" without reading the context/classpath accurately. Inspect bean definitions, auto-configuration conditions, and HTTP behavior together. Avoid enabling TRACE or logging credentials/tokens in production.

If Actuator is enabled for operations, the `conditions` and `beans` endpoints can aid diagnosis, yet **must never be exposed publicly**; Actuator access must be protected per infrastructure policy.

### 13.3. Distinguishing 401, 403, and 302

- `401 Unauthorized`: authentication required or credentials rejected; HTTP Basic typically sends `WWW-Authenticate`.
- `403 Forbidden`: authentication may be valid but lacks permission; or POST was blocked by CSRF (the CSRF filter can block before authentication completes).
- `302 Found`: usually a browser redirect to form login, depending on the entry point.
- `404`/`405`: may come from MVC/WebFlux routing after passing the filter chain; do not confuse with a security decision.
- `200`: handler succeeded, **does not prove a URL is public** if the request carried cookies/tokens.

In every case, inspect **request method + path + headers + credentials + chain/rule + result** before editing security configuration. Avoid turning off filters merely to change a status code.

## 14. Self-Assessment Questions

**Question 1.** A Boot MVC app has `spring-boot-starter-security` without `@EnableWebSecurity`. Can it require login for all URLs?

**Answer:** Yes. Boot auto-configures default web security when conditions hold. The annotation is not the sole requirement for Boot to enable security.

**Question 2.** You create a `SecurityFilterChain` making `/health` public, yet still see a random password in logs. Is Boot broken?

**Answer:** No. Replacing the default web chain does not replace `UserDetailsService`. Without another user/provider or an excluding classpath condition, Boot may still create the generated user.

**Question 3.** You define a custom `UserDetailsService`, yet anonymous requests to `/private` still require login. Does that make sense?

**Answer:** Yes. The user store governs identity sources; the default web policy can still demand authentication. The two auto-configurations are conceptually independent.

**Question 4.** Both `spring-boot-starter-webflux` and `spring-boot-starter-web` are present; the code uses `@EnableWebFluxSecurity`, yet MVC requests ignore the reactive rules. Why?

**Answer:** Boot defaults to MVC when both starters exist. WebFlux rules are not a Servlet `SecurityFilterChain`. Verify the web application type and configure the matching stack.

**Question 5.** In WebFlux, you add only `@EnableWebFluxSecurity`. Do all URLs become `permitAll`?

**Answer:** No. Enabling infrastructure does not open access. Default security usually requires authentication; opening a URL requires a `SecurityWebFilterChain` with appropriate `authorizeExchange(...).pathMatchers(...).permitAll()`.

**Question 6.** To use `@PreAuthorize` in a Servlet service, is `@EnableWebSecurity` alone enough?

**Answer:** Not enough. You need `@EnableMethodSecurity` and matching method security setup; calls must pass through the interceptor/proxy for the annotation to apply.

**Question 7.** Can `@EnableWebMvc` replace `@EnableWebSecurity`?

**Answer:** No. One enables the MVC web framework; the other enables Servlet Spring Security. They serve different purposes.

**Question 8.** Why do the two demos return the same 200/401/403 codes while using two different test suites?

**Answer:** The HTTP policies are written equivalently, but the execution models differ: Servlet filters and `MockMvc` on one side, reactive WebFilters and `WebTestClient` on the other.

## 15. Pre-Release Checklist

- [ ] Clearly chose **Servlet** or **Reactive**, with starter and WebApplicationType verified?
- [ ] Understand the differences among enable annotations, auto-configuration, filter chain beans, and user/provider beans?
- [ ] No generated user/password used as a production identity?
- [ ] Chain bean defines URLs/methods/roles/authorities accurately, with appropriate `denyAll`/fallback?
- [ ] Integration tests cover anonymous, wrong role, wrong password, CSRF, and valid requests?
- [ ] Verified no URL slips outside all chains when using multiple chains?
- [ ] Login/logout/error/health/actuator endpoints fall within required filter scopes?
- [ ] Method security enabled separately if the project uses `@PreAuthorize`?
- [ ] WebFlux does not rely on ThreadLocal/Servlet filters as defaults for reactive pipelines?
- [ ] OAuth2/JWT has issuer/audience/key validation and trusted authority mapping?
- [ ] Resource/owner/tenant permissions still enforced in services/repositories?
- [ ] Production has HTTPS, secret management, safe logging, patched dependencies, and proper session/token policies?

## 16. Key Takeaways

1. **`@EnableWebSecurity` = Servlet Spring Security infrastructure. `@EnableWebFluxSecurity` = Reactive Spring Security infrastructure.**
2. **Spring Boot provides auto-configuration**: just adding the starter can enable default security and generate a development user/password; you do not always have to add annotations manually.
3. **`SecurityFilterChain`/`SecurityWebFilterChain` beans decide concrete web policies**. Annotations do not know which URLs need which roles or permissions.
4. **User sources and web chains are separate responsibilities**. A custom chain does not mean the default user disappeared, and a custom user does not mean URLs became public.
5. **Pick the right web stack, test with the right tool**: Servlet uses `HttpSecurity`/`MockMvc`, reactive uses `ServerHttpSecurity`/`WebTestClient`.
6. **Web security is the outer boundary**. Add method/domain policies, negative tests, and HTTPS when applications handle real data.

## Official References

- [Spring Boot 3.5 — Spring Security Auto-Configuration](https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html)
- [Spring Security 6.5 — Servlet Java Configuration, @EnableWebSecurity](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html)
- [Spring Security 6.5 — WebFlux Security, @EnableWebFluxSecurity](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html)
- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html)
- [Spring Security 6.5 — Reactive Test WebTestClient Setup](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/setup.html)
- [Spring Security 6.5 — WebFlux CSRF Testing](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/csrf.html)
- [Spring Security 6.5 — Servlet MockMvc Setup](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html)
- [Spring Security 6.5 — Servlet MockMvc CSRF Test](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/csrf.html)
- [Spring Boot — Reactive Web Applications and MVC/WebFlux Starter Selection](https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html)
- [Spring Boot 3.5.16 Release, 25/06/2026](https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/)
