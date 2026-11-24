# Role of Auto-Configuration and Conditions for Custom Configuration to Take Effect

You create a Spring Boot project, add `spring-boot-starter-security`, and run the application. Suddenly an API that previously returned `200 OK` asks for login. You declare a `SecurityFilterChain` to permit `/public/**`; requests start working. Yet the login screen still has a test `user` account created by Spring Boot, even though you "wrote custom Security configuration."

This is an ideal scenario for understanding **Spring Boot auto-configuration**: Boot registers default beans **conditionally**. When your application declares a bean playing the matching role, *part* of the defaults *back off*. That does not mean adding any arbitrary `@Configuration` makes all Spring Security defaults disappear.

Lesson goals: explain **what Boot auto-configures**, **which conditions cause custom configuration to actually take effect**, **how to separate request configuration from account configuration**, and **how to verify active configuration using logs, condition reports, and HTTP tests**.

The primary scope is **Spring Boot Servlet/Spring MVC + Spring Security**, with Java 17 and Spring Boot 3.5.16 examples. The conditional principles also apply to Boot 4, though class names and auto-configuration module organization may shift across major versions. The end of the lesson contrasts WebFlux.

## 1. What Is Spring Boot Auto-Configuration?

Spring Boot does not "read the application's mind." It inspects the **classpath**, **application type**, **declared beans**, **configuration properties**, and **other conditions** to decide whether to register default beans.

General overview:

~~~text
@SpringBootApplication
       |
       +--> enables @EnableAutoConfiguration
       |
       +--> discovers auto-configurations on the classpath
                 |
                 v
          Evaluates @Conditional...
                 |
        +--------+---------+
        |                  |
  Conditions match   Do not match
        |                  |
        v                  v
  Registers needed    Skips configuration
   default beans     (does not register bean)
        |
        v
  Spring ApplicationContext ready
~~~

`@SpringBootApplication` combines application configuration, component scanning, and enabling auto-configuration. Default configurations commonly use conditions such as:

| Condition | What does it check? | Common scenario |
| --- | --- | --- |
| `@ConditionalOnClass` | Is a class/library on the classpath? | Spring Security classes present to enable security auto-config |
| `@ConditionalOnMissingBean` | Is no bean of a target type registered yet? | No custom `SecurityFilterChain`, so add default chain |
| `@ConditionalOnBean` | Does a prerequisite bean already exist? | Add a feature only when a related bean exists |
| `@ConditionalOnWebApplication` | Is the app servlet, reactive, or a matching web type? | Servlet filters differ from reactive web filters |
| `@ConditionalOnProperty` | Does an environment property match a value? | Feature enabled only when a property condition holds |
| `@ConditionalOnMissingClass` | Is a specific library/class absent? | Avoid configuration incompatible with another dependency |

Each auto-configuration can combine **multiple conditions**, and an application's own bean can cause one default branch to back off. Do not assume `@ConditionalOnMissingBean` is true merely because you do not see that class in the current Java file: Spring inspects **bean definitions in the `ApplicationContext`**, not text searches for class names.

One more detail: conditions may sit at the **class level** or on **`@Bean` methods**. If placed on the class, the entire group of beans in that configuration may be skipped; if placed on a method, only that bean is skipped. Therefore "auto-configuration is disabled" always requires specifying **which part**.

### Auto-Configuration vs. Spring Security Framework Defaults

Distinguish two layers:

1. **Spring Boot auto-configuration** decides **which beans to create** in the application based on conditions.
2. **Spring Security** implements filter chains, authentication, and authorization once beans are created, with internal defaults inside `HttpSecurity` and its configurers.

Adding a custom `SecurityFilterChain` replaces *Boot's default web security configuration*. Yet Spring Security itself remains active; required filters still run according to `HttpSecurity`, and features you did not configure may retain their defaults. `http.build()` builds a real chain—it does not "turn off Spring Security."

## 2. What Does Boot Configure Right After Adding starter-security?

In a typical **Spring Boot 3.5 servlet** app with `spring-boot-starter-web` and `spring-boot-starter-security`, before registering replacement security beans:

- Web requests require authentication under the default policy.
- Depending on request type and `Accept` header, clients may encounter a login page or an HTTP Basic challenge.
- Boot can create an in-memory `UserDetailsService` with a single test account named `user` and a random password logged at startup.
- Boot can also provide `DefaultAuthenticationEventPublisher` if no matching bean exists.
- Endpoints like `/error` and Actuator endpoints must also be considered in security policies rather than assumed "public."

These behaviors are a **development starting point**. Boot's generated account and random password are not how production user systems are built. Moving to a real application requires explicit user sources, providers, secrets, and policies.

In Boot 3.5, documentation describes related configurations including `SecurityAutoConfiguration`, `SpringBootWebSecurityConfiguration`, and `UserDetailsServiceAutoConfiguration`. In Boot 4, modules and some class names change (such as `ServletWebSecurityAutoConfiguration`); the principle of **backing off by bean type and conditions** remains key.

### "Protecting Every URL by Default" Does Not Mean Every URL Has a Controller

Boot does not invent a `GET /orders` route or business accounts. It places a security layer around incoming requests. Hence a URL with no controller can return `401`/redirect before reaching `404` handling, depending on the filter chain and client. Never infer from that status code alone that a controller exists or is absent.

## 3. Two Configuration Branches to Keep Separate: Web Policy and User Store

The central takeaway of this lesson is that **`SecurityFilterChain` and `UserDetailsService` fulfill two independent roles**.

| What bean do you add? | Direct impact on Boot defaults | What NOT to infer |
| --- | --- | --- |
| `SecurityFilterChain` | Boot's default web protection chain backs off in favor of your defined chain | Does not automatically remove the test `user` account |
| `UserDetailsService` | Boot's default in-memory `UserDetailsService` backs off in favor of your bean | Does not automatically change filter chain URL policies |
| Suitable `AuthenticationProvider` or `AuthenticationManager` | Can also prevent Boot's default `UserDetailsService` from being created per matching conditions | Does not automatically open or lock endpoints as desired |
| `AuthenticationEventPublisher` | Replaces the default authentication event publisher bean | Does not replace the filter chain or user source |
| `PasswordEncoder` | Supplies password encoding/matching for components configured to use it | Does not replace the chain, accounts, or entire provider |
| `@EnableMethodSecurity` | Activates method-level security checks as configured | Does not replace all URL filtering or user loading |

Boot 3.5 docs state clearly: declaring a custom `SecurityFilterChain` stops Boot from **creating the default web security chain**, whereas the default `UserDetailsService` backs off only when a matching **authentication bean type** or other classpath condition is met (such as certain OAuth2/SAML modules).

Mental model diagram:

~~~text
                       ApplicationContext
                               |
             +-----------------+------------------+
             |                                    |
     Web security branch                 User/authentication branch
             |                                    |
Custom SecurityFilterChain @Bean?     UserDetailsService/Provider/Manager?
     /               \                           /            \
   Yes                No                       Yes             No
    |                  |                         |              |
Use app's         Boot may create         Do not create     Boot may create
chain             default chain           default user      default user*
    |                  |                         |              |
    +--------- filters HTTP requests ------------+------ authenticates accounts
~~~

`*` Additional conditions (such as OAuth2 client/resource server/SAML modules on the classpath and Spring Boot version) can also cause the default user config to back off. Do not treat the diagram as an absolute algorithm for every stack.

**Common source of confusion:** you added `@Bean SecurityFilterChain`, yet startup still logs a random password. That **does not mean** your custom chain was ignored. Your custom chain may be active while Boot still creates the test account because you did not supply an authentication source. Inspect the two branches separately.

## 4. Conditions for a Custom Configuration to Actually Take Effect

Merely writing a configuration class is not enough. A bean must **actually be registered and referenced by the components that use it**.

### 4.1. Appropriate Dependencies Present

A servlet project using Spring Security needs the right modules on the classpath. With Spring Boot, add the starter and let the BOM manage versions:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
</dependency>
~~~

Do not manually specify an arbitrary `spring-security-web` version while Boot manages modules, as that can create an incompatible classpath.

### 4.2. Configuration Must Belong to the ApplicationContext

A `@Configuration` class is discovered via component scanning or `@Import`. For example, a main class in `com.example.app` scans subpackages such as `com.example.app.security`, yet does not by default scan packages outside that tree. Putting the class outside scanned packages means `@Bean` methods are never invoked, even though the Java file compiles.

When using `@Bean`, the **return type** must match what Boot's conditions and consumers expect. For servlet security, a typical signature is:

~~~java
@Bean
SecurityFilterChain appSecurity(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(a -> a.anyRequest().authenticated())
            .build();
}
~~~

This is a **code fragment inside a valid `@Configuration`** illustrating only the bean type; it is not a standalone Java file.

### 4.3. Conditions Must Be Satisfied

A bean declared with `@Conditional...` will not appear in every situation. Conditions can fail due to a missing class, non-servlet app type, wrong property, or an existing replacement bean. With security configuration, **do not "fix" it by blindly removing conditions**; read the condition report first.

### 4.4. Matching Servlet vs. Reactive Model

- Servlet MVC uses `HttpSecurity` and `SecurityFilterChain` beans (`jakarta.servlet.Filter` via Spring Security's `FilterChainProxy`).
- WebFlux uses `ServerHttpSecurity` and `SecurityWebFilterChain` beans; defaults involve `ReactiveUserDetailsService`.
- These bean types **do not substitute for one another**. A servlet `SecurityFilterChain` does not cause WebFlux's default web protection to back off the same way.

If both `spring-boot-starter-web` and `spring-boot-starter-webflux` are accidentally added, Boot applies rules to pick an application type; verify the actual runtime type rather than guessing from one dependency.

### 4.5. Correct Chain Ordering and URL Scope

With multiple `SecurityFilterChain` beans, a bean's existence does not mean every request reaches it. `FilterChainProxy` selects the **first chain matching the request** in order; inside that chain, `requestMatchers` rules evaluate access.

If a chain is scoped to `/api/**`, it will not process `/admin/**` or `/login` when those paths do not match. You need another chain covering remaining paths, typically an `anyRequest()` fallback.

### 4.6. Beans Must Be Used by the Right Authentication Flow

A `PasswordEncoder` bean does not automatically enable database login if the app lacks a matching `UserDetailsService`/provider. A custom `AuthenticationProvider` is not guaranteed to run if you construct another `AuthenticationManager` without wiring that provider into it. Inspect the bean graph and runtime flow instead of counting `@Bean` methods in source code.

## 5. Java 17+ and Spring Boot 3.5 Example: Customizing Both Web Policy and User Store

The example below starts with Maven and needs no database. It shows **both custom bean groups**:

- `SecurityFilterChain` defining public, authenticated, and admin-required endpoints.
- `UserDetailsService` defining a custom test user so Boot does not generate a random `user`.
- `PasswordEncoder` encoding the in-memory test password.

The reference version is **Spring Boot 3.5.16** (Spring Security managed by the Boot BOM), JDK **17+**, and compatible Maven. Hardcoded accounts/passwords in code are strictly for **local practice**, never for production.

### 5.1. Creating the Project

Structure:

~~~text
auto-security-lab/
  pom.xml
  src/main/java/com/example/lab/AutoSecurityLabApplication.java
  src/main/java/com/example/lab/SecurityConfiguration.java
~~~

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
    <artifactId>auto-security-lab</artifactId>
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

The Security dependency declares no separate version; the Boot parent manages related modules.

File `src/main/java/com/example/lab/AutoSecurityLabApplication.java`:

~~~java
package com.example.lab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class AutoSecurityLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(AutoSecurityLabApplication.class, args);
    }

    @GetMapping("/public/ping")
    public String publicPing() {
        return "pong";
    }

    @GetMapping("/private/whoami")
    public String whoami(Authentication authentication) {
        return authentication.getName();
    }

    @GetMapping("/admin/secret")
    public String adminOnly() {
        return "admin-only";
    }
}
~~~

File `src/main/java/com/example/lab/SecurityConfiguration.java`:

~~~java
package com.example.lab;

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
    SecurityFilterChain appSecurity(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/public/**").permitAll()
                    .requestMatchers("/admin/**").hasRole("ADMIN")
                    .anyRequest().authenticated()
                )
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("learner")
                .password(encoder.encode("demo-password"))
                .roles("USER")
                .build()
        );
    }
}
~~~

What the code actually configures:

1. Spring Boot finds both classes because they share package `com.example.lab`; `@SpringBootApplication` triggers component scanning and auto-configuration.
2. Bean `appSecurity` has type `SecurityFilterChain`, so Boot drops its default web security chain and lets the app control rules.
3. Bean `users` has type `UserDetailsService`, so Boot drops its default `user` test account.
4. Bean `passwordEncoder` uses bcrypt for the test user.
5. `httpBasic` enables testing with `curl -u`; the app does not configure form login in this chain.
6. User `learner` only has `ROLE_USER`, so it **lacks** `ROLE_ADMIN`.

For real apps, never hardcode passwords, never store production users in an in-memory demo store, and implement proper account policies, sessions, auditing, and authentication mechanisms.

### 5.2. Running and Checking Responses

With JDK 17+, Maven, and access to Maven Central on first dependency download:

~~~bash
mvn -q -DskipTests package
mvn spring-boot:run
~~~

Keep the app running and open another terminal. In bash, run:

~~~bash
curl -s http://localhost:8080/public/ping
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/private/whoami
curl -s -u learner:demo-password http://localhost:8080/private/whoami
curl -s -u learner:demo-password -o /dev/null -w '%{http_code}\n' http://localhost:8080/admin/secret
~~~

Outputs of the four commands in order (one line per command):

~~~text
pong
401
learner
403
~~~

On Windows PowerShell, use `curl.exe` when needed to avoid the system `curl` alias. `-u learner:demo-password` is **strictly for local demos** and can remain in shell history; never use this with real passwords. You can use your IDE's HTTP client instead of putting secrets in shell commands.

Why these response codes?

- `/public/ping` matches `permitAll()` so 200 + body `pong`.
- `/private/whoami` lacks credentials, hits `authenticated()` and `httpBasic`, so normally 401.
- Same endpoint with valid `learner`: Spring Security supplies `Authentication` to the controller; `getName()` returns `learner`.
- `/admin/secret` with authenticated `learner` lacking `ROLE_ADMIN`, so 403.

The configuration and outputs above are **expected per the API logic in the example**; re-verify whenever you change ports, context paths, chains, entry points, or web stacks. Never assume every system returns the same response body for 401/403.

## 6. Experimenting by Changing One Bean to Observe Partial Back-Off

In the practice project above, you can run isolated experiments (change one piece at a time and restart).

| Experiment | Effect to Observe | Why |
| --- | --- | --- |
| Keep all three beans as-is | Custom rules and user `learner` take effect | Both default branches back off |
| Remove only the `users(...)` method | Boot may generate default `user` and random password | No custom `UserDetailsService`/alternative authentication |
| Keep `users(...)`, remove only `appSecurity(...)` | Boot may create the default web protection chain | No application-defined `SecurityFilterChain` |
| Add only `PasswordEncoder`, no custom user store | Does not create business users or custom rules | Encoder does not replace user store/authorization |
| Move `SecurityConfiguration` outside component scan without `@Import` | Custom configuration beans are not registered | Spring does not pick up that class in context |
| Add a chain matching only `/api/**` with no fallback | Paths outside `/api/**` may bypass Spring Security | No matching `SecurityFilterChain` for remaining URLs |

The table uses "may" for Boot defaults because classpath, properties, and other application beans also affect conditions. When experimenting, record **which beans were actually created** and the HTTP responses.

Note: **do not add `@EnableWebSecurity` by reflex** when Boot already integrates Spring Security. Many standalone Spring Security examples include that annotation; in Boot apps, understand why you need it before adding it. It does not substitute for placing `SecurityFilterChain` in a scanned package.

## 7. Multiple SecurityFilterChains: Having a Bean Does Not Mean Every URL Matches

If APIs and web pages need different login flows, use multiple chains:

~~~java
// Configuration fragment inside a @Configuration class of a servlet app.
@Bean
@Order(1)
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}

@Bean
@Order(2)
SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/**").permitAll()
            .anyRequest().authenticated()
        )
        .formLogin(Customizer.withDefaults())
        .build();
}
~~~

Additional imports include `org.springframework.core.annotation.Order`. This is an **illustrative configuration fragment**, not a complete standalone class with user providers.

How Spring Security selects:

~~~text
GET /api/orders
     |
     v
FilterChainProxy
     |
  @Order(1) securityMatcher("/api/**") ? -- Yes --> use apiSecurity
     |
     No
     v
  @Order(2) default matcher all requests ? -- Yes --> use webSecurity
     |
     No
     v
  No Spring Security chain matches request
~~~

**`securityMatcher` and `requestMatchers` have different jobs**:

- `http.securityMatcher("/api/**")` decides whether **the entire `SecurityFilterChain` applies** to a URL.
- `http.authorizeHttpRequests(...requestMatchers(...))` decides **access rules inside the selected chain**.
- `anyRequest()` in the first chain means only "every URL matched by the first chain"; it does not protect the entire site if `securityMatcher` narrowed its scope.

Spring Security picks the **first matching chain**, rather than merging filters from two chains into one. `@Order(1)` takes precedence over `@Order(2)`; order from specific conditions to general ones.

If you omit the second chain, `/public/ping` and `/admin/secret` fall outside `/api/**` and may bypass Spring Security altogether. That is a dangerous misconfiguration even when the API chain says `anyRequest().authenticated()`. Therefore you usually need a chain **without a restricted `securityMatcher`** as a fallback covering remaining paths.

A subtle case: `formLogin()` can register login processing endpoints such as `POST /login`. If you put form login inside a chain matching only `/api/**`, `/login` sits outside scope and is not served by that chain. Ensure the login URL falls within an appropriate chain or is covered by a dedicated chain.

## 8. When Actuator Is Present, Configure Management Endpoints Too

Spring Boot Actuator exposes endpoints such as `/actuator/health`, `/actuator/metrics`, `/actuator/beans`, and `/actuator/conditions`. Several contain sensitive operational data and **must not be publicly open**.

Common pitfall: **when the application supplies its own `SecurityFilterChain`, Boot's default Actuator protection may also back off**. Your rules must then cover Actuator as well. Never write only:

~~~java
// NOT enough to protect the whole app if scoped improperly.
.requestMatchers("/api/**").authenticated()
.anyRequest().permitAll()
~~~

That snippet permits all non-`/api/**` paths in the matching chain, which can include operational endpoints once exposed.

A safer design: decide explicitly which endpoints are exposed/permitted and use Boot's matchers such as `EndpointRequest` where appropriate. Configuration fragment:

~~~java
// Requires import: org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest
// Requires actuator dependency and matching servlet @Configuration.
http.authorizeHttpRequests(auth -> auth
        .requestMatchers(EndpointRequest.to("health")).permitAll()
        .requestMatchers(EndpointRequest.toAnyEndpoint()).hasRole("OPS")
        .anyRequest().authenticated());
~~~

**Note:** `EndpointRequest` is available only with the corresponding Actuator dependency; this is a fragment, not part of the basic demo project. A trusted source must grant `ROLE_OPS` if using this example.

An endpoint being **available/exposed** differs from being **permitted to access**. Spring Boot's Actuator settings control which endpoints are exposed over HTTP; Spring Security checks requests hitting exposed endpoints. Follow least privilege and protect `conditions`, `env`, and `beans` against unauthorized access.

## 9. How to Find Out Why Auto-Configuration Did or Did Not Take Effect

When behavior does not match expectations, gather **runtime evidence**.

### 9.1. Inspect the Condition Evaluation Report

Start Boot with `--debug`:

~~~bash
java -jar target/auto-security-lab-0.0.1-SNAPSHOT.jar --debug
~~~

Or with the Maven Boot plugin:

~~~bash
mvn spring-boot:run -Dspring-boot.run.arguments=--debug
~~~

Boot prints a *conditions report* when debug is enabled. Sections typically include:

| Report Section | Meaning |
| --- | --- |
| Positive matches | Configurations/branches whose conditions matched |
| Negative matches | Conditions that did not match, with reasons |
| Unconditional classes | Configuration classes without matching conditions |
| Exclusions | Configurations explicitly excluded |

Search for auto-configurations related to Security, `SecurityFilterChain`, `UserDetailsService`, or `@ConditionalOnMissingBean` branches. Many Boot versions show exact reasons such as finding an application-provided bean. Not seeing the random password log **is not enough** to conclude the default user does not exist: log levels and properties can suppress output.

When Actuator is installed and **properly protected**, the `conditions` endpoint also exposes configuration conditions. Never expose that endpoint publicly just for debugging.

### 9.2. Inspect Registered Beans

In tests, you can inspect bean names by type:

~~~java
// Diagnostic snippet inside an existing context/test.
String[] chains = context.getBeanNamesForType(SecurityFilterChain.class);
String[] users = context.getBeanNamesForType(UserDetailsService.class);
System.out.println("SecurityFilterChain beans: " + chains.length);
System.out.println("UserDetailsService beans: " + users.length);
~~~

Still, **counting beans does not prove correct behavior**. An app can have multiple chains in the wrong order, a chain missing protected URLs, or a provider bean registered without being wired into the active manager. Pair bean inspection with live request tests and authorization checks.

### 9.3. Enable Security Logging in a Controlled Way

To diagnose filter chains and request decisions in development:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Enable `TRACE` only when truly needed in a safe environment, then turn it off afterward. Security logs can reveal URLs and authentication state; never push sensitive debug logs to widely accessible locations.

### 9.4. Check Package Scanning, Profiles, and Dependencies

When you define `@Bean`s yet Boot still uses defaults, check sequentially:

1. Does the `@Configuration` class sit under the main application package or get `@Import`ed?
2. Is there a `@Profile` and is the expected profile active?
3. Did a `@Conditional...` evaluate to false?
4. Is another bean with the same name or type complicating resolution?
5. Is the app actually running Web MVC/Servlet or WebFlux?
6. Did the build recompile your latest code and run the right artifact/port?
7. Did `spring.autoconfigure.exclude` or `@SpringBootApplication(exclude=...)` exclude a relevant configuration?
8. What did the startup report say about which beans were created and why?

Do not "fix" issues by piling on `@EnableWebSecurity`, `@Order`, `@Primary`, or disabling CSRF without finding the real cause.

## 10. Non-MVC Case: WebFlux Uses Different Bean Types

For **reactive WebFlux** applications, Spring Security uses different types:

| Servlet/MVC | Reactive/WebFlux |
| --- | --- |
| `HttpSecurity` | `ServerHttpSecurity` |
| `SecurityFilterChain` | `SecurityWebFilterChain` |
| `UserDetailsService` | `ReactiveUserDetailsService` |
| Servlet `FilterChainProxy` | Reactive `WebFilterChainProxy` |
| `authorizeHttpRequests` | `authorizeExchange` |

Example **configuration fragment** for WebFlux, requiring reactive starters and dependencies:

~~~java
@Bean
SecurityWebFilterChain reactiveSecurity(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/public/**").permitAll()
            .anyExchange().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

Do not assume a servlet `SecurityFilterChain` makes WebFlux's default auto-configuration back off. Likewise, `ReactiveUserDetailsService` applies to the user source in reactive stacks. When both MVC and WebFlux appear on a build classpath, check which web application type Boot chose and follow its rules.

## 11. Common Reasoning Errors

1. **"Adding starter-security makes Boot block every URL forever."** Defaults can be replaced with a valid application `SecurityFilterChain`.
2. **"I declared a `SecurityFilterChain`, so the default `user` account is gone."** Not automatically; the user source is a separate auto-configuration branch.
3. **"I declared a `UserDetailsService`, so `/admin` is protected by role."** A user store does not create URL authorization policies; you still need a chain.
4. **"Creating a `PasswordEncoder` bean means database authentication works."** No; you still need a user source and provider/manager using the encoder.
5. **"Just creating `SecurityConfiguration.java` means Spring finds it."** It must be scanned/imported and its beans registered cleanly.
6. **"A chain with `anyRequest().authenticated()` protects the entire app."** Not if scoped by `securityMatcher("/api/**")` without a fallback chain.
7. **"Two `SecurityFilterChain` beans both run on every request."** No; `FilterChainProxy` selects the first matching chain.
8. **"`securityMatcher` and `requestMatchers` are the same."** One picks the chain; the other defines rules inside a chain.
9. **"Adding custom web rules does not affect Actuator."** Boot may back off its default protection; the app must protect management endpoints too.
10. **"`permitAll` disables all filters."** No; requests traversing the chain still encounter appropriate filters. `permitAll` affects only that rule's authorization decision.
11. **"The generated password log disappearing proves custom config took effect."** No; verify with beans/conditions report and HTTP requests.
12. **"Enabling `@EnableMethodSecurity` removes the need for URL and data checks."** Method security is an extra layer; verify call paths and access policies.
13. **"Disabling all auto-configuration is the best way to stay in control."** Usually unnecessary; override cleanly the exact parts the app wants to own.
14. **"Custom config turns off Spring Security."** False: it replaces only selected defaults and still requires sound protection policies.

## 12. Checklist for Deploying Custom Configuration Safely

Before considering your configuration verified, check:

- [ ] Spring Security dependency is on the classpath with a Boot-managed compatible version.
- [ ] Main app has `@SpringBootApplication` and `@Configuration` classes are scanned/imported.
- [ ] Beans return the right type: `SecurityFilterChain` (servlet) or `SecurityWebFilterChain` (reactive).
- [ ] Each protected URL group matches a chain, with a fallback for unmatched paths.
- [ ] Chains are ordered properly with `@Order`: specific chains first, general fallback last.
- [ ] `requestMatchers` rules match exact HTTP methods and protected resources.
- [ ] Appropriate `UserDetailsService`/provider/manager source is present; Boot's sample account is not used in production.
- [ ] `PasswordEncoder` is applied consistently to password data.
- [ ] Risky Actuator endpoints have restricted exposure and authorization.
- [ ] CSRF, sessions, CORS, login/logout, and headers fit the client types; never disabled arbitrarily due to a 403.
- [ ] Conditions report confirms which auto-configs matched, did not match, and why.
- [ ] Tested public, unauthenticated, authenticated-unauthorized, and authorized requests.
- [ ] Tested service call paths, method security, and data-level permissions if applicable.

## 13. Self-Check Knowledge Quiz

**Question 1.** You have `@Bean SecurityFilterChain`, yet the app still prints a random password for `user`. Did your custom configuration fail?

**Answer:** Not necessarily. The custom chain causes default web security to back off; the default user store is a separate branch. Add an appropriate user/provider/manager source if you want to replace it, and confirm conditions via the conditions report.

**Question 2.** You added `@Bean UserDetailsService`, yet `/public/ping` still requires login. Why?

**Answer:** Because the user store only changes how accounts are loaded; the default URL-protecting chain may still require authentication. To make `/public/**` public, define a matching `SecurityFilterChain`.

**Question 3.** A chain has `securityMatcher("/api/**")` and `anyRequest().authenticated()`. Why might `/billing` still lack Spring Security protection?

**Answer:** `/billing` does not match `securityMatcher`, so it never enters that chain; another chain is needed to cover it.

**Question 4.** Why might a `@Configuration` holding `@Bean SecurityFilterChain` outside component scanning fail to override defaults?

**Answer:** Spring does not register beans from unscanned/unimported configuration classes. Auto-configuration still sees no bean present and may register defaults.

**Question 5.** You define two chains with overlapping matchers, and `@Order` puts the broader chain first. What happens?

**Answer:** The broader chain can intercept requests before the specific chain, preventing the later chain's rules from ever applying. Order specific chains before the general fallback.

**Question 6.** Why should you not use `anyRequest().permitAll()` as a "quick fix" for a 403 when CSRF is enabled?

**Answer:** `permitAll` adjusts authorization, not CSRF token verification; it can also accidentally expose private data. Diagnose the real error across authentication, privileges, and CSRF.

**Question 7.** To know exactly why `UserDetailsServiceAutoConfiguration` did not create a bean, what should you inspect?

**Answer:** The conditions report (`--debug` or protected Actuator `conditions`) along with the bean list and dependency graph to see which condition failed to match.

**Question 8.** Can a servlet `SecurityFilterChain` bean replace a WebFlux `SecurityWebFilterChain`?

**Answer:** No. The two stacks have different mechanisms and bean types; declare the one matching your application stack.

## Official Documentation

- [Spring Boot 3.5 — Spring Security Auto-configuration](https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html)
- [Spring Boot 4 — Spring Security](https://docs.spring.io/spring-boot/reference/web/spring-security.html)
- [Spring Boot — Auto-configuration](https://docs.spring.io/spring-boot/reference/using/auto-configuration.html)
- [Spring Boot — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html)
- [Spring Boot — Conditions Endpoint](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Security — Java Configuration and Multiple Filter Chains](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html)
- [Spring Security — Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
