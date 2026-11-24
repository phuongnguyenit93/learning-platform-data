# Multiple SecurityFilterChains and the Meaning of @Order in Spring Security Servlet

## 1. When do you need multiple SecurityFilterChains?

A Spring Boot application using **Spring MVC/Servlet** may serve multiple HTTP endpoint groups with different security mechanisms. For example: `/api/**` is an API requiring HTTP Basic or a Bearer token; web pages use form login and sessions; `/admin/**` requires administrative permissions. When only **URL access permissions** differ, a single `SecurityFilterChain` with multiple `requestMatchers` is usually enough. When **filter sets, login mechanisms, session/CSRF/CORS, 401/302 error handling, or security scope** differ, multiple chains keep the configuration clear.

**Core rule:** Spring Security's `FilterChainProxy` selects the **first `SecurityFilterChain` that matches the request**, in priority order. A request does not run sequentially through all chains to accumulate permissions. The `@Order` annotation determines the **order in which chains are tried**; `securityMatcher` determines **which URLs a chain matches**; after a chain is selected, `requestMatchers` and `anyRequest` inside `authorizeHttpRequests` decide access permissions.

This lesson targets the **Servlet stack** with Spring Boot 3.x, Spring Security 6.x, `SecurityFilterChain`, and `HttpSecurity`. For Spring WebFlux, the mechanism is `SecurityWebFilterChain`/`ServerHttpSecurity`, and Servlet examples do not apply verbatim.

## 2. Architecture: from Servlet container to a SecurityFilterChain

~~~text
HTTP client
    |
    v
Tomcat / Servlet container
    |
    v
Servlet Filter chain (container-managed)
    |
    +-- DelegatingFilterProxy("springSecurityFilterChain")
           |
           v
       FilterChainProxy (Spring Security)
           |
           +-- try chain #1: @Order(1), securityMatcher("/api/**")
           |       if matched -> SELECT #1, do not try remaining chains
           |
           +-- try chain #2: @Order(2), securityMatcher("/admin/**")
           |       if matched -> SELECT #2, do not try further
           |
           +-- try chain #3: @Order(3), matches every request
                   if matched -> SELECT #3 (fallback)
           |
           v
       Security filters belonging to the SELECTED CHAIN
           -> authenticate / authorize per chain configuration
           -> allowed -> continue Servlet Filter chain
    |
    v
DispatcherServlet -> Controller -> Service -> Response
~~~

This is a conceptual diagram, not the exact order of every sub-filter in every version. Three kinds of "order" must be distinguished:

| Kind of order | Mechanism | Meaning |
| --- | --- | --- |
| **Servlet Filter** order | Filter registration with the Servlet container, Boot filter registration | Where `DelegatingFilterProxy` sits relative to other container filters |
| **SecurityFilterChain** order | `@Order`, `Ordered` on chain beans | Which chain `FilterChainProxy` tries first |
| **Security filter** order inside one chain | `HttpSecurity`, Spring Security configurations, filter positions | In what order authentication, context, authorization, exception translation, etc. run |

Inside one chain there is also the order of **authorization rules**: specific matcher rules must precede `anyRequest`. `@Order` does not replace this rule ordering.

**Chain selection example:** With #1 matching `/api/**`, #2 matching `/admin/**`, and #3 matching all URLs: `GET /api/me` uses #1; `GET /admin/users` uses #2; `GET /about` uses #3. If #1 rejects a request because the caller is not logged in, Spring Security **does not retry chain #2 or #3**.

## 3. What does @Order actually do?

Placed on a `SecurityFilterChain` bean:

~~~java
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
            .anyRequest().authenticated())
        .formLogin(Customizer.withDefaults())
        .build();
}
~~~

The two methods above **only illustrate configuration beans** and must be placed in a `@Configuration` class with appropriate imports. The complete project is in section 6.

Detailed rules:

1. **Lower @Order values are tried first.** `@Order(1)` takes precedence over `@Order(2)`. Method position in the file or method name does not decide this order.
2. **@Order does not decide which URLs are protected.** Each chain's `securityMatcher` defines its scope; a high-priority chain that does not match is skipped for that request.
3. **When two chains both match, the first one wins.** Filters of the first chain do not run and then hand off to the second chain because of a 401/403.
4. **Equal order causes ambiguity.** If matchers overlap, use distinct, explicit `@Order` values to avoid relying on bean registration order.
5. **Omitting @Order** typically places the bean near the end of the default order compared to `@Order(1)` and `@Order(2)`; when correctness depends on fallback priority, writing an explicit order helps readers and testers understand the design.
6. `@Order` **does not change sub-filter order**. If you want to add a custom authentication filter, study `http.addFilterBefore` / `addFilterAfter` and Spring Security's standard filter positions rather than controlling it with the chain bean's order.

`Ordered.HIGHEST_PRECEDENCE` is the smallest value and `Ordered.LOWEST_PRECEDENCE` is very large; there is no need for extreme values when `1`/`2`/`3` express the intent clearly.

A rule easy to remember: **@Order answers "which chain to try first?", not "what does that chain match?" or "which filter runs first inside the chain?"**

## 4. How is securityMatcher different from requestMatchers?

Example:

~~~java
http
    .securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/public").permitAll()
        .requestMatchers("/api/admin").hasRole("ADMIN")
        .anyRequest().authenticated()
    );
~~~

- `securityMatcher("/api/**")` is a **chain-level** matcher: which requests can enter this chain.
- `requestMatchers("/api/public").permitAll()` is an **authorization rule** for requests that already entered the chain. `permitAll` does not bypass all security filters.
- `requestMatchers("/api/admin").hasRole("ADMIN")` is another rule **within the same chain**.
- `anyRequest().authenticated()` applies to **every remaining request that already belongs to the chain**, rather than expanding `/api/**` to cover `/admin`, `/reports`, or `/login`.
- Without calling `securityMatcher(...)`, a `SecurityFilterChain` defaults to a matcher covering **every request**, making it well suited as a final fallback chain.

`authorizeHttpRequests` configuration is evaluated in the order rules are declared. Put specific rules before `anyRequest`; avoid thinking `anyRequest` can be written first while later rules still get a chance to run.

In a Spring MVC environment, matchers created by string-taking overloads may rely on MVC matching components. Do not assume they are always Ant matchers. If an application has a custom context path, custom servlet path, or multiple servlets, inspect the request matcher and how it interprets paths. Never use client-supplied headers or paths as proof of access permission.

### Two independent decision layers

~~~text
securityMatcher() -> does this chain apply to the request?
    |
    +-- No  -> try the next SecurityFilterChain
    |
    +-- Yes -> select chain; run the chain's filters
                    |
                    v
            authorizeHttpRequests()
                    |
                    +-- specific requestMatchers
                    +-- anyRequest for the remainder
                    |
                    v
            Allow or deny
~~~

A request denied at the authorization step of the selected chain **does not go back** to chain selection to look for an "easier" option.

## 5. Chain ordering and overlapping matcher scenarios

Suppose there are three chains:

| Chain | @Order | securityMatcher | Policy description |
| --- | --- | --- | --- |
| API | 1 | `/api/**` | `/api/public` public, `/api/admin` ADMIN; other API authenticated |
| Admin | 2 | `/admin/**` | All require ADMIN |
| Web | 3 | Every request | `/public` public, rest authenticated |

| Request | Selected chain | Explanation |
| --- | --- | --- |
| `GET /api/public` | API | Matches chain #1 immediately |
| `GET /api/admin` | API | ADMIN permission is checked **inside the API chain** |
| `GET /admin/users` | Admin | API does not match, Admin matches |
| `GET /public` | Web | First two chains do not match |
| `GET /reports` | Web | Fallback catches all remaining URLs |

The table above only identifies the chain; **it does not assert the HTTP status**. Status depends on identity, roles, login mechanism, CSRF, CORS, MVC, and exception handlers.

### Shadowing bug: an overly broad chain placed first

~~~java
@Bean
@Order(1)
SecurityFilterChain catchAll(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}

@Bean
@Order(2)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().hasRole("API_USER"))
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

This snippet **illustrates a bug** and lacks standalone class/imports. The `catchAll` chain matches every request by default and is tried first, so it receives every `/api/**` request. The `api` chain at order 2 never gets a chance to enforce `hasRole("API_USER")`.

**Fix:** place narrow chains before broad chains; for instance `@Order(1)` for `securityMatcher("/api/**")` and `@Order(2)` for the fallback. Spring recognizing `/api/**` as "more specific" **does not automatically** make it win: only the configured evaluation order decides.

### Two matching chains do not combine permissions

Suppose the first chain requires `ROLE_USER` and the second chain requires `ROLE_ADMIN` for the same `/api/admin/**`. Users **do not automatically have to hold both roles**. Only the selected chain's policy takes effect. If business logic requires multiple conditions, put them in the selected chain's authorization policy or use method security/service-layer checks rather than relying on two chains running back-to-back.

## 6. Complete example: API with HTTP Basic, web with form login

Goal of the runnable example:

- API chain `@Order(1)` matches only `/api/**`, using HTTP Basic.
- Web chain `@Order(2)` sets no `securityMatcher`, so it acts as fallback; uses form login.
- Both chains share an in-memory `UserDetailsService` with users `alice` (USER) and `admin` (ADMIN).
- `/api/public` and `/public` are public. `/api/admin` and `/admin` require ADMIN. Remaining URLs require login.

The application uses **Java 17+**, Spring Boot 3.3.x, Spring Security 6.x, and Spring MVC. Passwords in the example are solely for local practice and are hashed with BCrypt at startup. Real applications need proper identity sources, secret management, and HTTPS.

### 6.1. Structure

~~~text
security-multiple-chains/
├── pom.xml
└── src/main/java/com/example/multichain/
    ├── MultipleChainsApplication.java
    ├── SecurityConfig.java
    └── DemoController.java
~~~

**`pom.xml`**

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
    <artifactId>security-multiple-chains</artifactId>
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

**`src/main/java/com/example/multichain/MultipleChainsApplication.java`**

~~~java
package com.example.multichain;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MultipleChainsApplication {

    public static void main(String[] args) {
        SpringApplication.run(MultipleChainsApplication.class, args);
    }
}
~~~

**`src/main/java/com/example/multichain/SecurityConfig.java`**

~~~java
package com.example.multichain;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiSecurityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public").permitAll()
                .requestMatchers("/api/admin").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webSecurityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            // No securityMatcher set: fallback for the remaining URLs.
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public", "/login").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .build();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("demo-pass"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("demo-pass"))
                .roles("ADMIN")
                .build()
        );
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }
}
~~~

**`src/main/java/com/example/multichain/DemoController.java`**

~~~java
package com.example.multichain;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/api/public")
    public String apiPublic() {
        return "api public";
    }

    @GetMapping("/api/me")
    public String apiMe(Authentication authentication) {
        return "api hello " + authentication.getName();
    }

    @GetMapping("/api/admin")
    public String apiAdmin() {
        return "api admin";
    }

    @GetMapping("/public")
    public String webPublic() {
        return "web public";
    }

    @GetMapping("/me")
    public String webMe(Authentication authentication) {
        return "web hello " + authentication.getName();
    }

    @GetMapping("/admin")
    public String webAdmin() {
        return "web admin";
    }
}
~~~

### 6.2. Explaining the configuration

- Two `SecurityFilterChain` beans are registered at startup. Boot typically **does not create an extra default HTTP security chain** once the application supplies its own chains; you must cover the URLs needing protection yourself.
- The API chain has matcher `/api/**` and order 1. The HTTP Basic filter processes credentials appropriately for API requests; the `hasRole("ADMIN")` rule requires the `ROLE_ADMIN` authority.
- The web chain at order 2 is tried when API does not match. It enables form login and can generate the default `/login` page. Basic is not enabled in the web chain.
- Both chains share the `UserDetailsService`. Sharing a user store **does not mean** the login mechanisms or entry points in the two chains are the same.
- `permitAll` for `/api/public` or `/public` still lets requests flow through the selected chain, while removing the login requirement in that authorization rule.
- The example **keeps default CSRF configuration**. The endpoints only illustrate HTTP GET. For state-changing requests, evaluate CSRF based on how clients send credentials instead of disabling CSRF globally merely because the path is an API.

### 6.3. Running and verifying with curl

From the directory containing `pom.xml`, using Maven and JDK 17+:

~~~bash
mvn spring-boot:run
~~~

When downloading dependencies for the first time, Maven requires network access. By default the server runs on `http://localhost:8080`. In Windows PowerShell you can use `curl.exe` if `curl` is aliased to another command.

Lines starting with `#` below are **expected results** when running the demo project properly; they are not output directly measured in the current environment.

~~~bash
curl -s http://localhost:8080/api/public
# api public

curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/api/me
# 401

curl -s -u alice:demo-pass http://localhost:8080/api/me
# api hello alice

curl -s -o /dev/null -w '%{http_code}\n' -u alice:demo-pass http://localhost:8080/api/admin
# 403

curl -s -u admin:demo-pass http://localhost:8080/api/admin
# api admin

curl -s http://localhost:8080/public
# web public

curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/me
# 302

curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/login
# 200

curl -s -o /dev/null -w '%{http_code}\n' -u alice:demo-pass http://localhost:8080/me
# 302
~~~

Interpretation:

| Request | Chain | Result and reason |
| --- | --- | --- |
| `/api/public` unauthenticated | API | 200, `permitAll` |
| `/api/me` unauthenticated | API | 401, HTTP Basic entry point |
| `/api/me` with alice Basic | API | 200, `api hello alice` |
| `/api/admin` with alice Basic | API | 403, missing ADMIN role |
| `/api/admin` with admin Basic | API | 200, `api admin` |
| `/public` unauthenticated | Web | 200, `permitAll` |
| `/me` unauthenticated | Web | 302, redirect to form login |
| `/login` unauthenticated | Web | 200, default login page |
| `/me` with Basic header but no web session | Web | 302, because the web chain does not enable HTTP Basic |

This is worth observing: **a Basic header does not make the fallback web chain automatically activate `BasicAuthenticationFilter`**. To access `/me` through real form login, a client must complete the proper login POST, send the CSRF token, and keep the cookie/session. A browser makes observing this flow much easier.

When `/api/me` returns 401, the API chain has already been selected and rejected the request; **there is no fallback to the form login chain**. When `/api/admin` returns 403 due to role, there is likewise no second attempt on the web chain.

## 7. What if there is no fallback chain?

Suppose an application only has:

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

The snippet above is not a standalone Java file; it must be placed in a configuration class with appropriate imports. It only covers `/api/**`. If `GET /admin` **matches no chain**, `FilterChainProxy` does not run a Spring Security filter chain for that request; the request may proceed straight to MVC. If the `/admin` controller has no other protection layer, that is a security vulnerability.

**Do not expect Boot to automatically add a default chain** once you have supplied a `SecurityFilterChain` bean. In standard Spring Boot Servlet setups, auto-configuration for the default HTTP chain backs off when the application defines its own chain. Proactively add a fallback chain protecting all remaining URLs when appropriate.

A strict option is a **deny-by-default** fallback:

~~~java
@Bean
@Order(99)
SecurityFilterChain denyUnlisted(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().denyAll())
        .build();
}
~~~

This is also a standalone conceptual snippet; **do not** place it alongside the web fallback in the complete example without redesigning the order. It denies every request that did not enter an earlier chain, including login pages or assets if not permitted in an earlier chain. Web applications may need an `authenticated()` fallback plus explicit public rules; choose based on requirements and make sure to check login, error, static files, and Actuator.

### permitAll differs from having no matching chain

`requestMatchers("/public").permitAll()` **still** lets Spring Security process the request inside the selected chain, so relevant filters/headers still apply. If a request matches no `SecurityFilterChain`, or is excluded from Spring Security via `web.ignoring()`, behavior differs significantly. For typical public URLs, `permitAll` is generally better than bypassing all of Spring Security.

## 8. When matchers overlap: put the specific chain first

Scenario:

~~~text
Chain A: @Order(1), securityMatcher("/api/**")
Chain B: @Order(2), securityMatcher("/api/admin/**")
~~~

`GET /api/admin/users` matches both, yet **A wins** because it is evaluated first. If you want the admin API to use distinct filters, reverse the priority:

~~~text
Chain Admin:    @Order(1), securityMatcher("/api/admin/**")
Chain API:      @Order(2), securityMatcher("/api/**")
Chain Fallback: @Order(3), matches every URL
~~~

Spring Security **does not** automatically know that a more specific matcher has higher priority. `@Order` expresses the developer's design decision.

A URL `/api/orders` that does not match the Admin chain will next be tried against the API chain and select API. The `anyRequest` rule inside the Admin chain is **not** evaluated if the Admin chain's matcher does not match.

### Do not use multiple chains to combine permissions

If you require both `ROLE_USER` and `ROLE_ADMIN`, do not create two chains matching the same URL expecting both rules to apply. Place the appropriate permission logic **inside the selected chain**, or add method security at the service layer. Likewise, protecting per-record ownership (IDOR/BOLA) typically requires checks at the business layer; `@Order` does not solve data-level authorization.

### Complex chain matching

You can use a custom `RequestMatcher` to inspect method, host, or headers. When doing so, consider reverse proxies, client-supplied data, and how the matcher operates. Never treat a spoofable header as proof of a role. With custom servlet paths or context paths, determine the exact URL scope the matcher actually receives.

## 9. Configurations that are per-chain

**Authentication mechanism:** An API chain can enable HTTP Basic, OAuth2 Resource Server bearer tokens, or a custom filter; a web chain enables form login. When a request matches a chain, only that chain's authentication filters operate. `AuthenticationManager` or `AuthenticationProvider` can be shared or separated depending on the configuration; `@Order` does not by itself separate identities.

**CSRF:** Each chain has its own CSRF configuration. In browsers using cookies/sessions, state-changing requests need care. APIs using only client-supplied tokens have a different CSRF model, yet **you should not disable CSRF merely because a URL starts with /api**; HTTP Basic credentials cached by browsers can be sent automatically.

**CORS:** Browser preflight `OPTIONS` requests may carry no credentials. CORS should be processed before authorization rejects preflight; with Spring Security, integrate CORS configuration into the chains that need it. CORS is not an authentication mechanism and does not stop non-browser clients from calling the API.

**Session/security context:** A token API can use `SessionCreationPolicy.STATELESS`; web form login uses sessions. Splitting into multiple chains **does not automatically create** two independent identity systems or cookies. Check how the security context, session cookie, and authentication repository are stored and read in the actual configuration.

**Login/logout URLs:** If a chain matches only `/secured/**` while form login still processes `/login`, the login URL may sit **outside the scope** of the chain that owns the form-login filter. Ensure the login page and login processing URL match the intended chain, are permitted when appropriate, and are not captured by an earlier chain.

**Security headers:** Endpoints passing through a chain receive that chain's configured filters/headers. URLs matching no chain will not receive security headers provided by a Spring Security chain. That is why fallbacks must be reviewed and overly broad `web.ignoring()` avoided.

**Actuator:** When the application supplies its own chains, actively check exposed management endpoints such as health, metrics, info, and their access policies. Do not assume an auto-configured fallback exists for every management URL.

**Method security:** `@EnableMethodSecurity` and `@PreAuthorize` check permissions at the method/service level; this is a complementary mechanism. It **does not** alter `FilterChainProxy` chain selection. Once a request passes HTTP authorization, you still need owner/tenant/domain-object checks if policy requires them.

## 10. Debugging and verifying chains in practice

### Enabling Spring Security logging in development

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

You can use `TRACE` for very detailed analysis, but never enable sensitive logging in production. When reading logs, look for request path/method, selected security chain, authentication filters, entry point, access denied handler, and authorization decisions. Do not depend on a fixed log line format because formatting changes across versions.

### Distinguishing startup conditions from request-time behavior

To see whether Boot creates its default chain, enable Boot debug mode:

~~~bash
mvn spring-boot:run -Dspring-boot.run.arguments=--debug
~~~

The **Condition Evaluation Report** explains why auto-configurations were applied or skipped. However, it is not enough to prove which chain `GET /api/orders` entered. To know which chain a request enters, check matchers, order, and HTTP logs/tests.

A "generated security password" message, if present, only relates to the **default user** branch; it does not prove the default HTTP chain is running. Custom `SecurityFilterChain` beans can coexist with the default user if the application has not yet supplied its own identity source.

### Testing map you need

When changing multiple chains, test in this order:

1. A URL guaranteed to match only the **specific chain**.
2. A URL lying in the **overlap** of two matchers.
3. A URL matching only a more general chain.
4. A URL **outside specific matchers** that must be protected by the fallback.
5. Login page/processing URL, `/error`, static assets, and required Actuator endpoints.
6. Each URL with anonymous, regular user, admin, valid/invalid credentials.
7. If using POST/PUT/DELETE, test CSRF and CORS/preflight for the exact client type.

Observe responses: **401** usually indicates missing authentication; **403** usually indicates access denied or CSRF; **302** can be a redirect to login. However, status codes are determined by configured entry points/handlers, so **do not deduce the chain solely from status codes**. Confirm using matchers and logs.

A sensible diagnostic flow:

~~~text
Actual HTTP request
 -> securityMatcher + @Order
 -> first matching chain
 -> authentication filter (right mechanism?)
 -> authorizeHttpRequests rule (matched and sufficient permissions?)
 -> DispatcherServlet / Controller / Service
 -> response / exception handling
~~~

## 11. Common mistakes

| Misconception | Accurate understanding |
| --- | --- |
| "`@Order(1)` protects every URL before other chains." | It is only selected when its **chain-level matcher matches** |
| "Requests run through all `SecurityFilterChain`s." | `FilterChainProxy` selects the **first matching chain** |
| "Using `requestMatchers("/api/**")` limits the chain to the API." | That is an **authorization rule**; `securityMatcher("/api/**")` limits the chain |
| "`anyRequest().authenticated()` in the API chain protects the whole website." | It applies only to requests **already belonging to the API chain** |
| "A narrow chain automatically beats a broad chain." | Selection order is decided by `@Order` |
| "If no chain matches, Boot creates a fallback." | Do not count on it; custom chains usually cause Boot's default HTTP chain to back off |
| "`@Order` makes `BasicAuthenticationFilter` run earlier." | Filter order **inside a chain** is a separate mechanism |
| "`permitAll` turns off Spring Security for the endpoint." | It still traverses the matched chain and security filters |
| "Sharing `UserDetailsService` means both chains automatically support Basic." | Each chain only has the authentication mechanisms enabled on it |
| "Having `@PreAuthorize` means HTTP chains don't need to be distinguished." | Method security and HTTP security have different responsibilities |

**Scenario to fix:** An app configures `@Order(1)` on a chain without `securityMatcher` using `anyRequest().permitAll()`, and then `@Order(2)` for `securityMatcher("/admin/**")` with `hasRole("ADMIN")`. `/admin/users` matches the first chain and **does not receive** the second chain's ADMIN rule. Fix it by putting the admin chain first, redesigning the fallback, and opening only genuinely public URLs. Only editing `hasRole` on the second chain without fixing shadowing will do nothing.

## 12. Self-check questions

**1.** There is an `@Order(1)` chain matching `/api/**` and an `@Order(2)` chain matching `/admin/**`. Which chain does `GET /admin/jobs` belong to?

**Answer:** The `/admin/**` chain, because the first chain does not match despite having higher priority.

**2.** `GET /api/me` returns 401 in the API chain. Does it automatically fall back to the web chain?

**Answer:** No. Chains are selected by matcher; authentication/authorization failure does not cause Spring Security to try the next chain.

**3.** Why doesn't `anyRequest().authenticated()` inside `securityMatcher("/api/**")` protect `/reports`?

**Answer:** `/reports` is not selected into the API chain. `anyRequest` only covers requests already within that chain's scope.

**4.** Two chains match `/api/admin/**`. How do you make the admin chain use separate filters with higher priority?

**Answer:** Place the narrow chain for `/api/admin/**` with a smaller `@Order` than the `/api/**` chain, test the overlap region, and keep an appropriate fallback.

**5.** Does `@Order` change the position of `AuthorizationFilter` relative to `BasicAuthenticationFilter`?

**Answer:** No. It orders the chain beans; sub-filter order is determined by Spring Security/`HttpSecurity`.

**6.** Why does a Basic header sent to `/me` still redirect 302 in the demo?

**Answer:** `/me` belongs to the web chain, which only has form login; HTTP Basic is only enabled in the API chain.

**7.** If an app declares only one chain matching `/api/**`, is `/admin` blocked by default?

**Answer:** You cannot conclude that. If no other chain matches, `/admin` may proceed without passing through any Spring Security filter chain. An explicitly designed and tested fallback or protection measure is required.

**Key takeaway:** **`@Order` chooses chain evaluation order; `securityMatcher` decides whether a chain matches a request; `requestMatchers` and `anyRequest` decide permissions inside the selected chain. Each request uses the first matching chain.**