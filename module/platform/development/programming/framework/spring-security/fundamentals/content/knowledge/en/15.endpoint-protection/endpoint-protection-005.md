# Rule Order and the First-Matching-Rule Principle

## 1. Objectives

This lesson covers the **Endpoint protection** topic in Spring Security. After completing it, you will be able to:

1. Explain the **first matching rule** mechanism in `authorizeHttpRequests`: matcher–rule pairs are evaluated in declaration order, and **only the first matching rule is applied**.
2. Place specific matchers before broad matchers, and use `anyRequest().denyAll()` properly as the fallback.
3. Identify *rule shadowing* bugs: a strict security rule sits behind a broad rule and is therefore never used.
4. Distinguish `FilterChainProxy` selecting the **first matching `SecurityFilterChain`** from `AuthorizationFilter` selecting the **first matching rule inside the chain**.
5. Distinguish security rule ordering from how Spring MVC selects controller mappings by specificity.
6. Build and run a Java 17 + Spring Boot app with HTTP Basic, verify 200/401/403, and write tests that catch rule-reordering regressions.

The main example uses **Spring MVC/Servlet** (`HttpSecurity`, `SecurityFilterChain`). Spring WebFlux uses different reactive types (`ServerHttpSecurity`, `SecurityWebFilterChain`); do not mix the two stacks.

## 2. How Does a Rule List Work?

Consider the HTTP configuration:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public/**").permitAll()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll()
);
```

This is an **illustrative fragment**; it belongs inside the application's `SecurityFilterChain` configuration method.

Each line creates a **`RequestMatcher` → `AuthorizationManager`** pair. For example:

- The `/public/**` matcher matches a group of public paths; `permitAll()` allows access at this authorization step.
- The `/api/admin/**` matcher requires the `ADMIN` role.
- The `/api/**` matcher requires an authenticated caller.
- `anyRequest()` is the catch-all case when none of the earlier matchers matched.

When a request arrives, Spring Security executes this general logic:

```text
Request R
   │
   ▼
Does Matcher 1 match R?
   ├─ Yes → Apply rule 1 → ALLOW or DENY → STOP RULE SELECTION
   └─ No
          ▼
Does Matcher 2 match R?
   ├─ Yes → Apply rule 2 → ALLOW or DENY → STOP RULE SELECTION
   └─ No
          ▼
Matcher 3 ... → ...
          ▼
Fallback anyRequest() if no matcher matched
```

**Two things to remember:**

- Spring Security does not test every rule and then pick the "strongest," "most specific," or "allow" rule.
- If the first matching rule matches but the user fails its condition, the request **is immediately denied by that rule**. There is no second pass to try subsequent rules looking for another path.

Spring Security documentation explicitly describes this behavior as processing pattern/rule pairs in **declaration order** and applying only the **first match**.

### Tracing Each Request

| Request | First matching matcher | Rule actually applied |
| --- | --- | --- |
| `GET /public/news` | `/public/**` | `permitAll` |
| `GET /api/admin/users` | `/api/admin/**` | `hasRole("ADMIN")` |
| `GET /api/orders` | `/api/**` | `authenticated` |
| `GET /internal/health` | `anyRequest()` | `denyAll` |

`/api/admin/users` also matches the `/api/**` pattern. However, the `/api/admin/**` line above is selected first, so a user holding only `ROLE_USER` cannot pass, even though they are logged in.

## 3. Wrong Order Can Expose Endpoints

**Dangerous configuration:**

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").permitAll()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().denyAll()
);
```

The request `GET /api/admin/users` already matched the `/api/**` line and was permitted. The `hasRole("ADMIN")` line below **never decides permissions for this request**. The `denyAll()` fallback does not help either: it only handles requests **not yet** matched by an earlier line.

Another subtler bug:

```java
.requestMatchers("/api/**").authenticated()
.requestMatchers("/api/admin/**").hasRole("ADMIN")
```

In the HTTP policy above, any logged-in user can reach `/api/admin/**` because `authenticated()` is chosen first. Hiding the Admin button in the UI does not prevent users from making direct HTTP calls.

**Proper fix:**

```java
.requestMatchers("/api/admin/**").hasRole("ADMIN")
.requestMatchers("/api/**").authenticated()
.anyRequest().denyAll()
```

This is a verifiable ordering principle: **specific first, general later, fallback last**. Do not measure string lengths; look for matchers that can match the same request simultaneously.

### If the First Matching Rule Denies, Does Evaluation Continue?

**No.** Suppose `/api/admin/users` hits `hasRole("ADMIN")` and the caller has `ROLE_USER`. The decision is deny; Spring Security does not "fall through" to `authenticated()` below. If it tried later rules, any sensitive policy could be neutralized by a broad fallback.

## 4. Difference from Spring MVC Controller Selection

Two independent mechanisms usually exist:

| Component | Job to do | Selection mechanism |
| --- | --- | --- |
| Spring Security `authorizeHttpRequests` | Select HTTP authorization policy | **First rule whose matcher matches in declaration order** |
| Spring MVC `@RequestMapping`, `@GetMapping` | Select controller method | Evaluates method/path/params/headers and mapping specificity via MVC rules |
| Spring Security `FilterChainProxy` (multiple chains) | Select `SecurityFilterChain` | **First chain whose security matcher matches in priority order** |

Example specific controller:

```java
@GetMapping("/api/admin/users")
public String users() {
    return "users";
}
```

Spring MVC may pick this mapping over a generic handler, but it **does not** elevate the priority of Spring Security's `/api/admin/**` rule. If security placed `/api/**.permitAll()` earlier, the endpoint still risks being exposed even though the controller mapping is very specific.

**Principle:** do not use the MVC handler-selection algorithm to infer security policy order.

## 5. Designing a Safe Rule List

A pattern worth considering:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public/**").permitAll()
    .requestMatchers("/api/reports/admin").hasRole("ADMIN")
    .requestMatchers("/api/reports/**").hasAnyRole("ANALYST", "ADMIN")
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll()
)
```

With this pattern:

| Request | Selected line | Reason |
| --- | --- | --- |
| `/public/ping` | `/public/**` | Public, matches early |
| `/api/reports/admin` | `/api/reports/admin` | More specific than the general report path |
| `/api/reports/summary` | `/api/reports/**` | Does not match exact admin, matches reports |
| `/api/profile` | `/api/**` | Only the general API matcher remains |
| `/internal/diagnostics` | `anyRequest()` | Not in any listed group |

There is no default mechanism that assumes `ADMIN` "includes" `ANALYST`. The `hasAnyRole("ANALYST","ADMIN")` rule here **allows either one**; it is an explicit OR policy, not a role hierarchy.

### What Is `anyRequest()` For?

`anyRequest().denyAll()` expresses **default deny**: newly added endpoints without declared permissions will be denied instead of becoming public. Even so, it cannot rescue any endpoint already matched by an overly broad rule above it.

In the DSL, `anyRequest()` is the fallback at the end of the list. Do not place a catch-all `permitAll()` in front and think the fallback can lock down URLs.

### Understanding Common Rules

- `permitAll()`: allows passing the authorization step on the matched route; other filters can still run.
- `authenticated()`: requires successful authentication, without requiring a specific role.
- `hasRole("ADMIN")`: by default convention, requires the `ROLE_ADMIN` authority.
- `hasAuthority("ROLE_ADMIN")`: checks the exact provided authority string.
- `hasAnyRole("ANALYST","ADMIN")`: requires at least one of the corresponding authorities.
- `denyAll()`: denies regardless of what roles the user holds.

`User.withUsername("admin").roles("ADMIN")` creates the authority `ROLE_ADMIN`; when calling `hasRole`, **do not pass** `"ROLE_ADMIN"` as the argument to `hasRole` under default prefix configuration.

## 6. Runnable Java 17 Application: Verifying First-Match

Let's build a Spring Boot Servlet/MVC application with these endpoints:

| Endpoint | Policy |
| --- | --- |
| `GET /public/ping` | Public |
| `GET /api/profile` | Any authenticated user |
| `GET /api/reports/summary` | ANALYST or ADMIN |
| `GET /api/reports/admin` | ADMIN only |
| `GET /internal/diagnostics` | Has a real controller, but blocked by `denyAll` fallback |

The example uses **Spring Boot 3.3.13**, Spring Security 6.x, Gradle 8.x, and Java 17+. It uses HTTP Basic and GET-only endpoints so first-match behavior can be observed clearly without changing CSRF settings.

### 6.1. Structure and Build

```text
rule-order-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/ruleorder/
    │   ├── RuleOrderApplication.java
    │   ├── SecurityConfig.java
    │   └── DemoController.java
    └── test/java/com/example/ruleorder/
        └── RuleOrderSecurityTests.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'rule-order-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

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

**`src/main/java/com/example/ruleorder/RuleOrderApplication.java`**

```java
package com.example.ruleorder;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RuleOrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(RuleOrderApplication.class, args);
    }
}
```

### 6.2. `SecurityFilterChain`: Note the Order

**`src/main/java/com/example/ruleorder/SecurityConfig.java`**

```java
package com.example.ruleorder;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration(proxyBeanMethods = false)
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .requestMatchers("/api/reports/admin").hasRole("ADMIN")
                .requestMatchers("/api/reports/**").hasAnyRole("ANALYST", "ADMIN")
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }

    @Bean
    UserDetailsService userDetailsService() {
        UserDetails viewer = User.withUsername("viewer")
            .password("{noop}viewer123")
            .roles("VIEWER")
            .build();

        UserDetails analyst = User.withUsername("analyst")
            .password("{noop}analyst123")
            .roles("ANALYST")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password("{noop}admin123")
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(viewer, analyst, admin);
    }
}
```

The application creates three users with **one distinct role** each. There is no automatic role inheritance. `ADMIN` can access summary because the rule uses `hasAnyRole("ANALYST","ADMIN")`, not because admin implicitly holds the `ROLE_ANALYST` authority.

`{noop}` and hardcoded accounts are **for local demo only**; never deploy them to production. A real application needs a secure password encoder, secrets storage, user/role lifecycle management, and HTTPS.

`httpBasic(withDefaults())` enables HTTP Basic; `formLogin(...disable())` avoids redirects to a login page for requests needing authentication. The example keeps default CSRF settings and has no state-changing endpoints.

### 6.3. Controller

**`src/main/java/com/example/ruleorder/DemoController.java`**

```java
package com.example.ruleorder;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public/ping")
    public String publicPing() {
        return "public";
    }

    @GetMapping("/api/profile")
    public String profile() {
        return "profile";
    }

    @GetMapping("/api/reports/summary")
    public String summary() {
        return "summary";
    }

    @GetMapping("/api/reports/admin")
    public String adminReport() {
        return "admin-report";
    }

    @GetMapping("/internal/diagnostics")
    public String diagnostics() {
        return "internal";
    }
}
```

`/internal/diagnostics` **has a real mapping** but is denied by `denyAll` at the HTTP layer. A logged-in user calling that endpoint will receive 403 and will not receive the body `"internal"`. Thus, the existence of `@GetMapping` does not guarantee a request is allowed to reach the controller.

### 6.4. Running with Gradle and Sending Requests

In the `rule-order-demo` directory, with JDK 17+ and a compatible Gradle 8.x installed, run:

```bash
gradle test
gradle bootRun
```

If the project has a compatible Gradle Wrapper, replace with `./gradlew test` and `./gradlew bootRun` on Linux/macOS, or `gradlew.bat test` and `gradlew.bat bootRun` on Windows. You cannot run bare `javac`/`java` without the full Spring libraries; Gradle provides the classpath and launches `RuleOrderApplication`.

In another terminal:

```bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/api/profile
curl -i -u viewer:viewer123 http://localhost:8080/api/profile
curl -i -u viewer:viewer123 http://localhost:8080/api/reports/summary
curl -i -u analyst:analyst123 http://localhost:8080/api/reports/summary
curl -i -u analyst:analyst123 http://localhost:8080/api/reports/admin
curl -i -u admin:admin123 http://localhost:8080/api/reports/admin
curl -i -u admin:admin123 http://localhost:8080/internal/diagnostics
```

**Expected HTTP matrix:**

| GET endpoint | Anonymous | VIEWER | ANALYST | ADMIN |
| --- | :---: | :---: | :---: | :---: |
| `/public/ping` | 200 | 200 | 200 | 200 |
| `/api/profile` | 401 | 200 | 200 | 200 |
| `/api/reports/summary` | 401 | 403 | 200 | 200 |
| `/api/reports/admin` | 401 | 403 | 403 | 200 |
| `/internal/diagnostics` | 401* | 403 | 403 | 403 |

`*` With the demo's HTTP Basic setup, an anonymous request blocked by `denyAll()` can go through `AuthenticationEntryPoint` and receive 401; exact anonymous responses in other apps also depend on exception handling. The tests below explicitly verify **403 for an authenticated user** on this endpoint.

The bodies of the **200** responses are `public`, `profile`, `summary`, and `admin-report`, respectively. Do not expect a fixed JSON body for 401/403; the framework and content negotiation configuration can change error responses. What matters here is the status code and that sensitive endpoints do not return successful data.

### 6.5. Automated Tests Catching Ordering Bugs

**`src/test/java/com/example/ruleorder/RuleOrderSecurityTests.java`**

```java
package com.example.ruleorder;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RuleOrderSecurityTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicIsAccessibleWithoutLogin() throws Exception {
        mvc.perform(get("/public/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void anonymousCannotUseApi() throws Exception {
        mvc.perform(get("/api/profile"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(roles = "VIEWER")
    void viewerCanReadProfileButNotReports() throws Exception {
        mvc.perform(get("/api/profile"))
            .andExpect(status().isOk());
        mvc.perform(get("/api/reports/summary"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "ANALYST")
    void analystCanReadSummaryButNotAdminReport() throws Exception {
        mvc.perform(get("/api/reports/summary"))
            .andExpect(status().isOk())
            .andExpect(content().string("summary"));
        mvc.perform(get("/api/reports/admin"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminCanReadAllReportEndpoints() throws Exception {
        mvc.perform(get("/api/reports/summary"))
            .andExpect(status().isOk());
        mvc.perform(get("/api/reports/admin"))
            .andExpect(status().isOk())
            .andExpect(content().string("admin-report"));
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void unlistedDiagnosticsRemainsDenied() throws Exception {
        mvc.perform(get("/internal/diagnostics"))
            .andExpect(status().isForbidden());
    }
}
```

**Why is this a valuable test suite?**

- If `/api/**.authenticated()` is placed **before** `/api/reports/**`, VIEWER will accidentally reach summary; `viewerCanReadProfileButNotReports` fails.
- If `/api/reports/**` is placed **before** `/api/reports/admin`, ANALYST will reach the admin report; `analystCanReadSummaryButNotAdminReport` fails.
- If the `denyAll()` fallback is removed or replaced with an overly broad rule, `unlistedDiagnosticsRemainsDenied` will flag the unintended change.
- Allow and deny tests sit side by side to cover the full boundary of the policy.

`@WithMockUser(roles = "ANALYST")` creates `ROLE_ANALYST` in the test security context; it does not perform a real login against the `InMemoryUserDetailsManager` password store. Use the `curl -u` commands above when you need to test HTTP Basic and credentials directly.

## 7. Two Levels of "First Match" When Using Multiple `SecurityFilterChain`s

An application can declare multiple `SecurityFilterChain` beans, such as an API using bearer tokens and a website using session login. Do not confuse **chain order** with **rule order**.

**Level 1 — selecting the chain.** `FilterChainProxy` iterates through chains in priority order, usually set with `@Order`. The first chain whose `securityMatcher` accepts the request is selected. If the request is denied inside that chain, Spring Security **does not move on to another chain** to ask permission a second time.

**Level 2 — selecting the authorization rule.** Inside the selected chain, `authorizeHttpRequests` checks `requestMatchers` in order and applies the first matching rule.

```text
Request
  ↓
FilterChainProxy
  ├─ Does @Order(1) SecurityFilterChain's securityMatcher match?
  │       ├─ Yes → select chain 1 → apply first-match rule in chain 1
  │       └─ No
  ├─ Does @Order(2) SecurityFilterChain's securityMatcher match?
  │       ├─ Yes → select chain 2 → apply first-match rule in chain 2
  │       └─ No
  └─ No chain matches → request falls outside those security chains
```

**Separate fragment illustrating two chains (do not paste into the section 6 demo):**

```java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated()
        )
        .httpBasic(withDefaults())
        .build();
}

@Bean
@Order(2)
SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().denyAll()
        )
        .build();
}
```

The snippet above requires `import org.springframework.core.annotation.Order` and the corresponding security/bean imports; it is an illustrative configuration fragment only, not a standalone program.

For `GET /api/admin/users`, the API chain `@Order(1)` is selected; the admin rule inside that chain decides access. For `GET /public/ping`, the API chain does not match, so the fallback chain `@Order(2)` is evaluated and denies it. **If a general chain without a `securityMatcher` is given highest priority**, it can shadow the API chain below it because a chain without a matcher normally matches every request.

In particular: if you only define a chain with `securityMatcher("/api/**")` and **no fallback chain covering the rest**, requests outside `/api/**` may go unprotected by Spring Security. Do not infer that "no matching chain" means "default deny"; those are two different situations.

| API | Level applied | Question |
| --- | --- | --- |
| `http.securityMatcher("/api/**")` | Entire `SecurityFilterChain` | Should this chain be selected for the request? |
| `authorizeHttpRequests(...requestMatchers(...))` | Inside the selected chain | Which rule applies? |
| `anyRequest().denyAll()` | Fallback in the selected chain | What if no earlier rule matched? |

## 8. HTTP Method Is Also Part of the Matcher

The same path does not necessarily use the same rule. For example:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.DELETE, "/api/articles/**").hasRole("ADMIN")
    .requestMatchers(HttpMethod.GET, "/api/articles/**").hasRole("READER")
    .anyRequest().denyAll()
)
```

This is a **fragment** needing `import org.springframework.http.HttpMethod`. DELETE and GET are defined separately; POST/PATCH not matching the two lines above hit the `denyAll` fallback. If a general rule:

```java
.requestMatchers("/api/articles/**").authenticated()
.requestMatchers(HttpMethod.DELETE, "/api/articles/**").hasRole("ADMIN")
```

is placed in front, the DELETE rule is shadowed by the method-agnostic matcher. The fix is to put the specific DELETE rule first and check the remaining HTTP methods.

### Watch Out for HTTP HEAD and OPTIONS

Spring MVC can support **HEAD** for a `@GetMapping` handler, while a security matcher restricted to `HttpMethod.GET` does not automatically match HEAD. If a broader rule further down is more permissive, HEAD could follow a different policy. Therefore, for sensitive resources, define explicit policies for HEAD/OPTIONS, preflight endpoints, and other methods rather than assuming GET alone is enough.

Matching can also depend on context path, servlet path, trailing slashes, encoding, case-sensitivity settings, and the actual `RequestMatcher` type. The `requestMatchers(String...)` API in a Spring MVC environment may choose an MVC-aware matcher depending on version and configuration. Test **actual requests** through your gateway or web server rather than guessing from the URL string alone.

### Do Not Confuse `permitAll` with Ignoring Filters

`requestMatchers("/public/**").permitAll()` permits at the HTTP authorization layer of the security chain, while the request still passes through configured security filters. By contrast, `web.ignoring()` or a configuration where no chain matches can cause requests to bypass those filters. For normal public endpoints, using `permitAll()` keeps security headers and necessary mechanisms intact. Do not bypass the entire chain just to avoid login.

## 9. HTTP Security Does Not Replace Service-Layer Permission Checks

A `.requestMatchers("/api/documents/**").authenticated()` rule only tells you the request is logged in; it does **not** prove the user is allowed to read a specific document ID. For `GET /api/documents/123`, the backend still needs to check owner, tenant, state, sharing settings, and business permissions.

Illustrative code:

```java
@GetMapping("/api/documents/{documentId}")
public DocumentDto view(@PathVariable long documentId) {
    return documentService.getVisibleForCurrentUser(documentId);
}
```

This is a **non-standalone fragment**; it requires the `DocumentDto` type, `documentService`, and server-side resource permission checks. A service call from a scheduled job or message handler can also bypass the HTTP layer; use `@PreAuthorize` or an appropriate authorization service when a policy must hold across multiple entry points.

Still, a check in the service **is no excuse for misordering HTTP rules**: another endpoint might return data directly or call a service path that lacks equivalent protection.

## 10. Common Mistakes and Review Checklist

| Mistake | Consequence | Fix |
| --- | --- | --- |
| `/api/**.permitAll()` placed before `/api/admin/**.hasRole("ADMIN")` | Admin endpoints can become public | Put admin rule first; test anonymous |
| `/api/**.authenticated()` before `/api/reports/**.hasRole(...)` | Any logged-in user can view reports | Put report rule first; test user without role |
| Assuming the "most specific" rule is picked automatically | Misjudging policy | Review in actual DSL declaration order |
| Assuming a denying rule falls through to the next rule | Misunderstanding first-match | A matched rule decides; there is no fallback allow |
| Setting `anyRequest().permitAll()` before reviewing all routes | New endpoints can be exposed | Use `denyAll` when appropriate for policy |
| General chain has higher priority than API chain | API chain is shadowed | Set `@Order` and `securityMatcher` clearly |
| Using `securityMatcher("/api/**")` without a fallback chain | Other paths may go unprotected | Add a chain covering the rest |
| Strict GET rule while HEAD/OPTIONS hit a broad rule | Policy differs by method | Design/test all relevant HTTP methods |
| Confusing MVC handler specificity with security rule order | Falsely believing specific endpoints are protected | Test both mechanisms separately |
| Testing only 200 without testing 401/403 | Fails to catch overly open permissions | Include negative cases |
| Treating every 403 as a missing role | Misses CSRF/dispatch/access denied handler | Find root cause via safe logs |
| Passing `hasRole("ROLE_ADMIN")` under default prefix | Role check fails | Use `hasRole("ADMIN")` or `hasAuthority("ROLE_ADMIN")` |

Checklist before changing rules:

1. For each sensitive endpoint, list all matchers that could match; identify the **first matcher**.
2. Verify the selected rule is strict enough even for an authenticated user with no roles.
3. Check whether any broad matcher accidentally shadows a specific matcher.
4. With multiple chains, identify the **first chain** and fallback chain, and check `@Order`.
5. Check all HTTP methods, especially HEAD/OPTIONS when controllers have GET.
6. Test anonymous, insufficient privilege, proper privilege, and unlisted requests.
7. For resource IDs, verify owner/tenant/state at the business layer.

## 11. Self-Check Exercises

**Question 1.** With the order `/api/**.authenticated()` then `/api/admin/**.hasRole("ADMIN")`, what happens when a user with `ROLE_USER` accesses `/api/admin/users`?

**Answer:** the first HTTP authorization step may allow the request because the user is authenticated. The admin rule is shadowed. Another controller/service check might still reject it, but the URL configuration is wrong.

**Question 2.** If the first matching rule matches and returns 403, does Spring Security evaluate the next rule?

**Answer:** no. "First match" means picking the policy once, whether that policy allows or denies.

**Question 3.** Can `anyRequest().denyAll()` block `/api/admin/users` when `/api/**.permitAll()` is at the top?

**Answer:** no. The request was already picked by the first matcher, so it never reaches the fallback.

**Question 4.** Why does `@GetMapping("/api/admin/users")` not prove the `/api/admin/**` rule is evaluated before `/api/**`?

**Answer:** Spring MVC selects controller mappings by its own mechanism; Spring Security applies authorization rules in declaration order.

**Question 5.** Two `SecurityFilterChain` beans both match `/api/admin`; if the first chain denies, is the second chain used?

**Answer:** no. `FilterChainProxy` picks the first matching chain; later chains are only tried when earlier chains **do not match**.

**Question 6.** Does `securityMatcher("/api/**")` mean every URL outside the API will be denied?

**Answer:** no. If no other chain matches, URLs outside `/api/**` may not be protected by Spring Security at all.

**Question 7.** Why is it necessary to test that `ANALYST` gets 403 when accessing `/api/reports/admin`?

**Answer:** if someone moves `/api/reports/**` above the admin rule, this test will fail and catch the overly broad permission.

**Question 8.** When using an `HttpMethod.GET` matcher, can you ignore HEAD?

**Answer:** you should not assume that; a `@GetMapping` handler can serve HEAD in Spring MVC while the security matcher restricts only GET. You need an explicit HEAD policy.

## 12. Key Takeaways

- **In `authorizeHttpRequests`, only the first rule whose matcher matches is applied**, even when that rule denies.
- **Specific rules first, broad rules later, fallback last**; `anyRequest().denyAll()` only protects requests not matched by earlier matchers.
- **Two distinct levels of first-match:** selecting the `SecurityFilterChain` by `securityMatcher` and chain order, then selecting the authorization rule by `requestMatchers`.
- `@GetMapping`/`@RequestMapping` have an independent handler-selection mechanism; do not equate MVC specificity with security rule priority.
- Matchers can inspect HTTP method, path, servlet mapping, dispatches, and custom matchers; test real endpoints and important HTTP methods.
- **Testing denied cases** catches shadowed rules better than checking only successful responses.
- HTTP protection must be paired with per-resource permission checks in services when business logic requires them.

### Official Documentation

- Spring Security — Authorize HTTP Requests, first matching rule: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Multiple SecurityFilterChain and securityMatcher: https://docs.spring.io/spring-security/reference/servlet/configuration/java.html
- Spring Security — FilterChainProxy architecture: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security — MockMvc integration: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html
- Spring Security — @WithMockUser testing: https://docs.spring.io/spring-security/reference/servlet/test/method.html
- Spring Framework — Mapping Requests, specificity and HTTP HEAD: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html
