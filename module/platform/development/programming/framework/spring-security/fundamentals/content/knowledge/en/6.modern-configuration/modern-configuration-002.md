# HttpSecurity and Building SecurityFilterChain in Servlet Applications

When you start configuring Spring Security in Java, you will commonly see a method like this:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/public/**").permitAll()
            .anyRequest().authenticated()
    );
    return http.build();
}
~~~

The middle three lines describe the **desired security policy**. Calling `http.build()` creates **a complete `SecurityFilterChain`** for Spring Security to use when handling HTTP requests. At that moment, no specific request is being logged in or authorized; you are building the configuration that will serve future requests.

Understanding this relationship explains why declaring a `SecurityFilterChain` takes effect, why multiple filters run in a specific order, and why a URL can sometimes go unprotected even though the source code has `anyRequest().authenticated()`.

This lesson focuses on **Servlet/Spring MVC**, with examples using Java 17+, Spring Boot 3.5.16, and Spring Security managed by Boot. This is an illustrative version with corresponding 6.5 documentation; the Boot 3.5 branch reached the end of OSS support in June 2026, so when initializing a new production system you should choose a currently supported Boot branch and verify the API against that version. The concepts of `HttpSecurity`, `SecurityFilterChain`, and `FilterChainProxy` remain foundational in modern Servlet configuration.

## 1. Accurately Distinguishing Three Easily Confused Objects

| Object | Role | When does it exist? |
| --- | --- | --- |
| `HttpSecurity` | **Builder**, accepts the DSL and `SecurityConfigurer`s to construct the filter set | Primarily during configuration bean creation at application startup |
| `SecurityFilterChain` | **Product of the builder**, containing a `RequestMatcher` and an ordered/configured list of filters | After `http.build()` succeeds; retained to handle requests |
| `FilterChainProxy` | **Dispatching filter**, selects which `SecurityFilterChain` matches each request | When the Servlet container receives a request and passes it into Spring Security |

`HttpSecurity` belongs to the `org.springframework.security.config.annotation.web.builders` package. `SecurityFilterChain` belongs to `org.springframework.security.web`. A common implementation of the built result is `DefaultSecurityFilterChain`. These types are **not different names for the same object**.

You can visualize it as:

~~~text
HttpSecurity                    -- builder / blueprint
   |
   +-- authorizeHttpRequests    -- access rules
   +-- httpBasic or formLogin   -- how authentication credentials are received
   +-- csrf / headers / cors    -- related protection layers
   +-- sessionManagement        -- session options
   +-- securityMatcher          -- scope of the chain
   |
   v
http.build()                    -- finalize configuration
   |
   v
DefaultSecurityFilterChain      -- matcher + ordered filters
   |
   v
FilterChainProxy                -- holds the list of chains
   |
   v
Incoming requests later         -- select and execute the matching chain
~~~

`SecurityFilterChain` is **not** an object whose `build()` method creates controllers, and by itself it does **not** perform password verification at build time. It tells `FilterChainProxy` when to run and which servlet filters to execute.

## 2. What Does HttpSecurity Do Before build()?

`HttpSecurity` implements Spring Security's configuration builder pattern. In Java configuration, fluent API calls such as `authorizeHttpRequests`, `httpBasic`, or `csrf` supply parameters to *configurers*. Each configurer adds the appropriate components when the builder is finalized.

Example:

~~~java
http
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/public/**").permitAll()
        .requestMatchers("/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated())
    .httpBasic(Customizer.withDefaults())
    .csrf(Customizer.withDefaults());

return http.build();
~~~

Effects to distinguish:

- `authorizeHttpRequests`: sets up **request authorization rules**. With this configuration, an `AuthorizationFilter` collaborates with an `AuthorizationManager` to evaluate the rules.
- `httpBasic`: enables reading HTTP Basic credentials appropriately and handling authentication challenges; a `BasicAuthenticationFilter` may appear in the chain.
- `csrf`: configures Cross-Site Request Forgery protection. In Servlet web applications, CSRF is enabled by default and typically checks unsafe HTTP methods.
- `headers`: rules for adding security response headers; several values have defaults.
- `sessionManagement`: how the application manages sessions, session creation policies, and related behaviors.
- `exceptionHandling`: how to respond when authentication is required or access is denied, such as `AuthenticationEntryPoint` and `AccessDeniedHandler`.
- `formLogin`: configures form-based login within an appropriately stateful security chain.
- `oauth2ResourceServer`: when appropriate dependencies/configuration are added, sets up bearer token authentication for a resource server.
- `securityMatcher`: restricts which requests **this entire chain** applies to.

Do not assume **each DSL call always produces exactly one filter**. One configurer can create multiple objects, share components, or alter the order/relationships among filters. Specific filter names depend on the version and enabled features.

### Why Use Customizer and Lambdas?

In the modern Java DSL, lambdas group related options by topic:

~~~java
http.authorizeHttpRequests(authorize -> authorize
        .requestMatchers("/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated()
);
~~~

The `authorize` variable is a configuration object supplied by the framework; you do not instantiate it yourself. `Customizer.withDefaults()` means **enable/configure the component with the configurer's defaults**, not permit all requests. Specifically, `httpBasic(Customizer.withDefaults())` never grants `ROLE_ADMIN` to users by default.

Prefer the lambda DSL of the Spring Security branch you are using; many older tutorials use `WebSecurityConfigurerAdapter` or invocation styles that are no longer suitable.

## 3. What Actually Happens During http.build()?

`HttpSecurity` inherits the `AbstractConfiguredSecurityBuilder` mechanism. When `build()` is invoked, the builder executes the component creation lifecycle described in the API documentation. Conceptually:

1. **Initialization phase:** registered configurers get an `init(...)` pass to prepare configuration and needed shared objects.
2. **Configuration phase:** configurers execute `configure(...)`, adding filters, handlers, and related objects according to the DSL parameters.
3. **Finalizing the object:** `HttpSecurity.performBuild()` creates a `DefaultSecurityFilterChain` with the request matcher and ordered filter list.
4. **Bean registration:** the result from `@Bean SecurityFilterChain` enters the Spring `ApplicationContext`, where the web security infrastructure uses it.

This describes the framework's internal logic, not pseudocode to copy into `@Configuration`:

~~~text
Application starts
      |
Spring invokes @Bean securityFilterChain(HttpSecurity http)
      |
      +--> DSL attaches configurers and rules
      |
      +--> http.build()
                 |
                 +--> init configurers
                 +--> configure configurers
                 +--> order filters according to Spring Security ordering
                 +--> create DefaultSecurityFilterChain
      |
      v
SecurityFilterChain bean is registered in the context
      |
FilterChainProxy has the chains ready
      |
[Later] HTTP request arrives
      |
FilterChainProxy selects matching chain and runs filters
~~~

**Building is configuration creation work, not per-request handling.** Spring typically calls the bean factory method during `ApplicationContext` initialization; `http.build()` is not called on every incoming request. Because `AbstractSecurityBuilder` guards against building more than once, do not call `build()` repeatedly on the **same builder** or reuse a finalized `HttpSecurity` to keep adding rules.

`http.build()` typically returns a `DefaultSecurityFilterChain`, but the bean's public return signature should use the `SecurityFilterChain` interface so application code depends less on the implementation.

### Why Not Call new HttpSecurity Yourself?

In Spring Boot/Spring Security, the container supplies an `HttpSecurity` already prepared with shared objects, configurers, and integration with the bean ecosystem. Therefore, the standard approach is to receive it as a `@Bean` method parameter:

~~~java
@Bean
SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth.anyRequest().authenticated())
        .build();
}
~~~

Calling `new HttpSecurity(...)` manually outside Spring Security's mechanism easily misses dependencies/shared objects and is not the right choice for normal applications. You also do not need to manually instantiate `FilterChainProxy` or register individual security filters by hand in a standard Boot project.

## 4. Who Runs the Built Filters When a Request Arrives?

In a Servlet environment, an HTTP request passes through the servlet container's filter chain before reaching `DispatcherServlet`. Spring Security plugs into this mechanism as follows:

~~~text
Browser / HTTP client
         |
         v
Servlet container's FilterChain
         |
         v
DelegatingFilterProxy (bridge to Spring Bean)
         |
         v
FilterChainProxy (typically the springSecurityFilterChain bean)
         |
         +--> select first SecurityFilterChain matching the request
                        |
                        v
             Security filters in the chain
                        |
                        +--> load/establish SecurityContext as needed
                        +--> CSRF/headers protection and other mechanisms
                        +--> process authentication (if configured)
                        +--> evaluate authorization
                        |
                        v
                DispatcherServlet
                        |
                        v
                     Controller
~~~

Two names containing "filter chain" are easily confused:

- **Servlet FilterChain** is the container's mechanism for dispatching filters and servlets across the entire application.
- **SecurityFilterChain** is a *list of security filters + request matcher* managed by Spring Security inside `FilterChainProxy`.

`DelegatingFilterProxy` enables the servlet container to invoke a Spring bean. `FilterChainProxy` is the filter that dispatches across security chains. The `SecurityFilterChain` returned from `http.build()` is a configuration consumed by `FilterChainProxy`; **each `SecurityFilterChain` bean is not registered with the container as an independent servlet filter**.

Spring Boot handles registering the bridge in a standardly configured application; you do not need to declare `web.xml` manually to wire each chain.

### In What Order Do the Filters Run?

Spring Security defines a standard ordering for filters; the framework sorts them when building the chain. With a configuration using CSRF, Basic authentication, and `authorizeHttpRequests`, you may see a relative order such as:

~~~text
... SecurityContext/headers/CSRF ...
            |
 BasicAuthenticationFilter (if HTTP Basic is enabled)
            |
 ... AnonymousAuthenticationFilter ...
            |
 ExceptionTranslationFilter
            |
 AuthorizationFilter
            |
 DispatcherServlet / Controller
~~~

This is a **simplified diagram**, not a complete filter list or a fixed order applicable to every version/configuration. What matters is that authentication and protection steps get to run **before** authorization decisions and controllers.

Do not try to change filter order simply by swapping the order of `httpBasic(...)` and `authorizeHttpRequests(...)` calls in the Java DSL. Filter ordering belongs to Spring Security's internal mechanism, not merely statement order in the file.

## 5. What Does a SecurityFilterChain Contain?

Conceptually, the `SecurityFilterChain` interface answers two questions:

1. **Does this request match the chain?** (request matcher).
2. **If it matches, which `Filter`s should run?** (the chain's filter list).

This can be represented as:

~~~text
SecurityFilterChain A
  matcher = /api/**
  filters = [filters used for HTTP Basic/API...]

SecurityFilterChain B
  matcher = all other requests
  filters = [filters used for form login/web...]

GET /api/orders   -> A
GET /profile      -> B
~~~

`DefaultSecurityFilterChain` is the implementation usually created when `HttpSecurity` builds. You do not need `new DefaultSecurityFilterChain` when using the DSL; the builder creates it.

This is also why `http.build()` does not return `FilterChainProxy`. `FilterChainProxy` manages **one or more** `SecurityFilterChain`s and selects the appropriate chain per request.

## 6. Two Matcher Levels: securityMatcher and requestMatchers

This is one of the most important distinctions in multi-chain configuration.

| Configuration | Application level | Question it answers |
| --- | --- | --- |
| `http.securityMatcher("/api/**")` | **Entire SecurityFilterChain** | Does this chain participate in handling the request? |
| `authorizeHttpRequests(a -> a.requestMatchers("/api/admin/**").hasRole("ADMIN"))` | **Authorization rule inside the selected chain** | What permission does a request in this chain require? |
| `authorizeHttpRequests(a -> a.anyRequest().authenticated())` | Final rule in the **current chain** | What condition applies to remaining requests in the chain? |

Example:

~~~java
@Bean
@Order(1)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public/**").permitAll()
            .requestMatchers("/api/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

With this bean, `GET /api/orders` matches `/api/**`, and then the rule `anyRequest().authenticated()` is evaluated. However, **`GET /profile` does not match `securityMatcher("/api/**")`**, so it never reaches `anyRequest()` of the API chain. If the application only declares this chain and has no other matching chain, `/profile` is **not protected by Spring Security under the existing chains**.

Do not assume `anyRequest()` inside a chain restricted by `securityMatcher` automatically extends across the whole site.

### What Is the Default securityMatcher of a Chain?

When `securityMatcher` is not called, `HttpSecurity`'s matcher usually matches "all requests". With **a single** web chain, that protects all paths according to the declared rules. With **multiple** chains, you must order them so specific chains are checked before the catch-all chain.

Rule order inside `authorizeHttpRequests` also matters: the system applies the **first matching rule**. Placing `anyRequest().permitAll()` before stricter conditions (or in the wrong position) can neutralize the intended policy; declare specific rules before catch-all conditions.

## 7. Complete Java 17+ Example: Building a Chain and Verifying HTTP Behavior

The example uses Spring Boot **3.5.16** as a learning version, with the corresponding Spring Security version managed by Boot. The application has three GET endpoints and one POST endpoint. It builds a `SecurityFilterChain` via `HttpSecurity`, uses HTTP Basic for easy testing with `curl`, and an in-memory user store for local practice.

Verification goals:

- `/public/ping` is accessible without logging in.
- `/private/whoami` is accessible only after authentication.
- `/admin/report` requires the `ADMIN` role, so regular users are denied.
- `POST /private/change` without a CSRF token is blocked even if the client sends HTTP Basic credentials, because the example keeps default CSRF protection.

This is a learning demo; hardcoded accounts and passwords are **not suitable for production**. Real systems need proper providers, password/secret management, HTTPS, and appropriate security controls.

### 7.1. Project Structure

~~~text
security-chain-lab/
  pom.xml
  src/main/java/com/example/securitychain/
    SecurityChainApplication.java
    SecurityConfiguration.java
  src/test/java/com/example/securitychain/
    SecurityRulesTest.java
~~~

### 7.2. Maven POM

Create `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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

    <groupId>com.example</groupId>
    <artifactId>security-chain-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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

Maven only pins the **Spring Boot** version in the parent; Security modules receive compatible versions from the Boot BOM. Java 17 is the Java level for the example. Spring Boot 3.5.16 is used to illustrate stable documented APIs, though because the 3.5 branch has reached end of OSS support, new production projects should check which Boot branch is actively receiving patches before locking in.

### 7.3. Main Class and Endpoints

Create `src/main/java/com/example/securitychain/SecurityChainApplication.java`:

~~~java
package com.example.securitychain;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class SecurityChainApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityChainApplication.class, args);
    }

    @GetMapping("/public/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/private/whoami")
    public String whoami(Authentication authentication) {
        return authentication.getName();
    }

    @GetMapping("/admin/report")
    public String report() {
        return "admin-report";
    }

    @PostMapping("/private/change")
    public String change() {
        return "changed";
    }
}
~~~

Four endpoints are explicitly declared. Security lives in the filter chain; the controller does not manually read username/password or check roles with `if` statements.

### 7.4. Configuring HttpSecurity and Calling build()

Create `src/main/java/com/example/securitychain/SecurityConfiguration.java`:

~~~java
package com.example.securitychain;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain appChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .csrf(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("mai")
                .password(encoder.encode("demo-user"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("demo-admin"))
                .roles("ADMIN")
                .build()
        );
    }
}
~~~

Read the `appChain` method step by step:

1. Spring detects the configuration class because it sits in the root package of `@SpringBootApplication`.
2. Spring supplies `HttpSecurity` as a parameter to the bean factory method.
3. `authorizeHttpRequests` declares three rule branches, with `anyRequest` as the fallback.
4. `httpBasic` enables HTTP Basic authentication, convenient for observing 401 responses and sending credentials in the lab.
5. `csrf(Customizer.withDefaults())` preserves default CSRF protection. In a servlet configuration, POST operations lacking a CSRF token can be blocked before entering the controller.
6. `http.build()` builds the chain and returns it to Spring to register as a `SecurityFilterChain` bean.
7. `users` and `passwordEncoder` support verifying the demo accounts. `UserDetailsService` is a separate branch from the URL policy, not a filter chain.
8. By default this chain applies to all requests because no `securityMatcher` restriction is set.

There is no `formLogin` in the demo: HTTP Basic is intentionally enabled to make API testing convenient. `httpBasic` does not make logins safe over plain HTTP outside localhost; real systems need HTTPS and proper credential management.

### 7.5. Building and Running the Application

With JDK 17+ and Maven installed:

~~~bash
java -version
mvn -version
mvn test
mvn spring-boot:run
~~~

Once the application is running on port 8080, open a second terminal and test with `curl`. The usernames/passwords below are **dummy demo data only**, not for real accounts; on Windows PowerShell, use `curl.exe` if `curl` is aliased to another command.

~~~bash
curl -s -o /dev/null -w 'public=%{http_code}\n' http://localhost:8080/public/ping
curl -s -o /dev/null -w 'private-anon=%{http_code}\n' http://localhost:8080/private/whoami
curl -s -o /dev/null -w 'private-mai=%{http_code}\n' -u mai:demo-user http://localhost:8080/private/whoami
curl -s -o /dev/null -w 'admin-mai=%{http_code}\n' -u mai:demo-user http://localhost:8080/admin/report
curl -s -o /dev/null -w 'admin-admin=%{http_code}\n' -u admin:demo-admin http://localhost:8080/admin/report
curl -s -o /dev/null -w 'post-no-csrf=%{http_code}\n' -u mai:demo-user -X POST http://localhost:8080/private/change
~~~

Expected status output:

~~~text
public=200
private-anon=401
private-mai=200
admin-mai=403
admin-admin=200
post-no-csrf=403
~~~

Explanation of each case:

- **Public = 200** because `/public/ping` matches `permitAll`.
- **Private anonymous = 401** because `/private/whoami` requires authentication and the configuration uses HTTP Basic.
- **Private Mai = 200** because demo credentials are valid, and `getName()` provides `mai`.
- **Admin Mai = 403** because Mai has `ROLE_USER` but does not have `ROLE_ADMIN`.
- **Admin admin = 200** because the admin account has `ROLE_ADMIN`.
- **POST missing CSRF = 403** because the chain enables protection for unsafe methods. This is expected behavior in the demo, not a failure of `http.build()`.

When using `curl -u`, credentials can remain in shell history or process lists; this example is only for localhost with dummy secrets. Note that response bodies/headers, redirects, proxies, and other security settings can alter results in real projects.

### 7.6. Testing with MockMvc

Create `src/test/java/com/example/securitychain/SecurityRulesTest.java`:

~~~java
package com.example.securitychain;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityRulesTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointIsOpen() throws Exception {
        mvc.perform(get("/public/ping"))
                .andExpect(status().isOk())
                .andExpect(content().string("pong"));
    }

    @Test
    void privateEndpointRequiresAuthentication() throws Exception {
        mvc.perform(get("/private/whoami"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(username = "mai", roles = "USER")
    void userCanOpenPrivateEndpoint() throws Exception {
        mvc.perform(get("/private/whoami"))
                .andExpect(status().isOk())
                .andExpect(content().string("mai"));
    }

    @Test
    @WithMockUser(username = "mai", roles = "USER")
    void userCannotOpenAdminEndpoint() throws Exception {
        mvc.perform(get("/admin/report"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "admin", roles = "ADMIN")
    void adminCanOpenAdminEndpoint() throws Exception {
        mvc.perform(get("/admin/report"))
                .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(username = "mai", roles = "USER")
    void unsafePostWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/private/change"))
                .andExpect(status().isForbidden());
    }
}
~~~

`@WithMockUser` places a test identity into the test's `SecurityContext`; it **does not verify passwords against `InMemoryUserDetailsManager`**. Therefore, combine the rule tests above with real requests (or MockMvc HTTP Basic) if you want to test the full login flow. The `post` test without a CSRF token verifies a protection layer separate from authorization.

In real environments, add tests for per-record, tenant, and business-state permissions; `hasRole("ADMIN")` does not solve object-level authorization by itself.

## 8. From Source Code to Behavior: Distinguishing Three Moments

A way to verify what is happening:

| Moment | Actual work | Participating components |
| --- | --- | --- |
| **Compile time** | Java compiler checks syntax and types `HttpSecurity`, `SecurityFilterChain` | JDK, Maven/Gradle, libraries on classpath |
| **Context startup** | Spring creates beans, runs DSL, calls `http.build()`, orders filters, finalizes chain | Spring `ApplicationContext`, `HttpSecurity`, configurers |
| **Request time** | `FilterChainProxy` picks a chain, filters run, endpoint is allowed/denied | Servlet container, `DelegatingFilterProxy`, `FilterChainProxy`, filters, MVC |

If a configuration is invalid and `http.build()` throws an exception during bean creation, the application may **fail to start**. But if the app starts and `GET /admin/report` returns 403, that is usually the **result of runtime authorization logic**, not a build failure.

Another example: `GET /public/ping` returns 404 while the filter log shows `permitAll`. That may simply mean the request passed security successfully but Spring MVC could not find a controller/route; not every non-200 status is a Security error.

## 9. Creating Multiple Chains with Multiple build() Calls

An application may want `/api/**` to use HTTP Basic while the web site uses form login. We define **two different `@Bean` methods**, each receiving `HttpSecurity` and building a separate chain:

~~~java
// Configuration fragment inside a Servlet app @Configuration class.
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public/**").permitAll()
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}

@Bean
@Order(2)
SecurityFilterChain webChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/**").permitAll()
            .anyRequest().authenticated()
        )
        .formLogin(Customizer.withDefaults())
        .build();
}
~~~

This is an **illustrative fragment**: it requires a class, imports (`@Order`, `HttpSecurity`, `Customizer`, etc.), a user source, and matching controllers before running.

How `FilterChainProxy` chooses:

~~~text
GET /api/orders
    |
    +--> chain @Order(1), matcher /api/** -> matches
           |  uses filters/rules of apiChain
           v
         stop checking subsequent chains

GET /profile
    |
    +--> chain @Order(1), matcher /api/** -> does not match
    |
    +--> chain @Order(2), matcher all requests -> matches
           |  uses filters/rules of webChain
           v
         stop chain selection
~~~

**Only the first chain matching the request is selected.** Spring Security does not run both chains and combine their permissions. `@Order` here determines chain evaluation order, which is **different** from the order of individual filters within a chain.

There should be a fallback chain covering remaining requests. If both chains use restrictive `securityMatcher`s, a URL falling outside every matcher will **bypass the Spring Security filter chain**. This is a dangerous configuration mistake when assuming `anyRequest().authenticated()` in the first chain protects the entire application.

### Mind Endpoints Provided by Filters

Some endpoints like `POST /login` or `POST /logout` can be handled by Spring Security filters rather than application controllers. If you place `formLogin` in a chain restricted by `securityMatcher("/api/**")` while the login URL is `/login`, that endpoint may **not lie inside the chain** to be processed. Login URLs must be designed to match the chain's scope.

If Actuator is present, once you declare a custom chain, the application must review protection for exposed management endpoints. Spring Boot yields default web security once a `SecurityFilterChain` bean exists; do not assume Boot's default rules continue protecting Actuator for you.

## 10. Choosing Where to Place Custom Filters

Some applications need custom filters to read headers, validate tenants, or record audit events. `HttpSecurity` provides methods such as:

~~~java
http.addFilterBefore(customFilter, UsernamePasswordAuthenticationFilter.class);
http.addFilterAfter(customFilter, BasicAuthenticationFilter.class);
http.addFilterAt(customFilter, SomeKnownFilter.class);
~~~

This only **illustrates the signatures/positioning**, with `customFilter` and `SomeKnownFilter` as placeholder names to convey the idea. Do not copy this snippet verbatim into a project without valid filter classes.

- `addFilterBefore`: inserts the filter before a filter whose order Spring Security recognizes.
- `addFilterAfter`: inserts after a recognized filter.
- `addFilterAt`: registers at the position corresponding to a known filter; **do not assume it automatically replaces the old filter completely**. Two filters at the same position can leave ordering nondeterministic.

Placing a filter in the wrong position can make it run before authentication information is ready, or after authorization has already made a decision. Identify which problem the filter solves: authentication, authorization, request protection, or auditing.

When a `Filter` is declared both as a **Servlet container Filter bean** and added directly to `HttpSecurity`, there is a risk the filter is invoked twice (once by the container, once inside Spring Security). Control registration and apply only the intended mechanism.

Before adding a filter, consider whether the requirement actually belongs in an `AuthorizationManager`, `AuthenticationProvider`, `OncePerRequestFilter`, or business service. Adding custom filters should not become the default way to implement every security rule.

## 11. Subtle Differences That Have Major Impact When Writing the DSL

### 11.1. permitAll Does Not Mean Bypassing Spring Security

If configured as:

~~~java
.requestMatchers("/public/**").permitAll()
~~~

a public request **still passes through the security filter chain** when the chain's matcher matches, so it can receive security headers and other protections. `permitAll` only states that the authorization rule requires no authority for that path.

Conversely, `WebSecurityCustomizer.ignoring()` can make requests **skip Spring Security** completely. For static resources, modern Spring Security documentation usually recommends `permitAll` so they still receive headers and baseline protections.

### 11.2. CSRF Configuration and Authentication Do Not Overlap

`authorizeHttpRequests(...).permitAll()` does not make `CsrfFilter` disappear. A POST to a public URL can still require a CSRF token depending on policy and authentication mechanism. A 403 on POST may be due to a missing CSRF token **even when roles are sufficient**.

In the demo, `POST /private/change` with Basic credentials but no CSRF token is expected to return 403. Turning off CSRF globally just because POST testing returns 403 can open vulnerabilities for browsers using cookies; understand the client, how credentials are sent, and evaluate defenses first.

### 11.3. URL Rules Do Not Replace Data-Level Permissions

~~~java
.requestMatchers("/documents/**").hasAuthority("DOC_READ")
~~~

This rule checks an authority when accessing the feature. It does not automatically know whether the user is allowed to view a **specific document ID**. Services/repositories still need owner/tenant/sharing policies per resource.

### 11.4. @Bean Method Name Is Not a URL Matcher

You can name a method `adminChain`, but if you do not configure `securityMatcher("/admin/**")`, that method name **does not restrict** requests to `/admin/**`. The request matcher and DSL rules control the scope.

### 11.5. Servlet HttpSecurity Differs from WebFlux ServerHttpSecurity

Spring MVC/Servlet uses `HttpSecurity` and `SecurityFilterChain`. WebFlux/Reactive uses `ServerHttpSecurity` and `SecurityWebFilterChain`; security filters run in the reactive mechanism. Declarations and components cannot be swapped simply by changing import names.

## 12. Diagnosing Build and Runtime Errors

When configuration behaves unexpectedly, check in order:

| Symptom | Investigation path |
| --- | --- |
| `SecurityFilterChain` bean does not appear | Is the `@Configuration` class scanned/imported? Is there a wrong `@Profile`/condition? |
| Application startup fails at `http.build()` | Read the root exception, conflicting DSL rules/configurers, missing beans |
| Default filter chain appears instead of custom chain | Check actual beans, package scan, and Boot auto-configuration conditions |
| Request goes through the wrong chain | `@Order`, `securityMatcher`, request type, dispatcher type |
| A URL hits no security filter at all | Is there a fallback chain covering that URL? |
| Returns 401 despite sending credentials | Are the right provider and auth mechanism used? Is HTTP Basic/form/token enabled? |
| Returns 403 despite being logged in | Missing authority, CSRF token, or another policy condition |
| Returns 302 to `/login` | Could be form login's `AuthenticationEntryPoint`, not necessarily a bug |
| Returns 404 after being permitted | Does the controller/route exist? 404 does not mean Security denied it |
| Custom filter runs twice | Is the filter registered both in the container and in the Security chain? |

Enable controlled security logging in development:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

`TRACE` can be selected when really needed to analyze a specific filter, but logs may contain paths, authentication-related info, and sensitive metadata; do not enable verbose logging carelessly in production.

Also check Boot's **Condition Evaluation Report** with `--debug` to see why auto-configuration backed off. Even when you see a `SecurityFilterChain` bean, still test requests against each important path to confirm the right chain is chosen.

### Can You Inspect the Built Filter List?

In a running application, `FilterChainProxy` manages the `SecurityFilterChain`s. When debugging, you can set a breakpoint in `FilterChainProxy` or use appropriate logging to see which matcher matched and which filters were used. That is closer to runtime truth than only reading the DSL.

Do not write tests solely to assert the exact default filter count, because Spring Security versions or options can add/remove filters while keeping the policy valid. More valuable tests verify **whether requests are blocked or allowed as required by business rules**.

## 13. Common Conceptual Mistakes

1. **"`HttpSecurity` is the filter that handles every request."** False: it is a builder; the built chain holds the filters that run.
2. **"`http.build()` authenticates users immediately."** False: building happens at configuration time, with no concrete request.
3. **"Swapping `httpBasic()` and `csrf()` reverses the filter order."** Incorrect; Spring Security determines filter ordering internally.
4. **"The `SecurityFilterChain` bean itself is the servlet filter named `springSecurityFilterChain`."** Not quite: `FilterChainProxy` dispatches across chains and is wired into the servlet filter chain via `DelegatingFilterProxy`.
5. **"`anyRequest()` always covers the whole website."** It only covers requests selected into the chain; `securityMatcher` can limit scope.
6. **"Multiple `SecurityFilterChain`s run together on one request."** `FilterChainProxy` uses only the first matching chain.
7. **"Because I have my own `SecurityFilterChain`, Boot stops creating the default user."** Web security chains and user stores are separate configuration branches.
8. **"`permitAll` skips all filters, including CSRF."** False: `permitAll` is an authorization rule.
9. **"A 403 on an API POST means `hasRole` failed."** It could be CSRF; inspect filters and policies.
10. **"A custom filter can be inserted anywhere."** False: position determines what SecurityContext and mechanisms are ready.
11. **"`addFilterAt` definitely removes the old filter."** Do not rely on this assumption; verify actual registration and ordering.
12. **"Configuration ran once locally so production is secure."** You still need to test resource-level permissions, CSRF, sessions, secrets, TLS, and logging.
13. **"Having an API chain means every request including Actuator is protected."** Not guaranteed if the matcher is restricted or a fallback is open.
14. **"WebSecurityConfigurerAdapter is required for configuration."** No; the Java DSL with a `SecurityFilterChain` bean is the modern approach.

## 14. Exercises to Verify Understanding of the Build Step

**Question 1.** What type of object does `http.build()` return when using the Servlet DSL, and has any user been logged in at that moment?

*Answer:* It creates a `SecurityFilterChain` (typically `DefaultSecurityFilterChain`) containing a matcher and filters; no specific request is authenticated at build time.

**Question 2.** How do `securityMatcher("/api/**")` and `requestMatchers("/api/admin/**")` differ?

*Answer:* The first decides whether **the chain is selected** for a request. The second decides an **authorization rule** inside the chain once the chain has been selected.

**Question 3.** An API chain has `securityMatcher("/api/**")` and `anyRequest().authenticated()`. Does that protect `GET /profile`?

*Answer:* No, if no other chain matches. `GET /profile` does not enter the API chain, so `anyRequest()` inside that chain is never evaluated.

**Question 4.** Why does `@Order(1)` matter when there are multiple `SecurityFilterChain`s?

*Answer:* It affects the order in which `FilterChainProxy` evaluates chains; only the first matching chain handles the request. It is not a command to reorder filters inside a single chain.

**Question 5.** A user with `ROLE_USER` makes a POST allowed by `authenticated()` but has no CSRF token. What can the outcome be?

*Answer:* It can still be rejected, typically with 403, because CSRF is a separate mechanism from Authentication/authority checks.

**Question 6.** Why does a custom `@Bean SecurityFilterChain` not automatically remove Boot's generated test user?

*Answer:* The web security chain and user-source auto-configuration are two separate conditional branches. You need an appropriate `UserDetailsService`, `AuthenticationProvider`, or `AuthenticationManager` to replace the default user source.

**Question 7.** If `http.build()` succeeds but requests still redirect to `/login`, is that a build error?

*Answer:* Not necessarily. At runtime, the app may be using a form-login entry point because the request requires authentication. Check the selected chain and actual `AuthenticationEntryPoint`.

**Question 8.** When adding a custom filter with `addFilterBefore`, what should you check beyond whether the code compiles?

*Answer:* Its position relative to authentication/CSRF/authorization filters, whether it is registered once or twice, the chain's matcher, and HTTP tests verifying correct behavior.

## 15. Checklist When Finishing HttpSecurity Configuration

- [ ] Project is genuinely **Servlet/Spring MVC**, using `HttpSecurity` and `SecurityFilterChain`, not confused with WebFlux.
- [ ] `@Configuration` class is scanned/imported by Spring, and the `@Bean` method returns the chain after `http.build()` succeeds.
- [ ] Each chain is built from a valid `HttpSecurity`; the same builder is never built twice.
- [ ] Clear `authorizeHttpRequests` rules exist, with specific rules placed before the fallback.
- [ ] `securityMatcher` and `@Order` are appropriate when multiple chains exist.
- [ ] No important URL falls outside all chains; an appropriate fallback exists.
- [ ] Login/logout handling endpoints and Actuator endpoints are protected within the right scope.
- [ ] Providers/user store, `PasswordEncoder`, and actual authentication mechanisms are configured properly.
- [ ] CSRF, security headers, CORS, session, and exception handling are reviewed for the client type.
- [ ] Filters/CSRF are not disabled just to turn 401/403 into 200.
- [ ] Tests exist for public/anonymous/user/admin, POST with and without CSRF tokens, and URLs outside matchers.
- [ ] Logs/condition reports were checked when behavior differed from expectations, and real requests were tested.

When reading a `@Bean SecurityFilterChain`, separate three questions in order: **What policy is `HttpSecurity` defining -> what chain with which matcher/filters does `build()` create -> for which requests will `FilterChainProxy` select and run that chain?** Answering all three accurately explains Servlet configuration from startup through protecting real URLs.

### References

- [Spring Security 6.5 — Java Configuration](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html)
- [Spring Security 6.5 — Servlet Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html)
- [Spring Security 6.5 — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security 6.5 — CSRF Protection](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
- [Spring Security — HttpSecurity API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/web/builders/HttpSecurity.html)
- [Spring Security — AbstractConfiguredSecurityBuilder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/AbstractConfiguredSecurityBuilder.html)
- [Spring Boot 3.5 — Security Auto-configuration](https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html)
- [Spring Boot 3.5.16 release and OSS support notice](https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/)
