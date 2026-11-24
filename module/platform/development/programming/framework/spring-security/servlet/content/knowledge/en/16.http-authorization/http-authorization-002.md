# Rule Ordering and First-Match Semantics in HTTP Authorization

In **Spring Security Servlet**, multiple HTTP authorization rules can describe the same request. A common mistake is placing a general rule before a specific rule and assuming the framework will automatically pick the "strictest" or "longest-path" rule. With `authorizeHttpRequests` configured as a list of `requestMatchers`, remember this principle:

> **The first rule whose RequestMatcher matches the HTTP request is used to make the authorization decision.** Subsequent rules are no longer evaluated for that same decision step, even if the first rule denies access.

In addition, there is **another level of ordering**: when declaring **multiple `SecurityFilterChain`s**, `FilterChainProxy` selects the **first chain** whose `securityMatcher` matches the request. Only after selecting the chain are the authorization rules belonging to **the selected chain** evaluated. These are two related "first-match" principles with **different scopes**.

This article focuses on **rule ordering and first-match semantics in HTTP authorization**; examples use Java 17+, Spring Security 6.x, Spring Boot 3.3.5, and MockMvc. Non-standalone illustrative snippets are clearly marked; the complete project example can be run with Gradle when the corresponding dependencies are present.

## 1. Learning Objectives

After this article, you should be able to:

1. Explain how Spring Security evaluates the list of authorization matchers **in declaration order**.
2. Distinguish **a matching request matcher** from **an accepted permission condition**; denial in the first rule does not mean falling through to subsequent rules.
3. Place **specific/strict** rules before **broad/general** rules, and place `anyRequest()` at the end.
4. Distinguish `securityMatcher(...)` for **selecting a SecurityFilterChain** from `requestMatchers(...)` inside `authorizeHttpRequests` for **selecting an authorization rule**.
5. Check the effects of HTTP method, path, role, authority, overlapping rules, CSRF, and filter chain order.
6. Write tests demonstrating 200/201/401/403 cases and detecting unintentionally exposed permissions.
7. Follow a review and regression testing process when adding endpoints or refactoring security configuration.

## 2. Three Questions for an HTTP Request

A request passing through Spring Security usually has to answer three questions across different processing layers:

**Question A - Which chain does the request enter?** `FilterChainProxy` uses `SecurityFilterChain.securityMatcher` and **chain order** to select the set of filters protecting the request.

**Question B - Which permission does the request require?** Inside a chain with `AuthorizationFilter` and `authorizeHttpRequests`, the list of `requestMatchers` is evaluated **in order**, selecting the first matching rule.

**Question C - Does the principal have sufficient permission?** The selected rule checks `Authentication`, authorities, roles, or `AuthorizationManager` logic to allow or deny. Once a rule is selected and the result is deny, **there is no step to look for an "easier" next rule**.

Diagram:

~~~text
HTTP request
    |
    v
FilterChainProxy
    |
    +-- SecurityFilterChain @Order(1) securityMatcher -> matches?
    |       +-- Yes: SELECT CHAIN 1; do not evaluate chain 2/3
    |       +-- No: evaluate next chain
    |
    +-- SecurityFilterChain @Order(2) securityMatcher -> matches?
    |       +-- Yes: SELECT CHAIN 2
    |       +-- No: continue evaluating
    |
    v
Inside the selected chain:
    AuthorizeHttpRequests / RequestMatcherDelegatingAuthorizationManager
    |
    +-- rule 1 requestMatcher -> matches?  Yes -> grant/deny decision
    |                                             DO NOT evaluate rule 2
    +-- rule 2 requestMatcher -> matches?  Yes -> grant/deny decision
    +-- rule 3 requestMatcher -> ...
    +-- anyRequest() -> explicit fallback if configured
    |
    v
Allow -> controller; Deny -> security exception/entry point
~~~

**Note:** Other filters such as `CsrfFilter` and authentication filters also run according to chain configuration. A 403 may come from CSRF **before** authorization rules are even evaluated; do not conclude that `hasRole` failed solely from the HTTP status.

## 3. An Example of Wrong Ordering

Consider two paths:

- `GET /api/products/42`: logged-in users can view.
- `GET /api/admin/audit`: only admins can view.

The following **WRONG** configuration puts the general rule first:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").authenticated()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().denyAll())
~~~

Both `/api/products/42` and `/api/admin/audit` match `"/api/**"`. For `/api/admin/audit`, Spring Security stops selecting rules right at `authenticated()`. Any logged-in user can pass HTTP authorization, even though the admin rule sits on the line below!

**The admin rule never gets a chance to be evaluated.** There is no implicit logic for "which rule is more specific" or "which role is stronger" once a rule above has already matched.

The **CORRECT** configuration for the intent above:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll())
~~~

New order:

1. `GET /api/admin/audit` matches the admin rule first -> must have `ROLE_ADMIN`.
2. `GET /api/products/42` does not match the admin rule, matches `/api/**` -> requires authenticated.
3. `GET /other` does not match the two rules above -> `anyRequest().denyAll()`.

### 3.1. Case of Deny First, Permit Later

Consider:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").denyAll()
    .requestMatchers("/api/public/**").permitAll()
    .anyRequest().denyAll())
~~~

Even though `/api/public/ping` is declared `permitAll` on the second line, it already matched `/api/**` above and is hit by `denyAll()`. **Denial does not make the framework try the second rule.**

To make public truly public:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/public/**").permitAll()
    .requestMatchers("/api/**").denyAll()
    .anyRequest().denyAll())
~~~

Similarly, an overly broad `permitAll()` at the top can nullify admin restrictions below. The outcome depends on the **first matching rule**, not on whether later rules are "stronger" or "weaker".

### 3.2. Visual Rule-Ordering Check Table

With these rules:

~~~java
.requestMatchers("/api/public/**").permitAll()
.requestMatchers("/api/admin/**").hasRole("ADMIN")
.requestMatchers("/api/**").authenticated()
.anyRequest().denyAll()
~~~

| Request | First Matching Matcher | Decision to Verify |
| --- | --- | --- |
| GET /api/public/ping | /api/public/** | `permitAll()` |
| GET /api/admin/audit | /api/admin/** | `hasRole("ADMIN")` |
| GET /api/products/42 | /api/** | `authenticated()` |
| GET /private | anyRequest | `denyAll()` |

The longest path does not win automatically. This configuration works **because the author placed specific matchers before broader matchers**.

## 4. "Matching" and "Being Permitted" Are Two Independent Steps

Each rule in `authorizeHttpRequests` essentially consists of:

1. A `RequestMatcher` deciding whether the request belongs to the group to evaluate.
2. An `AuthorizationManager`/policy deciding whether the current principal has enough permission for the matched request.

Example:

~~~java
.requestMatchers("/api/admin/**").hasRole("ADMIN")
.requestMatchers("/api/**").authenticated()
~~~

For a regular user accessing `/api/admin/audit`:

- The first rule **matches the path**.
- The first rule requires `ROLE_ADMIN`, which the user lacks -> **deny**.
- The second rule **is not evaluated**, even though the user certainly satisfies `authenticated()`.

This is an important property preventing requests from "falling through" to an easier rule after failing a strict rule. If you observe an admin API being open, the cause is usually a **broad rule matching earlier**, not the framework falling back after a denial.

### 4.1. `hasRole` vs. `hasAuthority`

- `hasRole("ADMIN")` by default checks an authority with the `ROLE_` prefix, e.g., `ROLE_ADMIN`.
- `hasAuthority("SCOPE_orders.read")` checks the **exact authority string**, without automatically adding `ROLE_` or `SCOPE_`.
- `authenticated()` only requires an authenticated principal under Spring Security's trust model, without checking a specific role.
- `fullyAuthenticated()` differs from `authenticated()` by not accepting remember-me-only authentication as full authentication.
- `permitAll()` does not require an authenticated principal for that rule, but **does not turn off the entire filter chain**.
- `denyAll()` always denies at the corresponding rule.

For example, a role with the wrong prefix can cause a 403 even when first-match is right. When debugging, check both **which matcher was selected** and **the user's actual authorities**; do not look only at order.

## 5. HTTP Method Is Also Part of the Match Condition

The path may match, yet a different method will lead to a different rule.

Order-management business example:

- `GET /api/orders/42`: requires `SCOPE_orders.read`.
- `POST /api/orders`: requires `SCOPE_orders.write`.
- `DELETE /api/orders/42`: not open if there is no dedicated rule.

Illustrative rules:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/orders/*")
        .hasAuthority("SCOPE_orders.read")
    .requestMatchers(HttpMethod.POST, "/api/orders")
        .hasAuthority("SCOPE_orders.write")
    .requestMatchers("/api/orders", "/api/orders/**")
        .denyAll()
    .anyRequest().denyAll())
~~~

For `GET /api/orders/42`, the first rule matches both method and path. For `POST /api/orders`, the GET rule does not match the method, so the POST rule matches and requires write. For `DELETE /api/orders/42`, the first two rules do not match the method, so the `denyAll` rule blocks the request.

**Note:** In a web application with CSRF protection, POST/PUT/PATCH/DELETE may be rejected by `CsrfFilter` for missing a CSRF token **before** method-aware rules are checked. To test authorization specifically for POST, use a valid token or a properly configured test fixture; do not disable CSRF broadly in production for testing convenience.

### 5.1. What Happens If the Method Is Omitted?

The following configuration is usually **too broad**:

~~~java
.requestMatchers("/api/orders/**").hasAuthority("SCOPE_orders.read")
~~~

It does not express "read-only". The matcher only specifies the path, so other HTTP methods to that path can also match; if a user has `SCOPE_orders.read` and a controller also supports POST/DELETE there, HTTP authorization may allow unintended actions. Another filter (such as CSRF) may block some requests, but **never use CSRF as a substitute for write/delete permissions**.

Specify HTTP method matchers when authorization goals depend on method, and define an explicit fallback for unsupported methods.

### 5.2. Path Pattern Types and Actual Coverage

In Spring MVC, the form `"/api/orders/*"` typically illustrates one segment after `/api/orders/`, while `"/api/orders/**"` typically describes a broader scope. However, actual matcher semantics can depend on Spring Security version, `RequestMatcher` type, Spring MVC/servlet path configuration, and how the framework normalizes paths. Do not infer behavior from regex or JavaScript globs; test with the **actual matchers in your application**.

In particular, check:

- Whether there is a non-root context path.
- Whether there are multiple `DispatcherServlet`s or a custom servlet path.
- Trailing slashes, path variables, dots, URL encoding, and semicolons/path parameters.
- Case sensitivity of the matcher and proxy infrastructure.
- Whether a path matches `/api/orders/**` when there is no extra segment; if important, explicitly declare `"/api/orders"` as in the example.
- How forward/error dispatches from Spring MVC pass through the security chain.

Do not write something that "looks right" and assume every case matches as intended. **A RequestMatcher is a condition evaluated by the framework on the HTTP request**, not a list of paths inferred by the developer from controller names.

## 6. Position of `anyRequest()` and Default Policy

`anyRequest()` represents the fallback for requests not matching the specific rules above. In a list-based configuration, place it at the **end**:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/actuator/health").permitAll()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll())
~~~

Do not place `anyRequest().permitAll()` at the top and expect rules below to take effect; it will cover all requests before other rules are evaluated. The DSL API also enforces restrictions against declaring further rules after `anyRequest()`.

### 6.1. Default Deny Instead of Default Permit

For APIs with sensitive data, the safe policy is usually:

~~~java
.anyRequest().denyAll()
~~~

Thanks to this, new endpoints **are not automatically opened** when a developer adds a controller and forgets to update authorization rules. If `anyRequest().authenticated()` is chosen, any new endpoint only requires being logged in to pass the general authorization step, which can exceed intent for admin endpoints or special operations.

Choosing `denyAll()` as fallback does not "override" permissions of rules above it: it is only evaluated if no prior matcher matched.

### 6.2. An Overly Broad Rule Right Before the Fallback

Example:

~~~java
.requestMatchers("/api/**").authenticated()
.anyRequest().denyAll()
~~~

The `denyAll` fallback **does not protect** new endpoints under `/api/**` from the overly general `authenticated()` rule. If later a `POST /api/admin/create-user` controller is added without an admin rule above, regular authenticated users can pass the HTTP authorization step. Consider whitelisting specific endpoint/method groups or separating `/api/admin/**` before the general rule.

### 6.3. What If No Matcher Matches?

Depending on the version and how the AuthorizationManager is built, behavior when no rule matches may vary or follow a non-obvious contract. Do not rely on a "guessable default" to protect APIs. Declare an **explicit fallback** with `anyRequest().denyAll()` and test unlisted paths.

## 7. Two Levels of First-Match: Filter Chain and Authorization Rule

If there is only one `SecurityFilterChain`, order review usually focuses on `requestMatchers`. But when there are multiple chains, there is an earlier decision.

### 7.1. Selecting a SecurityFilterChain via `securityMatcher`

**Standalone illustrative sample**, not combined into the single-chain project in section 8:

~~~java
@Bean
@Order(1)
SecurityFilterChain adminChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/admin/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().hasRole("ADMIN"))
        .httpBasic(Customizer.withDefaults())
        .build();
}

@Bean
@Order(2)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}

@Bean
@Order(3)
SecurityFilterChain fallbackChain(HttpSecurity http)
        throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().denyAll())
        .build();
}
~~~

Place these methods inside Spring `@Configuration`, importing `Bean`, `Order`, `HttpSecurity`, `SecurityFilterChain`, and `Customizer`. Do not copy these three beans alongside the single-chain bean without redefining the policy; the samples are **two different approaches**.

For `/api/admin/audit`:

1. `adminChain` matches first per `@Order(1)` -> selected.
2. Inside `adminChain`, `anyRequest().hasRole("ADMIN")` -> user must have `ROLE_ADMIN`.
3. `apiChain` **could also match the URL**, but is not selected because the earlier chain matched.

If the order of the two chains is reversed, the general `apiChain` can win first and require only `authenticated`, weakening admin protection. **This is a chain-level bug**, even if the rules inside `adminChain` are ordered perfectly.

### 7.2. One Selected Chain Does Not Try Another Chain on Denial

When the first matching chain is selected and authorization denies, Spring Security **does not forward the request to the second chain** to look for an easier rule. Filter chain selection is **first-match**, not "try until some chain lets it through".

Similarly, when the first rule matches and denies, the framework does not try the next rule in the same chain.

Two decision layers with similar structure but different functions:

| Level | Selecting Component | Condition | If Matched | If Denied |
| --- | --- | --- | --- | --- |
| Filter chain | `FilterChainProxy` | `securityMatcher` and chain order | Runs filters of first matching chain | Does not fall through to next chain |
| HTTP authorization rule | `RequestMatcherDelegatingAuthorizationManager` / `authorizeHttpRequests` config | `requestMatchers` in order | Runs authorization manager of first matching rule | Does not fall through to next rule |
| Permission/identity | `AuthorizationManager` + Authentication | Authorities, roles, status, business policy | Grants/denies within selected rule | Handled by security exception/entry point |

### 7.3. What If a Request Matches No SecurityFilterChain?

In principle, a request not matched by **any Spring Security filter chain** may not be protected by Spring Security as you expect. Therefore, when using multiple chains with `securityMatcher(...)`, ensure there is a **fallback chain** covering remaining requests or a verified default-deny architecture.

This **differs from** `anyRequest().denyAll()` inside a chain restricted by `securityMatcher("/api/**")`. That fallback only protects requests **that entered the chain**; it does not automatically apply to `/admin/**` outside the chain.

### 7.4. @Order Differs from Rule Line Order Inside a Chain

- `@Order(1)` on a `SecurityFilterChain` bean prioritizes **chain selection order**.
- The order of `requestMatchers` inside one `authorizeHttpRequests` decides **HTTP rules**.
- `@Order` on a method/service or filter component does not automatically move authorization rules.
- Spring MVC controller mapping priority does not rewrite security rule order.

Do not debug an ordering bug in `authorizeHttpRequests` by merely changing the chain's `@Order`, or vice versa.

## 8. Runnable Java 17+ Example: Path- and HTTP-Method-Based Policy

The following example illustrates **a single filter chain** with clear ordering and a deny-all fallback. The program uses Spring Boot 3.3.5, Spring Security, HTTP Basic, MVC, and MockMvc. The in-memory users are only for learning; passwords are encoded with BCrypt.

The application includes:

- `GET /api/public/ping`: accessible to anyone.
- `GET /api/admin/metrics`: `ROLE_ADMIN` only.
- `GET /api/orders/42`: `SCOPE_orders.read` authority only.
- `POST /api/orders`: `SCOPE_orders.write` only, requires a CSRF token under default policy.
- `DELETE /api/orders/42`: has a controller but **is denied by denyAll** because no rule allows it.
- `GET /api/profile`: authenticated users.
- Any request outside the whitelist: `denyAll`.

### 8.1. Project Structure

~~~text
rule-order-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/rules/
    │   ├── RuleOrderApplication.java
    │   ├── SecurityConfiguration.java
    │   └── ApiController.java
    └── test/java/example/rules/
        └── RuleOrderTests.java
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'rule-order-demo'
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
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
~~~

### 8.2. Application

File `src/main/java/example/rules/RuleOrderApplication.java`:

~~~java
package example.rules;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RuleOrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(RuleOrderApplication.class, args);
    }
}
~~~

### 8.3. SecurityConfiguration

File `src/main/java/example/rules/SecurityConfiguration.java`:

~~~java
package example.rules;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
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
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                // 1. Specific public rule first.
                .requestMatchers(HttpMethod.GET, "/api/public/ping")
                    .permitAll()

                // 2. Admin group is stricter than regular rules.
                .requestMatchers("/api/admin/**")
                    .hasRole("ADMIN")

                // 3. Method- and specific-resource-based permissions.
                .requestMatchers(HttpMethod.GET, "/api/orders/*")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.write")

                // 4. Do not open unlisted order methods.
                .requestMatchers("/api/orders", "/api/orders/**")
                    .denyAll()

                // 5. An endpoint requiring login, without requiring a scope.
                .requestMatchers(HttpMethod.GET, "/api/profile")
                    .authenticated()

                // 6. All remaining requests are denied.
                .anyRequest().denyAll())

            .httpBasic(Customizer.withDefaults())

            // Do not disable CSRF: POST must satisfy CSRF policy.
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder(10);
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {

        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-pass"))
            .authorities("ROLE_USER", "SCOPE_orders.read")
            .build();

        UserDetails writer = User.withUsername("writer")
            .password(encoder.encode("writer-pass"))
            .authorities("ROLE_USER", "SCOPE_orders.write")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-pass"))
            .authorities("ROLE_ADMIN")
            .build();

        return new InMemoryUserDetailsManager(reader, writer, admin);
    }
}
~~~

Points to read carefully:

1. The `GET /api/public/ping` rule is **public and specific**, not opening `POST /api/public/ping` or all URLs under `/api/public/**`.
2. `"/api/admin/**"` comes before other rules; only admin can pass.
3. `HttpMethod.GET` and `HttpMethod.POST` separate read and write purposes.
4. `"/api/orders"` and `"/api/orders/**"` sit in a dedicated fallback to prevent unapproved methods from being exposed by a broader new rule.
5. `/api/profile` only requires `authenticated`; `reader`, `writer`, and `admin` all qualify.
6. `anyRequest().denyAll()` is placed last, preventing new endpoints from opening access automatically.
7. `httpBasic` is used to produce the familiar 401 result when credentials are missing on a protected API; this is an example for learning HTTP authorization, not a recommendation that HTTP Basic is optimal for every production API.
8. CSRF remains enabled by default. If a POST request lacks a token, `CsrfFilter` can return 403 **before** reaching the write rule; tests must distinguish these two error causes.
9. In-memory users have different server-issued roles/scopes. `.hasRole("ADMIN")` is equivalent to checking `ROLE_ADMIN` under the default prefix; do not pass `"ROLE_ADMIN"` into `hasRole`.
10. For production, add account status, a real user store, HTTPS, key/password lifecycle, logging redaction, and method-level/domain-level authorization per your threat model.

### 8.4. API Controller

File `src/main/java/example/rules/ApiController.java`:

~~~java
package example.rules;

import java.security.Principal;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {

    @GetMapping("/api/public/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/api/admin/metrics")
    public String metrics() {
        return "admin-metrics";
    }

    @GetMapping("/api/orders/{id}")
    public String order(@PathVariable long id) {
        return "order-" + id;
    }

    @PostMapping("/api/orders")
    @ResponseStatus(HttpStatus.CREATED)
    public String createOrder() {
        return "created";
    }

    @DeleteMapping("/api/orders/{id}")
    public String deleteOrder(@PathVariable long id) {
        return "deleted-" + id;
    }

    @GetMapping("/api/profile")
    public String profile(Principal principal) {
        return principal.getName();
    }
}
~~~

Even though the controller has a `DELETE /api/orders/{id}` method, no user is permitted by the current HTTP authorization rules to invoke it. This proves that **having a controller mapping** does not mean security allows the request to reach the controller.

### 8.5. MockMvc Tests Verifying Order

File `src/test/java/example/rules/RuleOrderTests.java`:

~~~java
package example.rules;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RuleOrderTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void publicPingWorksAnonymously() throws Exception {
        mockMvc.perform(get("/api/public/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("pong"));
    }

    @Test
    void orderReadWithoutAuthenticationIsUnauthorized() throws Exception {
        mockMvc.perform(get("/api/orders/42"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void readerCanReadOrder() throws Exception {
        mockMvc.perform(get("/api/orders/42")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("order-42"));
    }

    @Test
    void writerCannotReadOrderWithoutReadScope() throws Exception {
        mockMvc.perform(get("/api/orders/42")
                .with(httpBasic("writer", "writer-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void writerCanCreateOrderWithCsrf() throws Exception {
        mockMvc.perform(post("/api/orders")
                .with(httpBasic("writer", "writer-pass"))
                .with(csrf()))
            .andExpect(status().isCreated())
            .andExpect(content().string("created"));
    }

    @Test
    void writerPostWithoutCsrfIsForbidden() throws Exception {
        mockMvc.perform(post("/api/orders")
                .with(httpBasic("writer", "writer-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void readerCannotCreateOrderEvenWithCsrf() throws Exception {
        mockMvc.perform(post("/api/orders")
                .with(httpBasic("reader", "reader-pass"))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    void deleteIsDeniedByOrdersFallback() throws Exception {
        mockMvc.perform(delete("/api/orders/42")
                .with(httpBasic("writer", "writer-pass"))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanReadAdminMetrics() throws Exception {
        mockMvc.perform(get("/api/admin/metrics")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin-metrics"));
    }

    @Test
    void readerCannotReadAdminMetrics() throws Exception {
        mockMvc.perform(get("/api/admin/metrics")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void profileNeedsOnlyAuthentication() throws Exception {
        mockMvc.perform(get("/api/profile")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("reader"));
    }

    @Test
    void unmatchedPathIsDeniedEvenForAuthenticatedUser()
            throws Exception {
        mockMvc.perform(get("/undocumented")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isForbidden());
    }
}
~~~

### 8.6. Explaining Tests by First-Match Semantics

| Test case | First Matching Rule | Expected |
| --- | --- | --- |
| GET /api/public/ping, anonymous | GET public | 200 |
| GET /api/orders/42, anonymous | GET orders read | 401 because not authenticated |
| GET /api/orders/42, reader | GET orders read | 200 |
| GET /api/orders/42, writer | GET orders read | 403, missing SCOPE_orders.read |
| POST /api/orders, writer + CSRF | POST orders write | 201 |
| POST /api/orders, writer, missing CSRF | Blocked earlier by CsrfFilter | 403, not proof of wrong write rule |
| POST /api/orders, reader + CSRF | POST orders write | 403, missing SCOPE_orders.write |
| DELETE /api/orders/42, writer + CSRF | Orders fallback denyAll | 403 |
| GET /api/admin/metrics, admin | Admin role | 200 |
| GET /api/admin/metrics, reader | Admin role | 403 |
| GET /api/profile, reader | GET profile | 200 |
| GET /undocumented, reader | anyRequest denyAll | 403 |

These expected statuses are tied to the **sample config**, including HTTP Basic and CSRF. In another application, the authentication entry point may redirect instead of returning 401, or exception handling may return JSON; the authorization criterion remains granting/denying according to policy.

### 8.7. Commands to Run

In the project directory with Java 17+ and a compatible Gradle version:

~~~bash
gradle test
gradle bootRun
~~~

If using the wrapper:

~~~bash
./gradlew test
./gradlew bootRun
~~~

On Windows use `gradlew.bat test` and `gradlew.bat bootRun`. This is a project with Spring Boot libraries; running bare `javac/java` without providing the full classpath will not compile.

When the application is running on the default port, you can test GET endpoints:

~~~bash
curl -i http://localhost:8080/api/public/ping
curl -i http://localhost:8080/api/orders/42
curl -i -u reader:reader-pass \
  http://localhost:8080/api/orders/42
curl -i -u reader:reader-pass \
  http://localhost:8080/api/admin/metrics
curl -i -u admin:admin-pass \
  http://localhost:8080/api/admin/metrics
~~~

The `curl -u` lines use test credentials; **never use this approach with production passwords to avoid exposing them in shell history/process lists**. In production you must use HTTPS. To test POST with CSRF, use MockMvc as in the tests or design a client that sends a valid token; do not disable CSRF just because an HTTP Basic request returned 403.

## 9. Debugging Rule Order in a Real System

A bug report often looks like: "Regular users can access admin APIs" or "Public API gets 401/403". Do not fix by guesswork; analyze each level.

### 9.1. Identify the Selected Chain

If there are multiple `SecurityFilterChain`s:

1. List the chain beans and their actual `@Order`.
2. Check each chain's `securityMatcher` against the request path/method/servlet path.
3. Identify the **first matching chain**. Do not infer from bean variable names or controller locations.
4. Verify whether the chain has `AuthorizationFilter` and the expected authentication mechanism.
5. Verify a fallback chain protects requests not matching specialized chains.

If the right chain is not being selected, changing the order of `requestMatchers` inside **a different chain** will not solve the problem.

### 9.2. Identify the First Matching Authorization Rule

Inside the selected chain:

1. Read the `requestMatchers` list in exact order.
2. For a specific request, evaluate method/path/dispatcher type one by one using the actual matchers.
3. Stop at the **first matching matcher**.
4. Inspect the authorization condition on that rule: `permitAll`, `authenticated`, `fullyAuthenticated`, `hasRole`, `hasAuthority`, `access`, or custom manager.
5. Inspect principal/authorities after authentication.
6. Distinguish rule denial from earlier errors in CSRF, session, token decoder, or account status.

A `hasRole("ADMIN")` rule may be **in the right position**, yet the actual user only has `"ADMIN"` without `"ROLE_ADMIN"` -> 403. A `hasAuthority("SCOPE_orders.read")` rule may fail to match scopes due to JWT converter mapping -> 403. Those bugs are not first-match bugs, yet they produce similar symptoms.

### 9.3. Controlled Logging and Observability

In a learning environment:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Use logs to observe chain/filter/authorization decisions, but do not rely on an exact fixed log line across all Spring Security versions. Avoid TRACE and request body dumping in production if they can expose passwords, session cookies, JWTs, or CSRF tokens.

To confirm rule shadowing, write a test for a request **matching both patterns simultaneously**, using a user who satisfies only the general rule and not the strict rule. If the test grants access, you may have placed the broad rule before the strict rule.

## 10. Checklist for Reviewing Overlapping Rules

A useful pull request review checklist:

| Question | Reason |
| --- | --- |
| Does the new rule overlap an existing rule? | May shadow or be shadowed |
| Does a broad `/api/**` or `/**` rule appear before a specific rule? | May accidentally open or lock endpoints |
| Are method-specific rules present? | Prevents READ authority from being used for WRITE |
| Is there an explicit `anyRequest().denyAll()` fallback? | Protects new endpoints |
| Are there multiple chains where a general chain has higher priority `@Order` than a specialized chain? | General chain may hijack requests |
| Does a `securityMatcher` leave a group of URLs outside every chain? | Requests may go unprotected |
| Do role/authority rules use the right prefix? | Prevents wrong permissions or accidental 403 |
| Do tests include an authenticated user lacking sufficient permission? | Catches an `authenticated()` rule masking `hasRole` |
| Do tests cover requests with other HTTP methods and trailing slashes? | Catches incorrect matcher coverage |
| Are method-level and resource-ownership checks present when needed? | HTTP path rules do not replace object authorization |

### 10.1. What Happens When Adding a New Endpoint?

Suppose currently you have:

~~~java
.requestMatchers("/api/**").authenticated()
.anyRequest().denyAll()
~~~

Tomorrow a developer adds a `POST /api/admin/delete-all` controller but **forgets to add an admin rule**. Because it matches `/api/**`, a regular user's authenticated request can be allowed by HTTP authorization. Having a `denyAll` fallback afterwards **does not fix** this hole because the request already matched the broad rule.

Defenses:

- Add the admin rule before `/api/**`, and test negative cases.
- Prefer whitelisting intentional endpoint/method groups rather than a general authenticated catch-all.
- Place admin groups under a dedicated chain or separate resource policies when multiple authentication mechanisms exist.
- For object-level permissions such as "only edit one's own orders", add method/service authorization and ownership checks; path-based role rules are not enough.

### 10.2. Method Security Does Not Change HTTP First-Match Mechanics

`@PreAuthorize` and method authorization can act as an **independent control layer** alongside HTTP authorization. If HTTP lets a request through, method security may still deny it at the service/controller call depending on configuration. However, do not use method security as an excuse to allow overly broad HTTP rules and skip tests.

**First-match in the `authorizeHttpRequests` list does not mean Spring Security skips all other authorization layers of the application.** It only describes how a rule is selected in one HTTP authorization manager configuration; other filters, controller logic, and method-level authorization still apply.

### 10.3. Error/Forward Dispatches and Multi-Servlet

Request dispatcher types such as `ERROR` or `FORWARD` may pass through security rules depending on Servlet dispatch mechanics and how Spring Security registers filters. A `denyAll` fallback can cause error pages or forwarded views to be blocked in some apps. When needed, create a policy for appropriate dispatcher types **after understanding the threat model**, rather than opening all URLs just because you saw a 403 in an error flow.

Example snippet (apply only if the application genuinely needs to allow these dispatch types):

~~~java
.dispatcherTypeMatchers(DispatcherType.FORWARD, DispatcherType.ERROR)
    .permitAll()
~~~

Requires importing `jakarta.servlet.DispatcherType`. Place this rule intentionally in the list; it still obeys **first-match**, not an automatic exception with higher priority than all other rules.

If the application has multiple Servlets or a custom servlet path, identify the right matcher type and use the exact builder/request matcher for the path scope. A string pattern that looks right is not guaranteed to match servlet mappings; test on the real app.

## 11. Common Mistakes

### 11.1. "Spring picks the most specific rule"

**False.** This is confusion with some other routing/cascade systems. `authorizeHttpRequests` evaluates request rules in declaration order; you must order them back-to-front properly and test.

### 11.2. "The first rule denied so the framework tries the next rule"

**False.** Matching selects the rule; the grant/deny decision happens in that rule. A denial does not fall through to an easier rule.

### 11.3. "Putting anyRequest denyAll at the end is enough to protect admin"

**Not enough** if `"/api/**".authenticated()` earlier already covers admin URLs. The fallback is not evaluated for requests that already matched.

### 11.4. "Adding hasRole after authenticated will tighten access"

**False** if both matchers overlap and `authenticated` comes first. Place strict rules first or redesign the patterns.

### 11.5. "There is only one first-match order in the whole application"

**False** when there are multiple `SecurityFilterChain`s. There is also chain selection by `@Order` and `securityMatcher` before HTTP rule selection.

### 11.6. "Having @GetMapping means Spring Security will only check GET"

**False.** HTTP authorization matchers are separate rules; if you put a path-only matcher and another controller supports POST on the same path, the policy may fail to block POST. Specify the method in the matcher when permissions differ by method.

### 11.7. "A 403 is always caused by a missing role"

**False.** CSRF, method mismatch, custom access decisions, or other entry points can cause 403. Analyze the filter chain, request method, token, and rules.

### 11.8. "Having requestMatcher denyAll in a chain protects the whole site"

**False** if the chain has a `securityMatcher` covering only one group of URLs. A fallback chain/default deny across the entire intended scope is needed.

### 11.9. "An authenticated user is enough for every read/write API"

Incorrect when the business requires scopes, resource ownership, tenant checks, or recent authentication. `authenticated()` is only an authentication requirement, not a full authorization model.

### 11.10. "Reordering rules is just a formatting refactor"

Incorrect when order changes. Moving a rule can alter actual access rights. Code review must treat order changes as **security behavior** changes, accompanied by regression tests.

## 12. Practice Exercises

1. With `/api/**.authenticated()` before `/api/admin/**.hasRole("ADMIN")`, can an authenticated user without `ROLE_ADMIN` pass the HTTP authorization step for `GET /api/admin/audit`? Explain first-rule matching.
2. If `denyAll()` for `/api/**` is placed before `permitAll()` for `/api/public/**`, why is the public API blocked?
3. Among the three rules for GET orders, POST orders, and orders fallback `denyAll`, which matcher selects `DELETE /api/orders/42`?
4. Why can `POST /api/orders` by `writer` with the right scope still get 403 when missing a CSRF token? Does that result prove the scope check is wrong?
5. Explain the difference between `@Order(1)` on a chain bean and the order of `requestMatchers` inside a chain.
6. With an admin chain matcher `/api/admin/**` and a general API chain matcher `/api/**`, what happens if the general chain has higher priority order?
7. If a request matches no `SecurityFilterChain`, does `anyRequest().denyAll()` in the separate `/api/**` chain protect it?
8. Write a test matrix for anonymous, reader, writer, and admin across at least six endpoints with different scopes; mark the first matching matcher and expected response.
9. Fix the bad config with `/api/**.permitAll()` so `/api/admin/**` is admin-only and `/api/public/**` stays public.
10. A developer adds `POST /api/orders/42/cancel`. If the existing read rule omits `HttpMethod`, what risk can arise?
11. Why can HTTP authorization path rules not replace checking `order.ownerId == principal.id`?
12. Use a MockMvc test to prove `hasRole("ADMIN")` checks `ROLE_ADMIN` by default rather than literal `ADMIN`.
13. Distinguish a chain selection bug, a rule selection bug, and a missing user authority error after token authentication.
14. Test the necessary path/trailing slash/encoding variants before using wildcard matchers in a real API.
15. With `anyRequest().denyAll()`, can a user receive 403 before a non-existent controller returns 404? Explain filter/controller ordering.
16. Why can replacing `authenticated()` with `fullyAuthenticated()` affect remember-me authentication?
17. When an application uses ERROR/FORWARD dispatches, how do you allow only the needed dispatch types without opening every path?
18. Code review catches a new broad-path `permitAll()` rule inserted at the top of the list: what regression tests are needed?
19. If an API supports both API keys and JWTs, in what order should `securityMatcher`/chains be arranged to prevent a credential on one endpoint from becoming a bypass on another?
20. Write a small decision table showing for each request: first matching chain, first matching HTTP rule, condition, principal authorities, and outcome.

## 13. Review and Production Checklist

- [ ] List the exact order of `SecurityFilterChain` beans and `securityMatcher`s.
- [ ] Have a fallback chain protecting requests outside specialized chains.
- [ ] List `requestMatchers` in actual order inside each chain.
- [ ] Specific/strict rules precede broader overlapping rules.
- [ ] `anyRequest()` sits at the end and expresses an intentional default policy.
- [ ] Do not rely on "most specific path wins automatically" or "deny falls back to the next rule".
- [ ] Method-specific rules apply to read/write/delete when permissions differ.
- [ ] Have tests blocking access for authenticated users lacking roles/scopes.
- [ ] Have tests for public, admin, normal user, unsupported methods, and unknown paths.
- [ ] Separate CSRF tests from authorization tests on unsafe methods.
- [ ] User roles/authorities have correct prefixes/mappings from `AuthenticationProvider`/token converters.
- [ ] Multi-tenant/resource ownership is checked beyond path-based rules when needed.
- [ ] New endpoints are not automatically opened by an overly broad `/api/**` matcher.
- [ ] Have regression tests when changing rule order or chain `@Order`.
- [ ] Verify Servlet dispatcher types and path matching behavior in the real application.
- [ ] Do not disable other security filters to "fix" a first-match bug.
- [ ] Security logs do not expose passwords, Authorization headers, session cookies, or CSRF tokens.

## 14. Conclusion

In Spring Security Servlet, **order is part of the security policy**. When using multiple `SecurityFilterChain`s, the framework picks the **first chain whose securityMatcher matches**. Inside that chain, `authorizeHttpRequests` picks the **first rule whose requestMatcher matches** and uses that rule's authorization condition to allow or deny. **If a rule matches and denies, the framework does not look for another rule to let it through.**

A memorable implementation principle: **specific first, general later, explicit default deny, and negative tests for every permission group**. Test method/path, chain order, role/scope, and CSRF, because a single misplaced matcher line can expose a sensitive endpoint even when every individual line looks reasonable.
