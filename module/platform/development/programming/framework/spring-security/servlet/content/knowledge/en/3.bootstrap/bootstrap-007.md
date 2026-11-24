# Distinguishing Spring Boot Auto-Configuration from Application-Provided Security Configuration

## 1. Goal and Scope

When you add `spring-boot-starter-security` to **Spring Boot using Servlet/Spring MVC**, the application is usually protected even before the developer writes any Spring Security configuration class. That is the result of Spring Boot **auto-configuration**: Boot inspects the classpath, application type, and existing beans, then supplies default beans *when conditions match*.

Conversely, **application-provided configuration** consists of the beans and rules that the developer explicitly declares to meet a concrete access policy. The most important point: **Boot's default for the HTTP security chain and Boot's default for the in-memory user are two separate branches**. Creating a custom `SecurityFilterChain` normally stops Boot from creating the **default HTTP chain**, but **does not automatically stop creating the default account**. And creating a custom `UserDetailsService` can stop Boot from creating the **default account**, while the **default HTTP chain remains in use**.

This lesson focuses on the **initialization phase of Servlet security configuration**, how Spring Boot decides which beans to create, and how to replace defaults safely. It does not apply verbatim to WebFlux, which uses `SecurityWebFilterChain` instead of Servlet `SecurityFilterChain`.

After studying this, you should be able to answer:

- Does security come from the Spring Security framework or from Spring Boot auto-configuration?
- When does Boot supply `SecurityFilterChain`, `UserDetailsService`, and the generated password?
- Which **default part** stops running when a custom bean is declared?
- Why can you have a custom HTTP configuration while the startup log still prints a generated default password?
- How do you verify which chain is actually in use and ensure no URLs are left uncovered?

## 2. Two Different Roles: Spring Security and Spring Boot

**Spring Security** is the framework handling authentication, authorization, security context, CSRF, security headers, login mechanisms, etc. In a Servlet application, HTTP request processing normally starts at a Servlet `DelegatingFilterProxy`, delegates to the `springSecurityFilterChain` bean of type `FilterChainProxy`, and selects a `SecurityFilterChain` matching the request.

**Spring Boot** helps configure and wire these components inside the Spring ApplicationContext. When dependencies and conditions match, Boot:

1. Enables/wires HTTP security infrastructure for the Servlet application.
2. Provides a default HTTP `SecurityFilterChain` if the application has not supplied a custom chain.
3. May create a `UserDetailsService` containing a default development account if no suitable identity-management mechanism exists.
4. Applies certain properties such as `spring.security.user.name`, `spring.security.user.password`, and `spring.security.user.roles` **to Boot's default account**, while that default branch remains active.

This division of labor explains why “Boot secures the app automatically” **does not mean** Spring Security only works through Boot. When you define your own `SecurityFilterChain`, Spring Security still executes filters, authentication, and authorization according to the new configuration.

### Visualizing the Two Independent Decision Branches

~~~text
Spring Boot Servlet application + Spring Security on classpath
                           |
                           v
                 Auto-configuration
                           |
             +-------------+-------------+
             |                           |
             v                           v
   Default HTTP security          Default login user
   Is there an app-declared       Is there another identity
   SecurityFilterChain?           config (UserDetailsService/provider/
             |                    AuthenticationManager...)?
       +-----+-----+                     |
       |           |                 +---+---+
      No          Yes               No      Yes
       |           |                 |       |
       v           v                 v       v
 Boot may       Boot backs       Boot may  Boot backs
 create default off on default   create    off on
 chain          chain            default   default user
                                 user
~~~

This diagram describes the **typical** behavior of Spring Boot 3.x with Spring Security 6.x on the Servlet stack. Actual conditions also depend on other beans, libraries, and application types (for instance OAuth2 resource server/client). Always check the configuration and Condition Evaluation Report for the version you are using.

## 3. When No Security Configuration Is Declared

Suppose a Spring MVC application has the dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
</dependency>
~~~

And only declares an endpoint:

~~~java
@RestController
class HelloController {

    @GetMapping("/hello")
    String hello() {
        return "hello";
    }
}
~~~

Without any custom security beans and with default conditions satisfied, Boot supplies an HTTP security chain conceptually equivalent to:

~~~java
@Bean
SecurityFilterChain defaultLikeChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .formLogin(Customizer.withDefaults())
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

**This code illustrates the default policy, not a snippet to copy into an app where you want Boot to auto-configure security.** In a typical scenario, all URLs require login. When calling `GET /hello` without credentials, API clients normally receive **401** with an HTTP Basic challenge; browsers requesting HTML may be **redirected to the login page**. These are two different ways to respond to an unauthenticated request, not a sign that Boot created two conflicting security layers.

If no suitable custom user source exists, Boot may create a default user named **`user`** with a random password printed in the startup log, or take name/password from `spring.security.user.*` properties. Using the default password is only convenient for development and is not a production login solution.

A simple request travels along this path:

~~~text
GET /hello
   -> Servlet container
   -> DelegatingFilterProxy
   -> FilterChainProxy
   -> Boot-provided SecurityFilterChain
   -> authentication + authorization
      -> unauthenticated: entry point (401 or appropriate redirect)
      -> valid: DispatcherServlet -> HelloController
~~~

Note: Spring MVC does not “protect itself” on the controller above just because `@RestController` is present. Spring Security intercepts before MVC when policy requires it.

## 4. When Does Boot Back Off in Favor of the Application?

### 4.1. Backing Off on HTTP Configuration: You Provide `SecurityFilterChain`

In a typical Servlet setup, Boot creates the **default web security chain** only when no `SecurityFilterChain` bean is supplied by the application or another library. As soon as one bean of this type exists, Boot will not add its **default chain**.

Example:

~~~java
@Configuration
class ApplicationSecurity {

    @Bean
    SecurityFilterChain applicationChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

Once this bean exists, Boot's default HTTP configuration (which enables both form login and HTTP Basic by default) **is not appended or merged automatically** onto the rules above. The application chain explicitly enables `httpBasic`; because `formLogin` is not declared, the example does not actively enable a form login UI.

However, framework components remain active: `FilterChainProxy`, security context, filter mechanics, authorization, etc. Boot “backing off on the default chain” **does not mean** disabling Spring Security or removing all other auto-configurations.

### 4.2. Backing Off on the Default User: You Provide an Identity Source

Another branch of Boot, typically handled by `UserDetailsServiceAutoConfiguration` in standard username/password scenarios, can create a default `InMemoryUserDetailsManager`. This branch backs off once suitable authentication components are present, for example:

- An application-provided `UserDetailsService` bean.
- An application-provided `AuthenticationProvider` or `AuthenticationManager` bean.
- Specialized authentication mechanisms/modules with their own auto-configuration conditions, such as certain OAuth2 setups.

Do not treat this example list as an exhaustive copy of conditions across all Boot versions; check actual conditions if the application uses multiple starters.

Example providing only users:

~~~java
@Bean
UserDetailsService users(PasswordEncoder encoder) {
    UserDetails alice = User.withUsername("alice")
        .password(encoder.encode("local-dev-password"))
        .roles("USER")
        .build();
    return new InMemoryUserDetailsManager(alice);
}
~~~

When this bean is managed by Spring and the default user branch qualifies to back off, Boot's `user`/random password is no longer created by that branch. **If the application still has not declared a `SecurityFilterChain`, Boot may still supply the default HTTP chain requiring login on every URL.**

The Java snippet above is an **illustrative `@Bean` method**, which must sit inside a `@Configuration` class alongside a `PasswordEncoder` bean; a complete runnable example is provided in section 6.

### 4.3. Four-Scenario Matrix to Remember

Assuming a typical Servlet application with the security starter and no other special configuration:

| Application's `SecurityFilterChain`? | Suitable app identity source? | Boot's default HTTP chain | Boot's default user |
| --- | --- | --- | --- |
| No | No | **Yes** | **Yes** |
| **Yes** | No | **No**; uses app chain | **May still exist** |
| No | **Yes** | **Yes** | **No** |
| **Yes** | **Yes** | **No**; uses app chain | **No** |

The second row is a common misconception: declaring `@Bean SecurityFilterChain` while the startup log **still prints a generated security password** does not mean your custom chain failed. That log pertains to the **default user**, and does not by itself prove which chain is active.

The third row is also important: adding a `UserDetailsService` **does not make endpoints public**. With Boot's default chain, HTTP authorization still requires authentication; only the user set or verification source changed.

### 4.4. Properties Do Not Replace Custom Beans

Example:

~~~yaml
spring:
  security:
    user:
      name: local
      password: dev-only-password
      roles: USER
~~~

These properties configure the **Boot-generated default in-memory user** when that branch is active. They are **not** a general DSL for declaring which URLs are `permitAll`/`hasRole`. When an application has its own `UserDetailsService`, do not expect `spring.security.user.password` to overwrite passwords managed by your custom service.

In real environments, avoid storing production application passwords in committed configuration files. Use proper identity mechanisms, secret management, and password hashing. The YAML snippet above **only illustrates the properties**, not a guide to putting sample passwords into production.

## 5. Initialization Order: Conditions and Bean Presence

Boot does not “run a default security layer first and then wait for the app to override individual rules.” Auto-configuration is declared with conditions such as:

- **Presence of classes on the classpath** (e.g., relevant Spring Security classes).
- **Matching web application type**, here Servlet.
- **Presence or absence of specific beans in the ApplicationContext**, typically using logic like `@ConditionalOnMissingBean`.
- **Whether other auto-configurations are active**, configuration ordering, and module conditions.

Spring Boot collects bean definitions and evaluates conditions, so application configuration can prevent a default branch from registering. Only after the context is ready does Spring Security's request-time phase operate using the resulting beans. Do not confuse **startup bean-creation decisions** with **request-time authorization decisions**.

~~~text
STARTUP                                REQUEST
-------                                -------
Read classpath, properties             HTTP request arrives at container
    -> evaluate auto-config                -> DelegatingFilterProxy
    -> collect custom @Bean                -> FilterChainProxy
    -> create chain/user/provider          -> select SecurityFilterChain
    -> finalize ApplicationContext        -> authenticate / authorize
                                               -> MVC + service if allowed
~~~

Your application's **bean name** (such as `applicationChain`) does not need to be a fixed string; what matters is the **`SecurityFilterChain` type and bean registration in the Spring context**. By contrast, `springSecurityFilterChain` is the infrastructure bean name typically referenced by `DelegatingFilterProxy`.

A `SecurityFilterChain` bean can also come from an add-on library, not just the `SecurityConfig.java` file you wrote. Therefore, when results differ from expectations, inspect **all beans in the context**, not just one configuration file.

## 6. Runnable Spring Boot 3.x / Spring Security 6.x Example

This example uses **Java 17+, Spring MVC, and HTTP Basic**. It supplies both `SecurityFilterChain` and `UserDetailsService`, thereby replacing **both independent default branches**. In-memory accounts and sample passwords are for learning only; passwords are hashed with BCrypt at runtime.

### 6.1. Project Structure

~~~text
boot-security-choice/
├── pom.xml
└── src/main/java/com/example/securitychoice/
    ├── SecurityChoiceApplication.java
    ├── SecurityConfig.java
    └── DemoController.java
~~~

**`pom.xml`:**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>boot-security-choice</artifactId>
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

**`SecurityChoiceApplication.java`:**

~~~java
package com.example.securitychoice;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityChoiceApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityChoiceApplication.class, args);
    }
}
~~~

**`SecurityConfig.java`:**

~~~java
package com.example.securitychoice;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    // Custom HTTP chain: Boot no longer creates the default HTTP chain.
    @Bean
    SecurityFilterChain applicationChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    // Custom user store: Boot no longer creates the default in-memory user.
    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo-pass"))
            .roles("USER")
            .build();
        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("demo-pass"))
            .roles("ADMIN")
            .build();
        return new InMemoryUserDetailsManager(alice, admin);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }
}
~~~

**`DemoController.java`:**

~~~java
package com.example.securitychoice;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public String publicEndpoint() {
        return "public OK";
    }

    @GetMapping("/profile")
    public String profile(Authentication authentication) {
        return "hello " + authentication.getName();
    }

    @GetMapping("/admin")
    public String admin() {
        return "admin OK";
    }
}
~~~

This code demonstrates:

- `/public` has `permitAll()`: requests do not require login yet still pass through the security chain.
- `/profile` requires a valid identity due to `anyRequest().authenticated()`.
- `/admin` requires the `ROLE_ADMIN` authority under `hasRole("ADMIN")`'s default convention.
- `alice` has only `ROLE_USER`; `admin` has `ROLE_ADMIN`. Authentication does not imply every permission.
- `SecurityFilterChain` provides the HTTP policy itself; `UserDetailsService` provides the users itself. Boot has no reason to create user `user` or the default HTTP chain once both branches have been replaced by the application.

**This is an illustrative HTTP Basic configuration, not a complete production template.** For applications using cookies/sessions and state-changing endpoints, design CSRF, sessions, logout, CORS, and login appropriately; this example only has HTTP GETs, so it does not disable CSRF.

### 6.2. Running and Verifying

In the directory containing `pom.xml`, using JDK 17+ and Maven:

~~~bash
mvn spring-boot:run
~~~

By default the server runs on port 8080. Run the following commands in a shell with real `curl` (Windows PowerShell may require `curl.exe`). The `# ...` comments indicate **expected results**, assuming the app runs unmodified without another port/config.

~~~bash
curl -s http://localhost:8080/public
# public OK

curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/profile
# 401

curl -s -u alice:demo-pass http://localhost:8080/profile
# hello alice

curl -s -o /dev/null -w '%{http_code}\n' -u alice:demo-pass http://localhost:8080/admin
# 403

curl -s -u admin:demo-pass http://localhost:8080/admin
# admin OK

curl -s -o /dev/null -w '%{http_code}\n' -u user:anything http://localhost:8080/profile
# 401
~~~

Explanation: user `user` does not exist in the custom `InMemoryUserDetailsManager`; Boot's configured password (if ever set) no longer governs this user source. If you see startup logs mentioning a generated default password even after creating both beans as shown, check bean registration and specific configuration conditions rather than jumping to conclusions from a single symptom.

### 6.3. Experiments to Distinguish the Two Branches

**Experiment A — Keep custom chain, remove custom user store bean.** In a copy of the demo project, remove only the `@Bean UserDetailsService users(...)` method; you may keep `PasswordEncoder`. When no other authentication mechanism causes Boot to back off, Boot can supply the default in-memory user; `/public`, `/profile`, and `/admin` policies still come from the **custom `applicationChain`**. The default user carries `ROLE_USER`, so it fails `hasRole("ADMIN")`.

**Experiment B — Keep custom user store, remove custom chain bean.** Remove only the `@Bean SecurityFilterChain applicationChain(...)` method. Without another chain, Boot can supply the **default chain**: `/public` as well as `/profile`/`/admin` require authentication, because Boot does not know about the `permitAll` and `hasRole` rules you just removed. Logging in with `alice` or `admin` uses the custom user store; the default username `user` does not appear.

**Experiment C — Remove both custom beans.** With default configuration, Boot can supply both the chain protecting all endpoints and the default user. Compare logs and HTTP statuses across experiments to confirm what changed.

Run these experiments by **editing code, rebuilding, and restarting**, not deleting a bean from a running app and expecting auto-configuration to re-evaluate per request. Experiments A/B are separate variants of the complete example, **not configurations active in one project simultaneously**.

## 7. Multiple SecurityFilterChains: Boot Does Not Auto-Add a Fallback

A subtle bug is declaring a chain that matches only `/api/**` and assuming other URLs are still protected by Boot's default chain. On the Servlet stack, once an application supplies a `SecurityFilterChain`, do not expect Boot to create an extra default chain to cover remaining URLs.

**Incorrect example when intending to protect all endpoints:**

~~~java
@Bean
SecurityFilterChain apiOnly(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

This bean scopes the chain strictly to `/api/**`. If no other chain matches `/profile`, requests to `/profile` can pass through the application **without receiving Spring Security filter chain protections**; this is a URL coverage gap. Do not fix it with `requestMatchers("/**")` *inside a chain that only matches `/api/**`*, because the chain-level matcher already excluded other URLs beforehand.

One approach is providing **two chains** with explicit ordering:

~~~java
@Configuration
class MultiChainSecurity {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .build();
    }
}
~~~

This snippet illustrates **an alternative configuration** to `SecurityConfig` in section 6; to include it in a Java project, add the corresponding imports (`@Configuration`, `@Bean`, `@Order`, `HttpSecurity`, `SecurityFilterChain`, `Customizer`), and do not declare it alongside `applicationChain` without designing ordering. For each request, `FilterChainProxy` selects the **first matching chain**: `/api/**` uses the API chain, and everything else falls into the fallback. `securityMatcher(...)` determines which requests a chain applies to; `requestMatchers(...)` inside `authorizeHttpRequests` decides permissions **within that chain**.

Before using multiple chains, map out your URLs: APIs, web pages, static assets, login, error, and management/Actuator endpoints. Ensure every endpoint needing protection matches an intended chain. If using Actuator, understand management endpoint security policies and which auto-configurations back off when you supply your own chain.

## 8. Do Not Confuse Configuration Forms

| Configuration approach | Primary decision | Limitation to keep in mind |
| --- | --- | --- |
| Adding `spring-boot-starter-security` | Puts Spring Security on classpath, triggers Boot auto-config conditions | Does not create app-specific users or domain policies |
| `spring.security.user.*` | Configures Boot's default in-memory user when that branch is active | Does not declare URL rules and does not control custom user stores |
| `@Bean SecurityFilterChain` | HTTP request rules: URLs, authentication/authorization, CSRF, form/basic, etc. | Causes Boot not to create default HTTP chain; app is responsible for coverage |
| `@Bean UserDetailsService` | How users and credentials are loaded for username/password flows | Does not itself alter `permitAll`, `hasRole`, or HTTP matchers |
| `@Bean AuthenticationProvider` | How specific credentials are verified | Does not replace URL protection |
| `@Bean AuthenticationManager` | Coordinates authentication according to app mechanisms | Does not directly define all HTTP authorization rules |
| `@EnableMethodSecurity` + `@PreAuthorize` | Permissions at the method/service layer | Not enabled merely by adding starter; does not replace HTTP policy |
| `@EnableWebSecurity` | Enables Spring Security web config via annotation where needed | Standard Spring Boot Servlet already sets up web security via starter and auto-config; usually only a `SecurityFilterChain` bean is needed to customize |

`@EnableMethodSecurity` is a separate choice for method security. You can use `@PreAuthorize("hasRole('ADMIN')")` on a service to guard business actions, but it is **not a replacement** for endpoint matchers. Conversely, `hasRole("ADMIN")` in the HTTP chain does not automatically verify ownership of individual orders in the database.

Do not bring legacy recipes based on `WebSecurityConfigurerAdapter` into Spring Security 6/Spring Boot 3 projects; modern Spring Security favors the `SecurityFilterChain` bean model.

## 9. How to Determine Which Configuration Is Actually Running

### Check 1 — Find Beans, Do Not Infer from Filenames

Look for `@Bean SecurityFilterChain`, `@Bean UserDetailsService`, and `AuthenticationProvider`/`AuthenticationManager` beans in the application and included libraries. Verify whether the package containing `@Configuration` falls within `@SpringBootApplication`'s component scan scope. If the config class is not scanned, the intended bean may not exist and Boot applies defaults.

### Check 2 — Inspect the Condition Evaluation Report

Enable Spring Boot debug mode in development:

~~~bash
mvn spring-boot:run -Dspring-boot.run.arguments=--debug
~~~

Boot prints a report of auto-configuration conditions that matched or did not match. Look for groups related to `SecurityAutoConfiguration`, `SpringBootWebSecurityConfiguration`, and `UserDetailsServiceAutoConfiguration`. Condition names and details can vary by Boot version. The report answers **why a default bean was considered or backed off**; it does not directly prove that a specific endpoint is properly secured.

If Spring Boot Actuator is present and `/actuator/conditions` is enabled/exposed by configuration, you can view the condition report there. Never expose management endpoints or sensitive configuration details to unauthorized users.

### Check 3 — Inspect Chains and Requests in Spring Security

In local development, you can enable:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Use the log to observe requests, filter chains, and certain security decisions. When deep analysis is genuinely needed, `TRACE` yields more detail but is noisy. Never log credentials, tokens, or secrets; avoid leaving security debug logging enabled carelessly in production.

**Distinguish two questions when debugging:**

- **Did Boot create a default bean?** → inspect the condition report and bean list.
- **Which chain did `GET /api/orders` pass through and where was it rejected?** → inspect chain matching, authentication/authorization logs, HTTP status, and controller/service traces.

### Check 4 — Call Endpoints with Different Identities

Build a simple test matrix: unauthenticated, standard role, admin role; for each, call a public URL, a login-required URL, and an admin URL. Even a single misconfiguration can cause `/public` to return 401 or `/admin` to return 200 for an under-privileged user. This provides evidence of **request-time behavior**; combine it with reading beans and the condition report to locate the root cause.

## 10. Common Mistakes and Fixes

**Mistake 1: “I declared a SecurityFilterChain, so Boot won't generate a password anymore.”** Incorrect regarding the condition. The default chain and default user are two branches; provide an identity source or suitable provider if you want to replace the default user.

**Mistake 2: “Adding UserDetailsService makes endpoints public automatically.”** No. Boot may still apply the default HTTP chain `anyRequest().authenticated()`. You need a custom `SecurityFilterChain` for `permitAll` or custom role policies.

**Mistake 3: “Just setting `spring.security.user.roles=ADMIN` protects /admin.”** That property only affects the default user's authorities. URL rules for `/admin` must be declared in the authorization policy; if the default chain requires authentication for all URLs, roles are not used to separate endpoints.

**Mistake 4: “I made a custom chain for /api/**, so other URLs will use Boot's default chain.”** Not guaranteed; creating a chain bean already causes Boot's default chain to back off. You need a fallback chain covering the remainder where appropriate.

**Mistake 5: “`permitAll` is equivalent to bypassing Spring Security.”** No. A `permitAll` request still traverses the chain and receives security headers and necessary filters. Completely bypassing the filter chain (like `web.ignoring()`) has different consequences.

**Mistake 6: “Seeing 401 always means Boot's default chain is running.”** 401 can also come from a custom chain using HTTP Basic/bearer or other entry points. Check the matching chain and auto-config report; do not infer from status alone.

**Mistake 7: “Customizing SecurityFilterChain forces you to disable all CSRF.”** No. Other defaults on `HttpSecurity` depend on the application; for cookie-based web apps, CSRF is usually essential. GET-only examples do not require changing CSRF settings.

**Mistake 8: “Adding `@PreAuthorize` makes it run automatically.”** If `@EnableMethodSecurity` is not enabled or a call bypasses the Spring proxy (self-invocation), it may not take effect as expected. Check method security separately from HTTP policy.

**Mistake 9: “The app declared @Configuration, yet Boot still ignores it.”** Check component scanning, profiles, conditional beans, excluded configurations, and startup errors. Merely having a Java file in the project **does not guarantee** the bean was created.

## 11. Self-Check Questions

1. An application has its own `SecurityFilterChain` but no other `UserDetailsService`/provider; why is there still a generated password?
   - Because default user configuration and default HTTP chain configuration are independent; Boot may still create the default user.
2. An application replaces only `UserDetailsService`; why does `GET /public` still return 401?
   - Because the default HTTP chain may still require `authenticated()` on every request. Naming a path “public” does not make it public automatically.
3. Why is `securityMatcher("/api/**")` insufficient to protect `/admin`?
   - It only selects the chain for `/api/**` paths. Another chain must match `/admin` if that endpoint needs Spring Security protection.
4. Which command helps find why Boot created or backed off from creating a default bean?
   - Enable Boot's `--debug` and read the **Condition Evaluation Report**, combined with inspecting actual beans.
5. Where is the boundary between “startup auto-configuration” and “request authorization”?
   - Startup decides which beans/chains exist; at request time, Spring Security selects a chain and checks identity/authorities according to those beans.

**Remember:** In Spring Boot Servlet, ask **“which beans does Boot supply, which beans does the application supply, and which conditions caused Boot to back off?”** before asking **“which chain did the request enter and which rule did it hit?”**. Once you separate those two phases and two branches (HTTP chain vs. user source), you will understand most situations where auto-configuration appears to “override” application configuration.