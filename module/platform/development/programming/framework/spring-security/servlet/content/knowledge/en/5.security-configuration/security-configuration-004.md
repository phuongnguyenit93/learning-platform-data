# Fallback Chains to Protect Paths Not Covered by Other Chains

> **Scope:** Spring Security 6 on the **Servlet stack** (Spring Boot 3.x, Spring MVC, Java 17+). This lesson belongs to **Security Configuration** and explains how to design a **fallback/catch-all `SecurityFilterChain`** so requests that do not match specialized chains still receive a clear protection policy. This is Servlet HTTP security chain selection; Spring WebFlux has its own `SecurityWebFilterChain` mechanism.

## 1. Problem: new paths can accidentally sit outside every security chain

An application may split its configuration into multiple `SecurityFilterChain`s: one chain for `/api/**`, one for admin paths, one for the web UI, and so on. Splitting is useful because each group can have different authentication, sessions, CSRF, or error handling.

However, if **no chain matches** a request, `FilterChainProxy` does not run the security filters of those chains for that request; the call can continue to the servlet/controller. Consequently, a new path like `/reports` might **not require login** as the developer assumed, even though multiple `SecurityFilterChain` beans exist in the project.

Example configuration with insufficient coverage:

```java
// RISK ILLUSTRATION SNIPPET: only one chain, not a complete configuration.
@Bean
@Order(1)
SecurityFilterChain apiOnly(HttpSecurity http) throws Exception {
    return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                    .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
}
```

Suppose this is the **only chain** and the application has a `GET /reports` controller. This chain only evaluates requests matching `/api/**`; `/reports` does not match, so it does not pass through the security filters provided by this chain. In standard Spring Boot, once you declare a custom `SecurityFilterChain` bean, Boot's default chain does not automatically appear as an extra safety net. Without another protection mechanism, `GET /reports` can become unintentionally public.

**Goal of a fallback:** place a final chain whose scope covers remaining requests and whose default policy is deliberately chosen, typically `anyRequest().authenticated()`.

## 2. How does FilterChainProxy select a security chain?

On the Servlet stack, the container typically invokes `DelegatingFilterProxy`, pointing to the Spring bean `springSecurityFilterChain` (typically `FilterChainProxy`). When a request arrives, `FilterChainProxy` iterates through the ordered list of `SecurityFilterChain`s and picks the **first chain whose `RequestMatcher` matches**.

```text
HTTP GET /reports
    |
    v
Servlet container -> DelegatingFilterProxy -> FilterChainProxy
                                             |
                                             v
                           SecurityFilterChain @Order(1)
                           securityMatcher("/api/**")
                           match? NO
                                             |
                                             v
                           SecurityFilterChain @Order(2)
                           securityMatcher("/admin/**")
                           match? NO
                                             |
                                             v
                           Fallback SecurityFilterChain @Order(3)
                           matches every request by default
                           match? YES
                                             |
                                             v
                           fallback security filters
                           -> authenticate / authorize
                           -> allow onward or return error
```

There are three foundational rules:

1. **First match wins.** Only the first matching chain is selected; filters from other chains are not automatically appended to the running chain.
2. **`securityMatcher(...)` defines the scope of the entire chain.** Inside a chain, `requestMatchers(...)` under `authorizeHttpRequests` define permissions for each request that chain accepts.
3. **The fallback chain must match all remaining requests and come after specialized chains.** You can omit `securityMatcher(...)` on the fallback because the default matcher of a standard `HttpSecurity` matches every request. When explicitness is needed, `AnyRequestMatcher.INSTANCE` can be used; never accidentally restrict the fallback to `/web/**` or `/api/**`.

Table distinguishing three decisions:

| Question | Where configured | Meaning |
| --- | --- | --- |
| Which chain receives `/reports`? | `@Order` on `SecurityFilterChain` beans and `http.securityMatcher(...)` | Selecting **one** chain |
| Within the chosen chain, what is `/reports` allowed to do? | `authorizeHttpRequests` with `requestMatchers` and `anyRequest` | Authorization rules |
| Does a denied request produce 401, 403, or redirect? | Entry point, authentication mechanism, and exception handling of the selected chain | How unauthenticated/unauthorized calls respond |

An `.anyRequest().authenticated()` statement **inside** a chain covers only requests **already selected by that chain**; it does not expand the chain's `securityMatcher` to the entire application.

## 3. Proper fallback configuration pattern

A simple pattern with one specialized API chain and one final chain:

```java
@Configuration
public class SecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/api/**")
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/public").permitAll()
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
        return http
                // No securityMatcher set: this chain matches every request by default.
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public").permitAll()
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
```

This is an **illustrative configuration snippet**; it must be placed in a Spring Boot/Spring Security project with imports for `@Configuration`, `@Bean`, `@Order`, `SecurityFilterChain`, `HttpSecurity`, and `Customizer`. Section 5 below provides the complete runnable file set.

In this configuration:

- `GET /api/public` → selects API chain → allowed without login via `permitAll()`.
- `GET /api/orders` → selects API chain → requires authentication.
- `GET /public` → does not match `/api/**` → selects fallback → allowed without login.
- `GET /reports` → does not match API → selects fallback → requires authentication, even if this path was just added to the application.

Having `@Order(1)` before `@Order(2)` is essential. **Do not place the match-all chain before the API chain**: if the fallback comes first, it captures all requests and the API chain is never used, losing specialized configurations such as API session, CORS, CSRF, or authorization rules.

### When more chains are needed

For example, the following order suits separated scopes:

```text
@Order(10) -> securityMatcher("/api/**")       -> API policy
@Order(20) -> securityMatcher("/admin/**")     -> admin policy
@Order(90) -> no securityMatcher declared      -> fallback for the rest
```

The `@Order` number is strictly evaluation priority, not security strength: **smaller values have higher priority**. Assign explicit values to chains to avoid opaque ordering when multiple beans coexist.

Never give a fallback a specialized matcher like `securityMatcher("/home/**")` and treat it as a catch-all. If writing an explicit matcher, you can use:

```java
http.securityMatcher(
        org.springframework.security.web.util.matcher.AnyRequestMatcher.INSTANCE
);
```

The snippet above only shows how to set the matcher; usually **omitting `securityMatcher` in the fallback is easier to read**.

## 4. Choosing a default policy: authenticated, denyAll, or permitAll?

**Choosing a fallback policy is a security decision**, not merely an ordering technique.

| Fallback policy | Result | When to consider |
| --- | --- | --- |
| `anyRequest().authenticated()` | Remaining requests must carry a valid identity | Common for apps with internal endpoints requiring login |
| `anyRequest().denyAll()` | Rejects all requests without an explicit allow rule | Environments requiring **fail closed** and review of new endpoints |
| `anyRequest().permitAll()` | Allows requests not matched by earlier chains | Only suitable if **intentionally** making everything else public; not a safe default |

`authenticated()` verifies the caller has an identity, **and does not itself check business permissions**. If `/admin` is only for administrators, the fallback can add `requestMatchers("/admin/**").hasRole("ADMIN")` **before** `anyRequest().authenticated()`, or separate out an admin chain. Do not treat "logged in" as "allowed to perform any operation".

`denyAll()` is useful if you want new endpoints to work only once explicitly declared. When using it, ensure legitimate endpoints such as `/login`, health checks, static resources, callbacks, or error pages are properly handled by an appropriate chain or intentional allow rules. Any `permitAll()` exception should be as specific as possible.

**Easy to confuse:** `permitAll()` inside `authorizeHttpRequests` still sends the request through the matching security filter chain. By contrast, `web.ignoring()` excludes URLs from normal security filter processing and can create unprotected zones; prefer `permitAll()` when you need public endpoints while still wanting security headers or shared mechanisms.

## 5. Runnable Java 17+ project and automated tests

The example uses **Spring Boot 3.3.5 / Spring Security 6.x / Java 17 / Gradle 8.5**. It has two chains and a concrete set of endpoints. The goal is to prove that **even paths without a controller yet must be checked by the fallback before returning 404**.

### 5.1. Project structure

```text
fallback-chain-demo/
  settings.gradle
  build.gradle
  src/main/java/demo/
    DemoApplication.java
    SecurityConfig.java
    DemoController.java
  src/test/java/demo/
    SecurityConfigTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'fallback-chain-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

### 5.2. Startup class

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

### 5.3. Two SecurityFilterChains and demo account

`src/main/java/demo/SecurityConfig.java`:

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/api/**")
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/public").permitAll()
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
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails learner = User.withUsername("learner")
                .password(encoder.encode("study123"))
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(learner);
    }
}
```

The `learner / study123` account is local study data for running `curl` and tests. The password is hashed with BCrypt before being stored in `InMemoryUserDetailsManager`. In real applications, do not hardcode accounts/passwords in source code, and use HTTPS for HTTP Basic.

Key point to observe: **the fallback has no `securityMatcher(...)`**, only `authorizeHttpRequests`. Thus it matches requests remaining after the API chain, then requires authentication except for `/public`. Both chains use HTTP Basic so 401 results are easy to verify; real applications can choose different authentication mechanisms per chain.

### 5.4. Controller

`src/main/java/demo/DemoController.java`:

```java
package demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/api/public")
    public String apiPublic() {
        return "api-public";
    }

    @GetMapping("/api/orders")
    public String apiOrders() {
        return "api-orders";
    }

    @GetMapping("/public")
    public String publicPage() {
        return "public";
    }

    @GetMapping("/admin")
    public String adminPage() {
        return "admin";
    }
}
```

There is no handler for `/future/feature`. We use that URL to verify that the fallback protects even paths not yet implemented.

### 5.5. Testing Spring Security with MockMvc

`src/test/java/demo/SecurityConfigTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityConfigTest {

    @Autowired
    MockMvc mvc;

    @Test
    void explicitPublicEndpointsAllowAnonymous() throws Exception {
        mvc.perform(get("/api/public"))
                .andExpect(status().isOk())
                .andExpect(content().string("api-public"));
        mvc.perform(get("/public"))
                .andExpect(status().isOk())
                .andExpect(content().string("public"));
    }

    @Test
    void apiChainRejectsAnonymousCaller() throws Exception {
        mvc.perform(get("/api/orders"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void fallbackRejectsAnonymousCaller() throws Exception {
        mvc.perform(get("/admin"))
                .andExpect(status().isUnauthorized());
        mvc.perform(get("/future/feature"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void validBasicCredentialsReachProtectedControllers() throws Exception {
        mvc.perform(get("/api/orders").with(httpBasic("learner", "study123")))
                .andExpect(status().isOk())
                .andExpect(content().string("api-orders"));
        mvc.perform(get("/admin").with(httpBasic("learner", "study123")))
                .andExpect(status().isOk())
                .andExpect(content().string("admin"));
    }

    @Test
    void authenticatedRequestToUnknownPathBecomesNotFound() throws Exception {
        mvc.perform(get("/future/feature").with(httpBasic("learner", "study123")))
                .andExpect(status().isNotFound());
    }
}
```

The most important test is `fallbackRejectsAnonymousCaller()`: `/future/feature` **does not yet exist in any controller**, yet an unauthenticated request still receives **401** because the fallback runs before Spring MVC. When authentication succeeds, the request is allowed through to MVC and only then receives **404** because no handler is found. Actual status codes may differ if an application configures custom exception handling, login redirects, or a reverse proxy in front; here we use the HTTP Basic setup shown.

### 5.6. Running the project and observing

Install JDK 17+ and a compatible Gradle (for example Gradle 8.5). In the project directory, run:

```bash
gradle test
gradle bootRun
```

If the project has a Gradle wrapper, replace `gradle` with `./gradlew` (Linux/macOS) or `.\gradlew.bat` (Windows).

From another terminal:

```bash
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/orders
curl -i http://localhost:8080/public
curl -i http://localhost:8080/admin
curl -i http://localhost:8080/future/feature
curl -i -u learner:study123 http://localhost:8080/api/orders
curl -i -u learner:study123 http://localhost:8080/admin
curl -i -u learner:study123 http://localhost:8080/future/feature
```

Expected results **with the demo configuration** (ignoring server-generated HTTP headers, considering only status/body):

| Request | Selected chain | HTTP status | Body when 200 |
| --- | --- | --- | --- |
| `GET /api/public`, anonymous | API | **200** | `api-public` |
| `GET /api/orders`, anonymous | API | **401** | — |
| `GET /public`, anonymous | Fallback | **200** | `public` |
| `GET /admin`, anonymous | Fallback | **401** | — |
| `GET /future/feature`, anonymous | Fallback | **401** | — |
| `GET /api/orders`, valid Basic | API | **200** | `api-orders` |
| `GET /admin`, valid Basic | Fallback | **200** | `admin` |
| `GET /future/feature`, valid Basic | Fallback | **404** | — |

**Do not use a 404 on a controller-less URL to conclude it is protected.** Always check the **unauthenticated** case first; when the fallback requires authentication and no credentials are supplied, security handles it before MVC decides whether a handler exists.

## 6. Misconfigurations that easily create vulnerabilities

### 6.1. Assuming API's `anyRequest().authenticated()` protects the entire app

```java
http.securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated());
```

`anyRequest` applies **only within `/api/**`** of that chain. It does not protect `/admin` or `/orders` if no other chain covers them. The solution is to add a match-all fallback chain after specialized chains.

### 6.2. Placing the fallback at higher priority than the API

```text
WRONG:
@Order(1) -> fallback (matches all)
@Order(2) -> API (matches /api/**, but is never selected)
```

This can route API requests through the web/fallback policy and drop API-specific restrictions. Solution: place specialized chains first and the fallback last; prove the order with tests for each URL group.

### 6.3. Calling a `/web/**` chain a "fallback"

```java
// This is only a dedicated chain for /web/**, NOT a catch-all.
http.securityMatcher("/web/**")
    .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated());
```

`/reports` does not match `/web/**`. If a fallback is needed, let the final chain match every request or use a matcher that truly covers the full intended scope.

### 6.4. Permitting the entire fallback because "we don't know what this URL is"

```java
// Caution: opens every URL not matched by a previous chain.
.authorizeHttpRequests(auth -> auth.anyRequest().permitAll())
```

This is not a "protective fallback". It makes new URLs public by default. When the requirement is to protect paths not covered by other chains, choose `authenticated()` or `denyAll()` depending on policy.

### 6.5. Losing access to public, login, or error endpoints

A fallback requiring authentication by default can accidentally lock `/login`, CSS/JS assets, health endpoints, or callbacks. Explicitly decide which URLs are public and which require roles, placing those matchers before the final `anyRequest` rule. For form login, ensure the **login page and login processing URL** belong to the right chain; a login URL configured by one chain may become unreachable if it falls outside that chain's matcher.

Do not use overly broad public wildcards just to make the UI work. Test both normal requests and login/logout/CSRF flows.

### 6.6. `web.ignoring()` causing confusion that fallback still protects

`web.ignoring()` makes requests bypass normal security filters, so an ignored area should not be assumed to be protected by the fallback. When public pages still need security headers and shared processing, configuring `permitAll()` in the appropriate chain is usually easier to control.

### 6.7. Subtle matcher gaps missing URLs

Do not test only `/api/items` while ignoring path variants with/without trailing slashes, URL encoding, uppercase/lowercase, servlet paths, new endpoint versions, or MVC matchers behaving differently than expected. Specific matchers can depend on `RequestMatcher` type and application configuration. Write tests using exact real URLs and ensure the fallback catches unmatched paths.

### 6.8. Believing the fallback protects every port and servlet context of the system

The fallback only works for **requests that actually traverse the corresponding `DelegatingFilterProxy` / `FilterChainProxy`**. Another Servlet context, a management server on a separate port, a reverse proxy in front of the app, or URLs excluded from filter mapping may need separate configuration. Do not extrapolate one application's fallback chain to every infrastructure component.

## 7. How to observe and debug chain selection

When an endpoint yields an unexpected result, inspect in order:

1. **Does the request enter Spring Security Servlet?** Confirm `springSecurityFilterChain` proxy is registered for the path and dispatcher type under consideration.
2. **Which `SecurityFilterChain`s exist?** Record `@Order`, `securityMatcher`, authorization rules, and authentication mechanisms for each chain.
3. **Which chain matches the request first?** An earlier match-all chain renders later chains inactive for that URL.
4. **Which rule do `requestMatchers` in the selected chain's `authorizeHttpRequests` apply?** An overly broad `permitAll` rule may permit more URLs than intended.
5. **What kind of error is returned?** HTTP 401 typically means unauthenticated in the HTTP Basic example; 403 relates to access denied or CSRF; 302 may come from form login. Status also depends on configuration.
6. **Is the endpoint mapped by MVC to a controller?** Do not mistake a post-auth 404 for a request bypassing security.

In development, you can temporarily enable DEBUG logging to observe request protection:

```properties
logging.level.org.springframework.security.web.FilterChainProxy=DEBUG
logging.level.org.springframework.security=DEBUG
```

Do not enable overly detailed sensitive logging in production. Logs may contain request details; avoid logging tokens, cookies, or credentials. Seeing a "Securing ..." message is only a signal; testing 401/403/200 behavior remains necessary.

### Regression test matrix to maintain

| Path category | Anonymous | Valid user | What it verifies |
| --- | --- | --- | --- |
| Intentionally public | 200 (or expected public response) | Works | Public endpoints are not accidentally locked |
| Specialized API | 401 via HTTP Basic (if login required) | 200/403 per permission | API chain is selected |
| Internal path covered by fallback | 401 via HTTP Basic | 200/403 per permission | Fallback misses nothing |
| **New or handler-less path** | **401** if fallback requires auth | **404** if no handler exists | New URLs are not accidentally exposed |
| Sensitive path requiring role | 401 when not logged in | 403 if wrong role | `authenticated()` does not replace role checks |

For endpoints accepting only POST/PUT/DELETE, also test CSRF, content type, and concrete HTTP methods. Under default Servlet configuration, CSRF can return **403** before some authorization steps; do not assume every unauthenticated request must return 401 in all cases.

## 8. Changing policy and safe testing

If an application wants "every route must be explicitly declared to be usable", the fallback can switch from `authenticated()` to `denyAll()`:

```java
// Policy variant, not included in the runnable demo above.
@Bean
@Order(99)
SecurityFilterChain denyUnknown(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth.anyRequest().denyAll())
            .build();
}
```

This variant **must replace the existing fallback**, not be added as a third chain behind an earlier catch-all; if added afterward it has no chance to run. `denyAll` blocks authenticated requests as well, so separate chains or rules are needed for valid URLs. This design fits environments where new endpoints require policy approval.

Conversely, for apps allowing authenticated users to access shared routes, `authenticated()` is a more practical default. Whichever option you choose, add **a test for a hypothetical undeclared URL** to detect early if the fallback is deleted, its matcher is changed, or its order is broken.

## 9. Self-check questions

1. **Why can having only `.securityMatcher("/api/**")` and `anyRequest().authenticated()` still leave `/reports` exposed?** Because `anyRequest` applies only after the API chain is selected; `/reports` does not match the chain's matcher.
2. **Why must the fallback come last?** `FilterChainProxy` selects the first matching chain; a catch-all placed first shadows specialized chains.
3. **Does a fallback necessarily need `securityMatcher("/**")`?** No; with standard `HttpSecurity`, omitting `securityMatcher` means matching every request. `AnyRequestMatcher.INSTANCE` can be used when explicitness is desired.
4. **What is the difference between `authenticated()` and `denyAll()` in a fallback?** `authenticated()` lets authenticated callers proceed unless another rule restricts them; `denyAll()` rejects all requests handled by that chain.
5. **`GET /future/feature` has no controller; why does an anonymous caller receive 401 before 404 in the demo?** The fallback checks authentication before MVC looks up a handler; after authentication succeeds, MVC returns 404.
6. **Does `permitAll()` bypass the Spring Security filter chain?** No; it is an authorization rule inside the chain. `web.ignoring()` is what skips normal security filters for a request.
7. **Once a fallback is configured, do you still need to test the API chain separately?** Yes. You must ensure the fallback does not sit ahead of it and does not accidentally replace the API's dedicated rules, auth mechanism, CSRF, or session policy.

**Key takeaway:** When using multiple `SecurityFilterChain`s, place **specialized chains first and a match-all fallback chain last**; apply a default protection policy for remaining URLs; and test new or handler-less URLs. Having `anyRequest().authenticated()` in a scoped chain does **not** guarantee protection for the entire application.
