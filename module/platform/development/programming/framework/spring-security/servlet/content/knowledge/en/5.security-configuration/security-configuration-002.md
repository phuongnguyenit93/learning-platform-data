# `securityMatcher` and `requestMatchers`: Selecting a Chain vs. Selecting a Rule

## 1. Problem to solve

In a Spring Security application running on the **Servlet stack** (Spring MVC, Tomcat, or an equivalent Servlet container), many developers see that both `securityMatcher("/api/**")` and `requestMatchers("/api/**")` accept a path pattern and assume they are interchangeable. In reality, **the two calls control two different stages of request processing**:

- **`HttpSecurity.securityMatcher(...)`** decides **whether an entire `SecurityFilterChain` applies to the request**. It sets the operating scope for the whole filter chain, including authentication mechanisms, authorization, CSRF, login/logout, and the corresponding filter configurations.
- **`authorizeHttpRequests(auth -> auth.requestMatchers(...))`** decides **which authorization rule applies inside the already-selected chain**. It only takes effect once `FilterChainProxy` has selected the chain containing that rule.

Confusing the two can cause serious bugs: endpoints outside `securityMatcher` are left unprotected by any chain; `permitAll` configurations have no effect; requests are handled by the wrong login mechanism; or a broad chain shadows a specialized chain.

Lesson objectives:

1. Read the processing order: **select chain → run filters → select authorization rule → allow/deny**.
2. Write single-chain and multi-chain configurations with `@Order`, properly scoped matchers, and clear fallback rules.
3. Accurately analyze which chain and rule a given request hits, including when deny rules exist or two chains overlap.
4. Recognize why `permitAll()`, `anyRequest()`, `securityMatcher()`, HTTP method, and CSRF have different scopes.
5. Write tests so no route is missed when new endpoints are added to the application.

## 2. Two levels of selection in Servlet security

A Servlet request typically follows this flow:

```text
HTTP request
    |
Servlet container
    |
DelegatingFilterProxy ("springSecurityFilterChain")
    |
FilterChainProxy
    |-- checks SecurityFilterChains in priority order
    |     |
    |     +-- first chain with a matching securityMatcher
    |             |
    |             +-- executes filters in the selected chain
    |                    |
    |                    +-- authentication / context / CSRF / ...
    |                    |
    |                    +-- AuthorizationFilter
    |                           |
    |                           +-- selects the first matching requestMatchers
    |                           +-- applies permitAll/authenticated/hasRole/denyAll...
    |                                    |
    +------------------------------------+--> controller if allowed
```

`DelegatingFilterProxy` bridges the Servlet container and the Spring Security bean. `FilterChainProxy` holds multiple `SecurityFilterChain`s, checks their matchers in order, and uses the **first matching chain**. Once a request enters a chain, Spring Security **does not automatically try the next chain** if the request is rejected due to missing permissions, CSRF, or authentication.

Inside that chain, `AuthorizationFilter` uses the rules configured by `authorizeHttpRequests`. The **first matching rule** decides the authorization outcome. A request can be blocked **before reaching** authorization (for example, the CSRF filter rejects a POST without a token). Therefore, the authorization rule table is not the entirety of a request's security checks.

### Comparison table

| Question | `http.securityMatcher(...)` | `authorizeHttpRequests(...requestMatchers(...))` |
| --- | --- | --- |
| Where is it called? | On `HttpSecurity` for a `SecurityFilterChain` bean | Inside the `authorizeHttpRequests` rule set of a chain |
| Purpose | Choose **whether to run this chain** | Choose **which authorization rule** applies once the chain runs |
| What is affected | All security filters of the chain | Allow/deny decision at the authorization layer |
| When not matched | `FilterChainProxy` tries the next chain | Tries the next rule **within the same chain** |
| When matched but denied | Does not fall back to another chain | Request is denied; does not fall through to later rules |
| What is `anyRequest()`? | Not a replacement matcher for full chain coverage | A rule catching all requests **that entered the current chain** |
| Typical uses | Partitioning API, web app, actuator, protocol-specific endpoints | Public/private, GET/POST, roles, authorities |
| Typical mistake | Forgetting a fallback chain, leaving endpoints without security filters | Thinking a rule protects URLs outside the chain's scope |

Both mechanisms rely on `RequestMatcher`; the difference lies in **where the matcher is evaluated**. Similar method names do not give them the same role.

## 3. Default of a `SecurityFilterChain` and `anyRequest()`

Consider a single-chain configuration:

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/**").permitAll()
            .requestMatchers("/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

This is an **illustrative configuration snippet**; it needs appropriate imports and must be placed in a `@Configuration` class. Because `securityMatcher` is not called, the chain-level matcher matches every request by default. Requests entering the chain are evaluated against the rules: `/public/**` is permitted; `/admin/**` requires `ROLE_ADMIN`; the rest require authentication.

Conversely:

```java
@Bean
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
```

The second chain **exists only for requests matched by `/api/**`**. `anyRequest().authenticated()` means "every remaining request **in this API chain**", and definitely does not mean "every path in the application".

A request `GET /admin/users` is **not** protected by the API chain above. If the application defines no other chain matching it, the request proceeds **without the security filters of any `SecurityFilterChain`**. A project that declares its own `SecurityFilterChain` bean should also not rely on Spring Boot auto-creating a fallback chain with a desired policy.

### Quick rules to remember

- `securityMatcher` creates the **chain boundary**.
- `requestMatchers` inside `authorizeHttpRequests` creates the **rule boundary**.
- `anyRequest()` at the end of a rule set catches the rest **within the scope of the current chain**.
- Not matching a chain is not the same as **being denied**. Missing a fallback chain can create a vulnerability; `denyAll()` inside a chain only denies requests **already selected into that chain**.

## 4. Multiple chains: selected by order, not by "specificity"

Suppose an application needs different protection mechanisms for API and web parts. We define:

```text
@Order(1) API chain:
    securityMatcher("/api/**")
    - GET /api/public   -> permitAll
    - GET /api/profile  -> authenticated
    - GET /api/admin    -> hasRole("ADMIN")
    - remaining in /api/** -> denyAll

@Order(2) Web fallback chain:
    default securityMatcher: every request
    - GET /home         -> permitAll
    - GET /account      -> authenticated
    - remaining         -> denyAll
```

When a request arrives, `FilterChainProxy` checks `@Order(1)` then `@Order(2)`. For `/api/profile`, the API chain matches so the web chain has no chance to run. For `/home`, the API chain does not match, so the web chain handles it.

**Do not trust the framework to automatically pick a "more specific" matcher.** Chain priority order is determined by `@Order` (or equivalent configuration order). A match-all chain placed before the API chain can shadow the entire API chain.

```text
WRONG:
  @Order(1) default chain matching every request
  @Order(2) /api/** chain                 <-- never selected

RIGHT:
  @Order(1) /api/** chain
  @Order(2) default chain matching every request
```

With `@Order`, lower numbers have higher priority. Putting a final chain with a default matcher matching every request is one way to guarantee there are no gaps. When you have multiple chains, give beans meaningful names, state priorities explicitly, and test overlapping URLs.

## 5. Complete example: Spring Boot 3.x, Spring MVC, Java 17+

The example below uses **HTTP Basic for illustration** on both chains, focusing on chain/rule selection. Real applications may use different authentication mechanisms across chains. The code uses Java 17+, Spring Boot 3.x, and Spring Security 6.x; it is not an out-of-the-box configuration for WebFlux.

With a Spring Boot project that already has build plugins and dependency management, add:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
```

Create `src/main/java/example/matchers/ChainMatcherDemoApplication.java`:

```java
package example.matchers;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ChainMatcherDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ChainMatcherDemoApplication.class, args);
    }
}

@Configuration
class SecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/profile").authenticated()
                .requestMatchers(HttpMethod.GET, "/api/admin").hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        return http
            // No securityMatcher -> default matcher matches every request.
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/home").permitAll()
                .requestMatchers(HttpMethod.GET, "/account").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("demo-reader"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("demo-admin"))
            .roles("USER", "ADMIN")
            .build();

        return new InMemoryUserDetailsManager(reader, admin);
    }
}

@RestController
class DemoEndpoints {

    @GetMapping("/api/public")
    String apiPublic() {
        return "api public";
    }

    @GetMapping("/api/profile")
    String apiProfile(Authentication authentication) {
        return "api profile: " + authentication.getName();
    }

    @GetMapping("/api/admin")
    String apiAdmin() {
        return "api admin";
    }

    @GetMapping("/home")
    String home() {
        return "web home";
    }

    @GetMapping("/account")
    String account(Authentication authentication) {
        return "web account: " + authentication.getName();
    }
}
```

For Java to allow all three top-level classes in a single file, only `ChainMatcherDemoApplication` is declared `public`; the other two classes are package-private. Spring Boot scans the `example.matchers` package and registers `@Configuration` and `@RestController`.

In this configuration:

- `apiChain` has **chain matcher** `/api/**`. All of its rules evaluate only requests that entered the API scope.
- `webChain` does not call `securityMatcher`, so it uses the default matcher matching every request. It is the **fallback chain** for URLs outside API.
- Both chains use HTTP Basic, so in this demo, an unauthenticated client calling a login-required endpoint typically gets `401`; an authenticated user lacking permission typically gets `403`.
- `.roles("ADMIN")` creates the authority `ROLE_ADMIN`, which matches `hasRole("ADMIN")`. If `hasAuthority("ADMIN")` were used instead, the match would differ.
- `PasswordEncoder` encodes demo passwords before storing them in memory. Hardcoded usernames/passwords are for learning only. Real environments need TLS/HTTPS and an appropriate identity management system.
- All demo endpoints are **GET**; default CSRF protection remains enabled. Do not infer that this configuration freely allows POST/PUT/DELETE without a CSRF token when an authentication mechanism relies on browser-sent credentials.

To run in a suitable Spring Boot Gradle project, use:

```bash
./gradlew bootRun
```

On Windows PowerShell you can run `./gradlew.bat bootRun`. After the application starts on HTTP port 8080 in your **local** environment, try:

```bash
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/profile
curl -i -u reader:demo-reader http://localhost:8080/api/profile
curl -i -u reader:demo-reader http://localhost:8080/api/admin
curl -i -u admin:demo-admin http://localhost:8080/api/admin
curl -i http://localhost:8080/home
curl -i http://localhost:8080/account
curl -i -u reader:demo-reader http://localhost:8080/account
```

**Expected results** (status/body are what matter; ignore HTTP headers and header order, which can differ across versions/environments):

| Request | Selected chain | Selected rule | Result |
| --- | --- | --- | --- |
| `GET /api/public`, anonymous | API | `permitAll` | 200, `api public` |
| `GET /api/profile`, anonymous | API | `authenticated` | 401 (HTTP Basic challenge) |
| `GET /api/profile`, reader | API | `authenticated` | 200, `api profile: reader` |
| `GET /api/admin`, reader | API | `hasRole("ADMIN")` | 403 |
| `GET /api/admin`, admin | API | `hasRole("ADMIN")` | 200, `api admin` |
| `GET /home`, anonymous | Web fallback | `permitAll` | 200, `web home` |
| `GET /account`, anonymous | Web fallback | `authenticated` | 401 (HTTP Basic challenge) |
| `GET /account`, reader | Web fallback | `authenticated` | 200, `web account: reader` |

Note that these are **expected results from the code**, not stdout captured from an actual run. To verify which chain each request enters, besides checking status codes, you can temporarily enable Spring Security logging in a development environment.

## 6. Analyzing each request: at which exact step?

### Scenario A — `GET /api/public`

1. `FilterChainProxy` checks the `@Order(1)` chain: `/api/**` matches `/api/public`.
2. The API chain is selected; the web chain **is not considered further**.
3. Security filters in the API chain process the request; then authorization evaluates the `GET /api/public` rule.
4. `permitAll` allows the request without authentication, yet it is still a request traversing the API chain.
5. The controller returns `api public`.

If you add `/api/public` to `requestMatchers(...).permitAll()` of the **web chain** while omitting the corresponding rule in the API chain, this request still enters the API chain first; the rule in the web chain never affects it.

### Scenario B — `GET /api/admin` as reader

1. Selects the API chain via `securityMatcher("/api/**")`.
2. HTTP Basic authentication succeeds with authority `ROLE_USER`.
3. The `GET /api/admin` rule requires `ROLE_ADMIN`; the user does not meet it.
4. The request is denied (in this configuration typically 403). **It does not try the web chain**, even though the web chain has a default matcher covering all URLs.

This proves "did not match chain so try next chain" is **different** from "matched chain but lacked permission so try next chain".

### Scenario C — `GET /home`

The API chain does not match, so `FilterChainProxy` checks the web chain, where the `GET /home` rule yields `permitAll`. The `/home` path never enters filters configured exclusively in the API chain.

### Scenario D — `GET /api/unknown`

The API chain matches, but there is no specific rule for `GET /api/unknown`. `anyRequest().denyAll()` **inside the API chain** catches this request. Even if the caller is authenticated, access is denied. The presence of the web chain does not let the request "escape" the API's `denyAll` policy.

### Scenario E — `POST /api/public`

The API chain still matches `/api/**`. However, the public rule in the example is only for **GET**. POST does not match that rule; at the same time, the CSRF filter may reject POST before authorization if a token is missing. Therefore **do not infer** an endpoint is public for all HTTP methods merely because `GET /api/public` allows anonymous access.

## 7. How much does the order of `requestMatchers` matter?

Within a chain, `authorizeHttpRequests` rules are evaluated in definition order. A broad rule placed earlier can swallow a specific rule placed later.

Inaccurate example:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").authenticated()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().denyAll()
)
```

Because `/api/admin/users` already matches `/api/**`, the `hasRole("ADMIN")` rule after it **is never used**. The right placement prioritizes narrow rules:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll()
)
```

This is an **illustrative configuration snippet** to place inside an appropriately scoped `HttpSecurity`. Note that `anyRequest()` must normally be the **final rule**; after declaring a rule catching all requests, adding new rules afterward is nonsensical and can be rejected by the framework at configuration build time.

How to check visually when reading code:

- First determine: **does a chain cover the request?**
- Inside the chain, read the rules **top to bottom**; find the first rule matching path, method, and matcher condition.
- Once a matching rule is found, stop searching other rules; check authentication, authorities, and other protective filters.
- If the last rule is `denyAll()`, a forgotten route will be denied; if the last is `authenticated()`, every route in the chain not separately declared requires login; if the last is `permitAll()`, you must explain why open-by-default is intentional.

## 8. Servlet matcher boundaries: path, HTTP method, and dispatcher

Both APIs can accept many kinds of `RequestMatcher`; string-pattern overloads can select matchers appropriate for the Spring MVC/Spring Security environment, so you should not assert every pattern always follows a single mechanism. When an application has multiple Servlets, custom servlet paths, or separate dispatcher configurations, use appropriate explicit matchers and test with real URLs.

Details easily overlooked:

1. **HTTP method:** `requestMatchers(HttpMethod.GET, "/api/profile")` differs from `requestMatchers("/api/profile")` (which is not restricted to GET). Policies for POST/PUT/PATCH/DELETE must be defined intentionally.
2. **Context path and Servlet path:** MVC `RequestMatcher`s typically evaluate paths relative to the corresponding Servlet context. Do not mistakenly concatenate `server.servlet.context-path` into patterns or assume `/api/**` always covers every path when an application has multiple servlets.
3. **The root path itself:** If you want both `/api` and `/api/**`, specify and test both. Do not guess how every matcher type handles trailing slashes, suffixes, or path variables.
4. **Dispatcher type:** A request can go through `REQUEST`, `FORWARD`, `ERROR`, `ASYNC`; error view routes or internal forwards may need appropriate rules. Do not open all dispatcher types merely to avoid a 403 without understanding the data boundary.
5. **Framework-generated paths:** Login, logout, OAuth callbacks, Swagger/UI, `/error`, static assets, or health endpoints may fall outside the `securityMatcher` you intended. For form login, the login page and login processing URLs must belong to a chain with the right filter and be granted access as designed.
6. **`securityMatcher` scopes the entire filter chain:** If the API chain uses `httpBasic` while the web chain uses `formLogin`, which chain a URL falls into also determines the authentication entry point/redirect and which security filters run.

Specifically for request matching, Spring Security typically provides matchers integrated with Spring MVC as well as explicit matchers. In complex Servlet setups, do not rely on overload names or generic assumptions about `Ant`/`MVC` to guarantee behavior; test actual routes against your application's stack and version.

## 9. Why is `permitAll()` different from bypassing the filter chain?

Two ways of opening an endpoint are not equivalent:

```java
// Still inside the chain, only allows passing the authorization step.
.requestMatchers("/public/**").permitAll()
```

versus a design that causes requests **not to match any chain** (or ignores security filters via web ignoring). With `permitAll`, the remaining filters of the chain can still run, such as filters setting HTTP security headers, handling CSRF, authentication, or custom filters.

Therefore, for public resources still served through an application with Spring Security, **`permitAll()` inside a covering chain** is generally preferred. If `securityMatcher` is too narrow without a fallback, a public endpoint can accidentally miss expected headers or common protections. Do not rely on "this page is public" to skip other HTTP protection layers.

In particular, `permitAll()` **does not automatically disable CSRF**. A POST route permitted by authorization still needs a CSRF token if CSRF configuration applies. For APIs using standalone bearer tokens rather than browser-sent cookies, CSRF may be designed differently, but you must evaluate credential and client types before deciding.

## 10. What if each chain uses a different login mechanism?

Splitting `SecurityFilterChain`s helps when API and browser UI truly have **different filter configurations**. For example:

```text
API /api/**:
  - bearer token or HTTP Basic as required
  - appropriate 401/403 API responses
  - session/CSRF policies considered separately

Browser UI /app/** or fallback:
  - form login or OAuth2 login
  - cookie/session and CSRF token
  - redirect to login page and appropriate logout
```

In that case, selecting the right chain is the step that determines **which authentication mechanism is present**. Adding `requestMatchers("/api/**").authenticated()` to the web chain **does not create** an API chain or switch to bearer-token authentication.

If an API chain only matches `/api/**` while the login page is at `/login`, make sure another chain actually handles `/login` and the login processing endpoint. A common mistake is defining an overly narrow chain scope while expecting that chain's login filter to serve a path outside its scope.

When multiple `SecurityFilterChain`s are needed, each chain should clearly document:

- `securityMatcher`: which requests belong to the chain;
- `@Order`: at what position the chain is evaluated;
- authentication: Basic, form login, OAuth2 resource server, or another mechanism;
- authorization: ordered `requestMatchers` and the final `anyRequest` rule;
- CSRF/session/CORS/headers: policies matching the right client type;
- technical endpoints: login, logout, error, health, static assets, and callbacks.

## 11. Automated testing to prove chains and rules

Do not test only that `GET /api/public` returns 200. A small change in `@Order` can cause the wrong chain to catch requests. For the example project above, add the test dependencies:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Create `src/test/java/example/matchers/SecurityChainsTest.java`:

```java
package example.matchers;

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
class SecurityChainsTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicApiWorksWithoutCredentials() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("api public"));
    }

    @Test
    void apiRequiresLogin() throws Exception {
        mvc.perform(get("/api/profile"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void ordinaryUserCannotEnterAdminEndpoint() throws Exception {
        mvc.perform(get("/api/admin").with(httpBasic("reader", "demo-reader")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanEnterAdminEndpoint() throws Exception {
        mvc.perform(get("/api/admin").with(httpBasic("admin", "demo-admin")))
            .andExpect(status().isOk())
            .andExpect(content().string("api admin"));
    }

    @Test
    void webFallbackStillProtectsAccount() throws Exception {
        mvc.perform(get("/account"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/account").with(httpBasic("reader", "demo-reader")))
            .andExpect(status().isOk())
            .andExpect(content().string("web account: reader"));
    }

    @Test
    void unknownApiRouteIsDeniedToAuthenticatedUser() throws Exception {
        mvc.perform(get("/api/unknown").with(httpBasic("reader", "demo-reader")))
            .andExpect(status().isForbidden());
    }
}
```

Run in a project with the Gradle wrapper:

```bash
./gradlew test
```

This is **proposed test code**, not verified run output recorded in this document. `MockMvc` executes the application's Spring Security configuration in the test environment, helping catch rule and chain bugs. To verify a specific filter chain at runtime, enable debug logging only in a development environment:

```yaml
logging:
  level:
    org.springframework.security: DEBUG
```

Observe the matchers and filters in the logs, then turn off debug when no longer needed. Security logs can expose sensitive request metadata; never intentionally log raw tokens or passwords for debugging.

### Test matrix needed as the application grows

| Test layer | Key scenarios |
| --- | --- |
| Chain selection | URLs under `/api/**`; outside `/api/**`; boundary URL `/api`; fallback chain |
| Authorization rules | Anonymous, regular user, admin; narrow vs. broad rules; final rule |
| HTTP methods | GET vs. POST/PUT/DELETE; whether 405/403 has the right cause |
| CSRF and login | Cookie/browser POST with CSRF token; API credential mode; login/logout in the right chain |
| Failure behavior | 401/403/redirect per authentication mechanism, without falling through to another chain |
| Auxiliary resources | `/error`, health, assets, callbacks, Swagger/UI if the application actually uses them |
| Domain-level permissions | Logged-in user unable to view another user's data |

Status 401, 403, or redirect also depends on the configured authentication entry point, access denied handler, and CSRF. When a test does not match expectations, investigate which filter produced the response before changing matchers.

## 12. Common mistakes and fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using `securityMatcher("/api/**")` and assuming `anyRequest()` protects web too | Routes outside API may lack a covering chain | Add a fallback `SecurityFilterChain` matching every request |
| Putting the match-all chain first | Specialized chains are never selected | Use `@Order` so narrow chains are evaluated first |
| Adding `requestMatchers("/admin/**")` to a chain matching only `/api/**` | Rule can never apply to `/admin/**` | Place the rule in the chain that actually covers that URL |
| Putting `/api/**` before `/api/admin/**` in one chain | Broad rule shadows admin rule | Place narrow rules above broad ones |
| Thinking `permitAll()` skips all filters | Surprise 403 CSRF on POST | Distinguish authorization from CSRF/filter protection |
| Assuming 403 in the first chain tries the next chain | Misjudging security scope and misdebugging | Remember **first matching chain** selection |
| Not testing HTTP methods | GET is public while POST is blocked or hits another rule | Set method-specific matchers and test independently |
| Using form login in a narrow chain while login path is outside scope | Broken login page/processing endpoint | Design matchers to include login or use an appropriate chain |
| Omitting fallback thinking Boot will add one | New endpoints are not protected as intended | Explicitly define a catch-all chain and final policy |
| Reading only `requestMatchers` without checking the enclosing chain | Misreading which URLs a rule actually governs | Always trace from `securityMatcher` and `@Order` first |

## 13. Practice exercises

**Exercise 1.** Two chains are declared:

```text
@Order(1) securityMatcher("/internal/**")
          requestMatchers("/internal/admin/**").hasRole("ADMIN")
          anyRequest().authenticated()

@Order(2) default matcher for every request
          requestMatchers("/public/**").permitAll()
          anyRequest().denyAll()
```

For `GET /internal/admin/settings` by a user with `ROLE_USER`, which chain/rule is selected? Will the request be retried on chain 2?

**Answer:** Chain 1 and rule `hasRole("ADMIN")` are selected; the user lacks permission and is denied. Chain 2 is not retried.

**Exercise 2.** With the two chains above, which chain processes `GET /public/info` for an anonymous caller? **Answer:** Chain 1 does not match; chain 2 matches and `permitAll` applies to `/public/**`.

**Exercise 3.** If `@Order(1)` is changed to a chain catching all URLs and `/internal/**` is moved to `@Order(2)`, what happens? **Answer:** The catch-all chain is selected first, so the dedicated `/internal/**` chain is never used; to separate policies you must swap the order or scope.

**Exercise 4.** An API chain has `securityMatcher("/api/**")` with no fallback. Name two things you must do before deployment. **Answer:** Define and configure a chain covering all other URLs needing protection; test out-of-scope routes and boundary routes to prove they do not slip past security filters.

**Exercise 5.** Why is `requestMatchers("/api/open").permitAll()` not enough to guarantee a browser POST succeeds? **Answer:** Authorization `permitAll` does not disable CSRF; other filters can block POST and matcher rules may be restricted by HTTP method.

**Core principle:** `securityMatcher` selects the **entire filter chain** for a request; `requestMatchers` inside `authorizeHttpRequests` selects the **authorization rule** within that chain. When evaluating whether a URL is secure, always inspect both levels in order and prove them with real tests.
