# Missed Endpoints Due to `securityMatcher`, `@Order`, or Missing Fallback Chain

## 1. Why Can an Endpoint Be Left Unprotected by Spring Security?

In **Spring Security Servlet**, having `spring-boot-starter-security`, a `SecurityFilterChain` bean, or an `.anyRequest().authenticated()` rule **is not enough to guarantee every HTTP request is checked by Spring Security**. When an application defines multiple filter chains, `FilterChainProxy` picks **the first chain** whose `RequestMatcher` matches the request. If **no chain matches**, the request receives none of the Spring Security filters managed by `FilterChainProxy`.

This is a dangerous deployment bug because endpoints still appear to work normally:

- `/api/orders` is protected by HTTP Basic/JWT, yet a newly added `/health/internal` returns `200 OK` without login;
- an `/api/**` chain has strict `authenticated()` rules, yet `/v2/api/orders` does not match `/api/**`;
- two chains match the same URL, and the `@Order(1)` chain permits public access, so the `@Order(2)` role-checking chain never runs;
- an app defines only a chain for `/admin/**`, assuming Spring Boot will automatically add a default chain for all remaining paths.

**Distinguish three outcomes:**

1. **No chain matches:** the request can reach the controller **without passing through Spring Security web filters**, unless another protection layer exists.
2. **A chain matches with `permitAll`:** the request **still traverses a `SecurityFilterChain`**; only authorization permits anonymous access, while other filters can still run.
3. **A chain matches and denies:** Spring Security enforces authentication/authorization and responds via its entry point or handler.

Never guess protection status solely from HTTP 200/401/403/404. Verify **which chain was selected** and **which rule applied**.

## 2. Mental Model: `FilterChainProxy` Selects the First Chain

Picture a three-chain configuration:

```text
HTTP REQUEST
    |
    v
DelegatingFilterProxy / springSecurityFilterChain
    |
    v
FilterChainProxy
    |
    +-- @Order(1) securityMatcher("/admin/**") ?
    |         YES -> use ADMIN chain, STOP checking others
    |         NO  |
    |             v
    +-- @Order(2) securityMatcher("/api/**") ?
    |         YES -> use API chain, STOP checking others
    |         NO  |
    |             v
    +-- @Order(3) match any request ?
              YES -> use FALLBACK chain
              NO  -> NO Spring Security filter chain
```

With `FilterChainProxy`, an HTTP request **never combines filters from multiple matching chains**. It applies only the filters of **the first matching chain**, in configured order.

This yields two rules:

- Narrowly scoped chains should come **before** broader chains when they can overlap.
- Always include a **fallback (catch-all) chain** aligned with app policy if you need every request covered by Spring Security.

For example, an `@Order(1)` chain matching all requests claims chain selection ahead of `@Order(2)` and `@Order(3)` API/ADMIN chains. `hasRole` rules in later chains **never get a chance to run**. This bug is *chain shadowing*.

Meanwhile, a fallback chain does not have to “permit everything”. In security-first systems, the fallback typically uses `anyRequest().denyAll()` or explicit authentication/authorization rules.

## 3. Two Matcher Levels: Selecting a Chain vs. Authorizing Inside a Chain

Spring Security uses similar-looking APIs with very different meanings.

### `http.securityMatcher(...)`

Sets **the condition for an entire `SecurityFilterChain` to participate in handling a request**:

```java
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
```

This is an example snippet inside a `@Configuration` class with proper imports.

With this snippet:

- `/api/orders` normally matches the API chain.
- `/public/info` **does not match the API chain**.
- `.anyRequest().authenticated()` applies **only to requests already routed into the API chain**; it does not protect `/public/info`.

### `authorizeHttpRequests().requestMatchers(...)`

Sets **authorization rules inside an already-selected chain**:

```java
http.securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/public/**").permitAll()
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated());
```

`/api/admin/report` is evaluated against the API chain's rules. `/admin/report` outside `/api/**` **is never seen by these rules**.

### Comparison Table

| Method | Role | Common Mistake |
| --- | --- | --- |
| `securityMatcher("/api/**")` | Selects **the whole `SecurityFilterChain`** | Assuming `anyRequest` afterward protects the entire site |
| `requestMatchers("/api/public/**").permitAll()` | Permits a group of requests **inside the current chain** | Confusing with bypassing filters entirely |
| `anyRequest().authenticated()` | Protects remaining paths **that entered the chain** | Does not protect paths outside `securityMatcher` |
| `anyRequest().denyAll()` | Denies remaining paths **that entered the chain** | Does not run if no chain matches the request |
| `web.ignoring().requestMatchers(...)` | Skips Spring Security's web filter chain for matched URLs | Using on public endpoints that still need security headers or CSRF infrastructure |

In short: **`securityMatcher` is the gate into the chain; `requestMatchers` is the rulebook inside the chain.** They are not interchangeable.

## 4. `@Order` Controls Precedence, Not Permissions

When multiple `SecurityFilterChain` beans exist, `@Order` sets evaluation priority. **Lower** values are checked first:

```java
@Bean
@Order(1)
SecurityFilterChain adminChain(HttpSecurity http) throws Exception {
    return http
            .securityMatcher("/admin/**")
            .authorizeHttpRequests(auth -> auth
                    .anyRequest().hasRole("ADMIN"))
            .build();
}
```

```java
@Bean
@Order(2)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                    .anyRequest().authenticated())
            .build();
}
```

These two separate snippets **are not a complete project**: they need an authentication mechanism, imports, and a fallback chain. They illustrate precedence.

Broken example:

```java
@Bean
@Order(1)
SecurityFilterChain permissiveFirst(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .anyRequest().permitAll())
            .build();
}

@Bean
@Order(2)
SecurityFilterChain protectedApi(HttpSecurity http) throws Exception {
    return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                    .anyRequest().authenticated())
            .build();
}
```

The first chain **has no `securityMatcher` restriction**, so it matches every request by default. `/api/orders` enters the first chain, receives `permitAll`, and the second chain never participates. **Having a strict rule in another bean cannot rescue the endpoint.**

The fix is scoping narrow chains properly, ordering them, and placing a catch-all last:

```text
@Order(1): /admin/**
@Order(2): /api/**
@Order(3): all remaining requests -> denyAll
```

If two chains have overlapping matchers such as `/api/**` and `/api/admin/**`, place `/api/admin/**` first. Whenever matchers overlap without explicit precedence, a simple bean-order refactor can silently change policy.

**Never rely on method declaration order in a Java file** to govern chain selection. In multi-chain configs, declare `@Order` explicitly and write tests proving matching behavior.

## 5. Risk of Omitting a Fallback Chain

Suppose an application declares only:

```java
@Bean
@Order(1)
SecurityFilterChain onlyApi(HttpSecurity http) throws Exception {
    return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                    .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
}
```

If the app also has a controller:

```java
@GetMapping("/internal/export")
String export() {
    return "restricted";
}
```

With no other chain matching `/internal/export`, Spring Security web filters **do not protect that route**. The controller can serve data directly when invoked. This controller snippet illustrates the risk; never expose it publicly in a real API.

A huge misconception: **“Spring Boot automatically adds a default `SecurityFilterChain` for URLs not covered by my custom chains.”** In standard Boot Servlet auto-configuration, once you declare a custom `SecurityFilterChain` bean, Boot's default filter chain auto-configuration **backs off**. Do not expect Boot to plug gaps between your `securityMatcher`s.

That is why you should define an **explicit fallback** and directly test `/some-new-route` outside expected prefixes. When new routes are added, security tests must fail if a route slips past coverage.

### Without a Fallback, 404 Does Not Prove Safety

A request to a path without a controller can return `404 Not Found` even when Spring Security never ran. If a developer adds a controller for that path tomorrow, it can immediately return 200 to anonymous callers. Coverage tests therefore need a **real existing route** or proof that a fallback chain matched; never treat 404 as proof that filters ran.

## 6. Safe Reference Architecture: Narrow Chains, Denying Fallback

An easy-to-reason-about architecture:

| Order | `securityMatcher` | Inner Authorization | HTTP Auth Mechanism |
| --- | --- | --- | --- |
| 1 | `/admin/**` | Must have `ROLE_ADMIN` | Basic demo |
| 2 | `/api/**` | `/api/public/status` public; `/api/reports` requires `ROLE_ANALYST`; rest denied | Basic demo |
| 3 | unrestricted (catch-all) | `anyRequest().denyAll()` | Basic demo |

Placing `denyAll` at the **end of each chain** stops newly added endpoints inside a chain from becoming public accidentally, while the final catch-all ensures every other URL still traverses a `SecurityFilterChain`.

Sample request routing:

```text
GET /admin/panel
    -> ADMIN chain
    -> ROLE_ADMIN required

GET /api/reports
    -> API chain
    -> ROLE_ANALYST required

GET /api/public/status
    -> API chain
    -> permitAll

GET /api/unknown
    -> API chain
    -> denyAll

GET /unlisted
    -> FALLBACK chain
    -> denyAll
```

Even a public URL like `/api/public/status` traverses the filter chain and can still receive other protective filters/mechanisms. `permitAll` is strictly an **authorization decision** for that route, not removing Spring Security from the request.

## 7. Spring Boot 3.3.5 and Java 17: Hands-On Project

The example uses **Spring MVC Servlet** with three `SecurityFilterChain` beans, two test users, HTTP Basic, and MockMvc tests. This code teaches **chain selection/authorization** and is not production configuration:

- `User.withUsername(...)` stores `{noop}` test passwords, unsafe for production.
- HTTP Basic runs on local loopback; real networks require HTTPS and proper credential management.
- Endpoints use GET only to avoid mixing state-changing CSRF mechanics into this chain-routing demo.
- Every undeclared URL is denied; only `/api/public/status` is public.

### 7.1. Project Structure

```text
chain-routing-demo/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/chain/
    │   │   ├── ChainRoutingApplication.java
    │   │   ├── SecurityConfig.java
    │   │   └── DemoController.java
    │   └── resources/application.yml
    └── test/java/demo/chain/
        └── ChainRoutingTest.java
```

Create `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
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

The project needs a Java 17-compatible Gradle wrapper. If missing, install Gradle and generate the wrapper per your build workflow; having `build.gradle` alone does not create an executable `gradlew`.

Create `src/main/resources/application.yml`:

```yaml
server:
  address: 127.0.0.1
  port: 8080
```

Bind to loopback only in this demo, keeping test passwords and non-TLS HTTP Basic off public networks.

### 7.2. Application Entry Class

Create `src/main/java/demo/chain/ChainRoutingApplication.java`:

```java
package demo.chain;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ChainRoutingApplication {
    public static void main(String[] args) {
        SpringApplication.run(ChainRoutingApplication.class, args);
    }
}
```

### 7.3. Three Explicit SecurityFilterChains with a Fallback

Create `src/main/java/demo/chain/SecurityConfig.java`:

```java
package demo.chain;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    UserDetailsService demoUsers() {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password("{noop}demo-only")
                        .roles("ANALYST")
                        .build(),
                User.withUsername("bob")
                        .password("{noop}demo-only")
                        .roles("ADMIN")
                        .build());
    }

    @Bean
    @Order(1)
    SecurityFilterChain adminChain(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/admin/**")
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().hasRole("ADMIN"))
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/api/**")
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(
                                HttpMethod.GET, "/api/public/status")
                                .permitAll()
                        .requestMatchers(
                                HttpMethod.GET, "/api/reports")
                                .hasRole("ANALYST")
                        .anyRequest().denyAll())
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
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
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
```

**Point-by-point explanation:**

1. `adminChain` participates only for `/admin/**`; every request within it requires `ROLE_ADMIN`.
2. `apiChain` participates only for `/api/**`; `/api/public/status` is public and `/api/reports` requires `ROLE_ANALYST`.
3. `anyRequest().denyAll()` inside the API chain prevents a developer from adding `/api/new-secret` and assuming it is protected merely by residing in the API chain.
4. `fallbackChain` has **no** `.securityMatcher(...)`: in this setup it catches every request not claimed by the prior two chains. Put it last with `@Order(3)`.
5. `httpBasic()` provides an authentication mechanism in each chain. If a chain defines authorization rules without an authentication mechanism, 401/403 behavior can diverge from expectations; here each chain configures HTTP Basic to avoid hiding that issue.
6. `SessionCreationPolicy.STATELESS` keeps the demo independent of sessions from prior requests. It does not mean HTTP Basic automatically enforces HTTPS.
7. `.roles("ADMIN")` produces authority `ROLE_ADMIN`. `hasRole("ADMIN")` checks the `ROLE_`-prefixed authority by convention.
8. Spring Boot uses your declared `SecurityFilterChain` beans; ensuring a fallback exists is your responsibility. **Do not wait for Boot to create a fourth chain.**

In production, API resource servers typically use bearer tokens instead of HTTP Basic, yet the rules of chain matching and `@Order` remain identical. A browser/OAuth2 login chain may require `formLogin`/`oauth2Login` while an API chain uses Resource Server; an explicit fallback design is still mandatory.

### 7.4. Controller with Public and Protected Routes

Create `src/main/java/demo/chain/DemoController.java`:

```java
package demo.chain;

import java.security.Principal;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/api/public/status")
    public Map<String, String> status() {
        return Map.of("status", "ok");
    }

    @GetMapping("/api/reports")
    public Map<String, String> reports(Principal principal) {
        return Map.of(
                "report", "quarterly",
                "requestedBy", principal.getName());
    }

    @GetMapping("/admin/panel")
    public Map<String, String> admin(Principal principal) {
        return Map.of(
                "panel", "admin",
                "requestedBy", principal.getName());
    }

    @GetMapping("/unlisted")
    public Map<String, String> unlisted() {
        // Real controller present to prove fallback denies it.
        return Map.of("secret", "should-not-be-public");
    }
}
```

`/unlisted` intentionally exists in MVC yet **is not permitted by any specialized chain**. Without a fallback, requests go straight to the controller; with the fallback in place, requests are denied before the controller responds. This route exists solely for local demonstration/testing; never place real secrets here.

## 8. Testing with MockMvc Through Real SecurityFilterChains

Create `src/test/java/demo/chain/ChainRoutingTest.java`:

```java
package demo.chain;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ChainRoutingTest {

    @Autowired
    MockMvc mvc;

    @Test
    void apiPublicStatusWorksWithoutLogin() throws Exception {
        mvc.perform(get("/api/public/status"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("ok"));
    }

    @Test
    void apiReportsRequiresAuthentication() throws Exception {
        mvc.perform(get("/api/reports"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void analystCanReadReports() throws Exception {
        mvc.perform(get("/api/reports")
                        .with(httpBasic("alice", "demo-only")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.requestedBy").value("alice"));
    }

    @Test
    void adminWithoutAnalystRoleCannotReadReports()
            throws Exception {
        mvc.perform(get("/api/reports")
                        .with(httpBasic("bob", "demo-only")))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminPanelRequiresAuthentication() throws Exception {
        mvc.perform(get("/admin/panel"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void adminCanOpenAdminPanel() throws Exception {
        mvc.perform(get("/admin/panel")
                        .with(httpBasic("bob", "demo-only")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.requestedBy").value("bob"));
    }

    @Test
    void analystCannotOpenAdminPanel() throws Exception {
        mvc.perform(get("/admin/panel")
                        .with(httpBasic("alice", "demo-only")))
                .andExpect(status().isForbidden());
    }

    @Test
    void unlistedRouteRequiresProtectionEvenThoughItExists()
            throws Exception {
        mvc.perform(get("/unlisted"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void unlistedRouteRemainsDeniedAfterAuthentication()
            throws Exception {
        mvc.perform(get("/unlisted")
                        .with(httpBasic("alice", "demo-only")))
                .andExpect(status().isForbidden());
    }

    @Test
    void unknownApiRouteIsNotImplicitlyPermitted()
            throws Exception {
        mvc.perform(get("/api/unknown")
                        .with(httpBasic("alice", "demo-only")))
                .andExpect(status().isForbidden());
    }

    @Test
    void incorrectCredentialsAreStillRejected() throws Exception {
        mvc.perform(get("/admin/panel")
                        .with(httpBasic("bob", "wrong")))
                .andExpect(status().isUnauthorized());
    }
}
```

Run:

```bash
./gradlew test
```

On Windows PowerShell:

```powershell
.\gradlew.bat test
```

These tests send **real HTTP Basic through security filters**, rather than using `.with(user("..."))` to inject a principal and skip password checks. `@SpringBootTest` + `@AutoConfigureMockMvc` loads the application context and filter chain, testing authorization far more faithfully than standalone MVC controller tests.

**Expected outcomes for the demo config:**

| Request | Expectation | Chain |
| --- | --- | --- |
| Anonymous `GET /api/public/status` | 200 | API |
| Anonymous `GET /api/reports` | 401 | API |
| `alice` GET `/api/reports` | 200 | API |
| `bob` GET `/api/reports` | 403 | API |
| Anonymous GET `/admin/panel` | 401 | ADMIN |
| `bob` GET `/admin/panel` | 200 | ADMIN |
| `alice` GET `/admin/panel` | 403 | ADMIN |
| Anonymous GET `/unlisted` | 401 | FALLBACK |
| `alice` GET `/unlisted` | 403 | FALLBACK |
| `alice` GET `/api/unknown` | 403 | API |

This table reflects **expectations from the example configuration**, not a universal status standard for every architecture. `AuthenticationEntryPoint` may return 302 with form login or a custom response with custom entry points. CSRF, dispatcher types, and filter ordering also affect outcomes.

## 9. Running HTTP on Loopback and Observing Results

Start the demo:

```bash
./gradlew bootRun
```

Call the public endpoint:

```bash
curl -i http://127.0.0.1:8080/api/public/status
```

A successful response returns HTTP 200 with a JSON body equivalent to:

```json
{"status":"ok"}
```

Role-protected API route:

```bash
curl -i http://127.0.0.1:8080/api/reports
```

In this HTTP Basic demo, without valid credentials it typically returns `401 Unauthorized`.

Send `alice`'s local credentials:

```bash
curl -i -u alice:demo-only \
  http://127.0.0.1:8080/api/reports
```

Successful JSON body corresponds to:

```json
{
  "report": "quarterly",
  "requestedBy": "alice"
}
```

Request the `/unlisted` route that has a controller yet is not declared public:

```bash
curl -i -u alice:demo-only \
  http://127.0.0.1:8080/unlisted
```

Expected `403 Forbidden`, **with no body containing `secret`**, enforced by the deny-all fallback.

**Security note:** passwords and HTTP Basic in this example are strictly for local use; never send credentials over public HTTP. Production requires TLS, secret management, and authentication suited to the client type.

## 10. Standalone Java 17 Example Illustrating “First Match”

This section is a **pure-Java mental model**, not a Spring Security class and not a replacement for `FilterChainProxy`. It illustrates why placing a match-all rule first shadows every rule behind it.

Create `FirstMatchDemo.java`:

```java
import java.util.List;
import java.util.function.Predicate;

public class FirstMatchDemo {
    record Chain(String name, Predicate<String> matcher) {
        boolean matches(String path) {
            return matcher.test(path);
        }
    }

    static String selected(String path, List<Chain> chains) {
        return chains.stream()
                .filter(chain -> chain.matches(path))
                .map(Chain::name)
                .findFirst()
                .orElse("NONE");
    }

    public static void main(String[] args) {
        List<Chain> proper = List.of(
                new Chain("ADMIN", p -> p.startsWith("/admin/")),
                new Chain("API", p -> p.startsWith("/api/")),
                new Chain("FALLBACK", p -> true));

        for (String path : List.of(
                "/admin/panel", "/api/reports", "/unlisted")) {
            System.out.println(path + " -> " + selected(path, proper));
        }
    }
}
```

Compile and run with Java 17+:

```bash
javac --release 17 FirstMatchDemo.java
java FirstMatchDemo
```

**Exact** stdout of this model:

```text
/admin/panel -> ADMIN
/api/reports -> API
/unlisted -> FALLBACK
```

Simply placing `new Chain("MATCH_ALL", p -> true)` at the front of `List.of(...)` sends every path to `MATCH_ALL` and prevents later matchers from ever being chosen. This models **precedence**, not full Servlet URL matching (context path, servlet path, encoding, and Spring Security matcher semantics).

## 11. Typical Bug A: `securityMatcher` Narrower Than Actual Scope

Example:

```java
http.securityMatcher("/api/v1/**")
    .authorizeHttpRequests(auth -> auth
        .anyRequest().authenticated());
```

If controllers also expose `/api/v2/orders`, the v2 endpoint falls outside the v1 chain. Without a fallback, it can slip through unprotected.

How to handle:

1. Maintain a **route inventory** of all deployed endpoints, not just manually tested URLs.
2. Decide whether v2 routes belong in a shared `/api/**` chain or a dedicated `/api/v2/**` chain.
3. Add negative tests for anonymous and under-privileged callers on v2 routes.
4. Keep a `denyAll` fallback for all unclassified paths.
5. Treat prefix/version changes as **security-boundary changes**, not just `@RequestMapping` edits.

Do not simply change the matcher to `"/**"` on a broad chain and assume it is fixed. If that broad chain precedes the admin chain, you introduce **shadowing**.

## 12. Typical Bug B: Wrong `@Order` Starves Later Chains

Suppose:

```text
@Order(1) -> securityMatcher("/api/**")
             .anyRequest().authenticated()

@Order(2) -> securityMatcher("/api/admin/**")
             .anyRequest().hasRole("ADMIN")
```

`GET /api/admin/reports` already matches `"/api/**"` in the first chain, so it **is never evaluated** against the admin chain below. Ordinary users can reach the admin endpoint even though `hasRole("ADMIN")` sits right there in source.

Fix:

```text
@Order(1) -> /api/admin/**  -> ROLE_ADMIN
@Order(2) -> /api/**        -> matching API permissions
@Order(3) -> catch-all      -> denyAll
```

Or combine the logic into **one** chain and order `requestMatchers("/api/admin/**")` before the broader rule. Both approaches work depending on authentication mechanisms and differing security-filter needs.

When should you split chains?

- When `/api/**` uses bearer tokens while `/web/**` uses sessions/form login.
- When a route group requires specialized authentication filters or mechanisms.
- When system endpoints need an isolated security filter chain.

If routes differ only in **permission rules** while sharing the same authentication mechanism, one chain with ordered `requestMatchers` is usually simpler and avoids cross-bean precedence bugs.

## 13. Typical Bug C: No Fallback Due to Trusting Auto-Config

Dangerous snippet:

```java
@Bean
SecurityFilterChain apiOnly(HttpSecurity http) throws Exception {
    return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                    .anyRequest().authenticated())
            .build();
}
```

If this is the only chain, any controller outside `/api/**` sits **outside `SecurityFilterChain` coverage**. In common Boot setups, declaring this bean causes Boot to skip creating its default chain, leaving no hidden safety net.

Minimal conceptual fix:

```java
@Bean
@Order(100)
SecurityFilterChain fallback(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .anyRequest().denyAll())
            .build();
}
```

This is a **minimal excerpt**; production needs an explicit authentication entry point, session/CSRF setup, and error semantics. It illustrates fallback scoping: omit `.securityMatcher` so the chain catches all remaining requests.

**Warning:** the fallback must still come after every specialized chain; placing a catch-all at `@Order(0)` causes it to deny or intercept all requests ahead of specialized chains. That is safer than leaking data, yet still breaks availability and policy.

## 14. `permitAll`, `denyAll`, and `web.ignoring` Are Not Equivalent

Inside one chain:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public/**").permitAll()
    .anyRequest().denyAll())
```

`/public/**` **still passes through** Spring Security web filters. Security headers, CSRF on relevant methods, authentication processing, or logging can still apply per configuration.

In contrast, using `WebSecurityCustomizer`:

```java
@Bean
WebSecurityCustomizer customizer() {
    return web -> web.ignoring()
            .requestMatchers("/assets/**");
}
```

This illustrates static resources **guaranteed** not to need security filters, requiring `WebSecurityCustomizer` import. Once a URL is ignored, it is not protected by `FilterChainProxy` in the normal way. **Never ignore URLs involving personal data, accounts, API sessions, OAuth2 callbacks, or write actions** just to allow public access.

For normal public endpoints, prefer `.permitAll()` inside a chain over ignoring completely. `denyAll` in a fallback creates a safety net for unclassified routes, yet **cannot undo** an earlier chain that called `permitAll()` too broadly.

## 15. `SecurityFilterChain` vs. Method-Level Security

Sometimes an endpoint falls outside any web filter chain yet its underlying method carries `@PreAuthorize`. Never treat that as a safe fallback architecture for all requests.

Example:

```java
@PreAuthorize("hasRole('ADMIN')")
public Report internalReport() {
    // ...
}
```

This illustrative method works only when method security is enabled and called through the proper Spring proxy. It does not compensate for:

- Other endpoints lacking `@PreAuthorize`.
- `SecurityContext` never being populated because requests bypassed web filters.
- Missing CSRF, security headers, session handling, or exception translation filters.
- *Self-invocation* within the same bean bypassing proxy interception in standard AOP models.
- Security context carrying the wrong authentication type or stale thread state.

Web security and method security complement each other. For Servlet HTTP endpoints, start with **every request matching an appropriate filter chain**, then layer method/object permissions on top.

## 16. Path Analysis: Context Path, Servlet Path, and Matchers

An HTTP request can be viewed through:

- Client request URI.
- Application context path, such as `/billing`.
- Servlet path if `DispatcherServlet` is not mapped at `/`.
- MVC controller mapping path, such as `/api/reports`.
- Actual path after ingress/reverse-proxy rewrites.

For example, the browser requests:

```text
https://example.test/billing/api/reports
```

If `/billing` is the **context path**, Spring Security matching can operate on container-split path components. Do not assume `securityMatcher("/billing/api/**")` matches simply because the browser URL shows `/billing`; check the matcher implementation and servlet/context-path configuration.

Similarly, if ingress rewrites `/portal/api/*` to `/api/*` before forwarding, the backend sees only `/api/reports`. Defining matchers against the **pre-rewrite public path** can prevent the chain from matching.

Practical guidelines:

1. Keep URL/path conventions consistent across `@RequestMapping`, `securityMatcher`, `requestMatchers`, and reverse proxies.
2. With multiple servlets or custom servlet paths, confirm whether matchers read the servlet path or MVC path. With Spring MVC, version-appropriate MVC matchers/builders may be needed; verify semantics on your actual stack.
3. For encoded slashes, duplicate slashes, trailing slashes, or normalization, avoid writing manual `startsWith` checks without understanding container behavior.
4. Test at the application level with configured `context-path`/`servlet-path`, not only MockMvc's default `/`.
5. When upgrading frameworks, matcher implementations or path-pattern strategies can change; rerun full test coverage.

Never make security decisions using manual string-prefix checks in an interceptor when the framework provides official `RequestMatcher` APIs.

## 17. Handling `DispatcherType.FORWARD`, `ERROR`, `ASYNC`

Servlets support **dispatcher types** such as `REQUEST`, `FORWARD`, `ERROR`, and `ASYNC`. Error dispatches or async redispatches can be re-evaluated depending on filter registrations and rules.

For example, an app returns `404` and dispatches to `/error`; if a deny-all fallback also intercepts error dispatches without exception handling in place, the final response can turn into `403`, making you think the main endpoint lacked permission.

You may need to explicitly permit specific internal dispatchers inside **the right chain's authorization rules**, for instance:

```java
.authorizeHttpRequests(auth -> auth
    .dispatcherTypeMatchers(
        DispatcherType.ERROR, DispatcherType.FORWARD).permitAll()
    .anyRequest().denyAll())
```

This is an **illustrative snippet** requiring `import jakarta.servlet.DispatcherType`; permit dispatcher types only when you understand your topology and policy. Never place a broad permit-all rule at the top and assume external requests remain safe, and never use dispatcher allowances to accidentally expose an endpoint needing authentication.

With async Servlets, ensure security context propagation and request lifecycles align; never assume every redispatch creates a fresh authentication or reruns every filter in identical order.

**When debugging a 404 that turns into 403**, check dispatcher types and the active chain rather than deleting the deny-all fallback just to see 404 again.

## 18. CORS Preflight, CSRF, and HTTP Method Matching

If an API supports CORS, browsers may send **`OPTIONS` preflight** requests without user credentials. Testing only `GET /api/reports` does not prove `OPTIONS` or `POST` requests are handled properly.

Notes:

- Configure CORS properly with Spring Security so preflight is not wrongly rejected by authentication filters; however, **an allowed preflight** never grants permission for the actual request.
- `requestMatchers(HttpMethod.GET, "/api/reports")` matches GET only. `POST`/`PATCH` on the same path can fall into `anyRequest().denyAll()`, as intended in the demo.
- With session cookies, Spring Security CSRF protection remains vital for state-changing requests. Never call `.csrf().disable()` app-wide just because a test POST got 403.
- `securityMatcher("/api/**")` does not automatically cover `/v2/api/**` or WebSocket handshake endpoints outside that prefix.
- If a client sends invalid credentials on a `permitAll` route, authentication filters can still react to a bad `Authorization` header; `permitAll` does not disable authentication filters.

You may define a separate public chain for CORS/static assets when genuinely different filter policies are required. However, each new chain adds a **precedence surface that must be tested**, not a free shortcut.

## 19. OAuth2, JWT Resource Servers, and Multiple Auth Mechanisms

Many apps combine:

```text
/admin/**   -> HTTP session / form login
/api/**     -> OAuth2 Resource Server JWT
/oauth2/**  -> OAuth2 Client login callback
/actuator/**-> management policy
fallback    -> denyAll
```

Chain configuration cautions:

1. Enabling `.oauth2ResourceServer().jwt()` on `/api/**` **does not** mean URLs outside the API validate JWTs.
2. If a form-login chain uses `securityMatcher("/web/**")`, endpoints like `/login`, `/oauth2/authorization/*`, and `/login/oauth2/code/*` may fall outside the chain. Filter-provided endpoints must sit inside the chain's scope or have matching endpoint URLs configured.
3. Seeing `oauth2Login()` in source **does not guarantee** callback requests enter that chain.
4. Never leave a permit-all fallback from testing enabled in production.
5. When management/actuator endpoints run on a separate port, inspect the management context/port's security config rather than assuming the main app's `requestMatchers` apply.
6. JWT `SCOPE_*` and `ROLE_*` authorities map differently; wrong authority checks inside a chain cause 403, totally distinct from **no chain matching**.

Splitting `SecurityFilterChain`s makes sense when authentication mechanisms differ sharply. Even so, every filter-created endpoint (login, logout, callback, `/error`) must appear in route-coverage tests.

## 20. Actuator, Static Resources, and Framework-Provided Endpoints

A route inventory listing only your project's `@RestController`s **is incomplete**. Endpoints also arise from:

- Spring Boot Actuator (when the dependency is present).
- Login/logout/OAuth2 callbacks created by Security filters.
- Spring MVC's error controller (`/error`) and internal dispatchers.
- Static resources (`/assets/**`, `/css/**`, `/webjars/**`).
- Framework-generated endpoints, third-party libraries, or additional servlets.
- WebSocket handshake / SSE endpoints.
- Endpoints enabled via feature flags, profiles, or deployment config.

Some endpoints may **not exist** in test environments yet **become active** in staging/production (actuator exposure, profile-specific beans). Never overlook routes registered after security config was written.

When Actuator runs on the **same port**, it may need a dedicated matcher; when Actuator runs on a separate management port/context, inspect the management server's security config. Never assume the main app's fallback guards every service and port.

Genuinely public static assets can use `permitAll`; routes serving user uploads or private reports **must never** be lumped into public `/assets/**` merely because they serve files.

## 21. Diagnostics via Logs and `FilterChainProxy`

When suspecting an unprotected request, prove **whether the request entered any `SecurityFilterChain`**.

### 21.1. Enabling Logs in a Controlled Environment

Temporary debug config:

```yaml
logging:
  level:
    org.springframework.security.web.FilterChainProxy: TRACE
    org.springframework.security.web.access: DEBUG
```

Exact logger names, messages, and verbosity depend on your Spring Security version. Watch which chains `FilterChainProxy` tried to match, which chain won, and where authorization decisions happened.

**Never leave broad system-wide TRACE enabled in production** where logs may capture sensitive request details or inflate latency/cost. Redact credentials, tokens, cookies, and identity assertions. In multi-chain systems, logging normalized matcher/selected chain under audited limits can be helpful.

### 21.2. Distinguishing Three Cases

| Observation | Likely Cause | Action |
| --- | --- | --- |
| `FilterChainProxy` selects no chain | Missing fallback or URL outside all `securityMatcher`s | Add an appropriate catch-all and test with a real endpoint |
| Request enters a different chain than expected | Wrong `@Order` or overly broad matcher | Narrow/reorder chains and add overlap tests |
| Right chain, yet 200 without role | Early `permitAll`/broad rule, wrong authority mapping, or disabled method security | Inspect rules inside the chain; test under-privileged callers |
| Right chain, 401 | Missing authentication, wrong credentials, or entry point | Inspect providers, filters, and HTTP auth mechanism |
| Right chain, 403 | Authenticated lacking permission, CSRF, or another policy | Inspect `GrantedAuthority`, CSRF, and method/object rules |
| 404 on new URL | Route missing or no chain | Use a real route to verify coverage; 404 does not prove security |
| Wrong 302 to `/login` | Chain uses form login/entry point or callback fell outside chain | Check matching for filter-created endpoints |
| 403 after `/error` dispatch | Fallback `denyAll` caught `ERROR`/`FORWARD` | Check dispatcher types and error-path policy |

Never conclude “security is active” merely because a token-bearing request returned 200. The crucial tests are **no-token requests**, **valid tokens lacking permission**, and **routes outside every expected prefix**.

## 22. Workflow to Find and Fix Missed Endpoints

Follow a repeatable diagnostic workflow:

1. **Record the real Servlet-level URL:** method, request URI, context path, servlet path, dispatcher type, and public host/port. Never log credentials.
2. **List all `SecurityFilterChain` beans created** in that Spring application context, with order and matchers. If a separate management context exists, check it independently.
3. **Identify the first chain matching the request.** Do not just search for whichever chain “contains `hasRole`”.
4. **Inspect authorization rules** inside the selected chain in exact `requestMatchers`, HTTP method, and authority order.
5. **Verify the authentication mechanism:** HTTP Basic/form login/JWT/OIDC, entry point, and session policy. A 401 alone does not prove the intended mechanism ran.
6. **Verify a fallback exists** after all specialized chains, denying unclassified URLs.
7. **Write regression tests** on real routes with anonymous, under-privileged, and authorized users. Include a test endpoint outside prefixes to verify the catch-all.
8. **Also test path rewrites, context/servlet paths, and `ERROR`/`ASYNC` dispatches** where used.
9. **Never fix via broad `permitAll`**, `web.ignoring`, or deleting matchers; fix matchers per the intended architecture.
10. **Deploy and monitor** auth denials, chainless requests, and 3xx/401/403 counts while keeping logs free of sensitive data.

If an incident already exposed data, fixing the matcher alone is insufficient: assess unauthorized access scope, audit logs, rotate affected credentials where applicable, and execute organizational incident response steps.

## 23. Pitfalls in Tests and Code Review

### MockMvc Without Spring Security Integration

If you use:

```java
MockMvcBuilders.standaloneSetup(controller).build();
```

this **MockMvc setup does not attach `SecurityFilterChain`**. Controllers can return 200 even when the real app enforces security. To test security configuration, prefer `@SpringBootTest` + `@AutoConfigureMockMvc` or:

```java
MockMvcBuilders.webAppContextSetup(context)
    .apply(springSecurity())
    .build();
```

`webAppContextSetup` is a **test-setup snippet** requiring proper imports and a Spring MVC context. Never see a 200 from a standalone test and assume production is unprotected; conversely, never rely on controller-only tests to prove a route is secure.

### Tests Using `.with(user("admin"))`

Spring Security Test's `user(...)` injects an identity directly without testing real credentials. It suits testing authorization yet does not prove JWT/Basic authentication works. When fixing a chain-selection bug, combine **unauthenticated requests**, real-credential valid requests, and wrong-role requests.

### A Misconfigured Route Might Not Exist in CI

If a route is active only under `@Profile("prod")` or a feature flag, default CI runs cannot exercise its coverage. Run tests/application contexts reflecting deployment config, or use route-vs.-policy inventory/contract checks.

### Accidentally Skipping HTTP Methods

A path `securityMatcher` can select all methods, while `requestMatchers(HttpMethod.GET, ...)` covers GET only. When writing policies for POST/PATCH/DELETE, test both HTTP methods and CSRF. Never let `OPTIONS /** permitAll` spill over to unintended routes.

## 24. Regression Test Scenarios

A solid regression suite beyond the happy path:

| Scenario | Requirement |
| --- | --- |
| Anonymous GET `/api/reports` | Cannot view reports |
| Admin lacking `ANALYST` GET `/api/reports` | Denied |
| Analyst GET `/admin/panel` | Denied |
| Anonymous GET `/unlisted` **with real controller** | Denied by fallback |
| Authenticated GET `/unlisted` | Denied by `denyAll` |
| Authenticated GET `/api/new-secret` | Denied by `denyAll` until explicit policy exists |
| `/api/admin/secret` matching overlapping matchers | Narrower chain / stricter role selected first |
| Swapping `@Order` of API and ADMIN | Regression test fails if privilege weakens |
| Login/callback/`/error` | Proper chain and dispatcher handling per UX |
| URL with ingress context path/prefix | Matches expected chain |
| New API version added | Does not bypass when URL no longer starts with `/api/` |
| Separate management/actuator port | Security of that port tested separately |

Apps need not all return a specific status like 401; statuses depend on entry points/form login. What matters is **enforced protection**, right principals/authorities, and zero data leakage.

## 25. Pre-Production Review Checklist

- Complete inventory of all exposed Servlet/MVC/framework endpoints, including filter-created URLs.
- Every endpoint has an explicit public/private/role/permission/tenant policy.
- `SecurityFilterChain`s carry explicit `@Order` and are reviewed under **first-match** semantics.
- Narrow chains precede broader chains whenever matchers can overlap.
- No catch-all `permitAll()` precedes protected chains.
- Every chain uses an accurately scoped `securityMatcher` or intentionally matches all requests.
- Inside chains, `requestMatchers` are ordered specific-to-general and end with an intentional `anyRequest`.
- A catch-all **fallback** sits last, preferring `denyAll` for unclassified routes.
- `web.ignoring` is not confused with `permitAll`; only genuinely safe static assets are ignored.
- CORS, CSRF, `ERROR`/`FORWARD`/`ASYNC` dispatches, and HTTP methods are handled appropriately.
- An authentication mechanism exists on chains requiring it; login/logout/callbacks are not excluded by `securityMatcher`.
- Context path, servlet path, proxy rewrites, and URL versioning are covered by tests.
- Method security complements rather than replaces web filter coverage.
- Separate Actuator/management ports have their own security checks.
- MockMvc/integration tests cover anonymous, wrong role, right role, real unlisted routes, and overlaps.
- Temporary logs/traces clearly show which chain matched without leaking tokens or passwords.
- Every matcher or chain-order change undergoes code review as a security-policy change.

## Takeaways

Spring Security Servlet selects **the first `SecurityFilterChain` whose matcher matches**. `securityMatcher` decides whether a request **enters the chain**; `requestMatchers` decides **permissions inside the selected chain**; `@Order` decides **which chain is tried first**. If no chain matches, Spring Security web filters can be **bypassed completely**. Once you declare custom `SecurityFilterChain` beans, do not expect Boot to generate an extra default chain to cover the rest. Place specialized chains first, put a **`denyAll` fallback** last, and prove with tests against **real endpoints** that neither anonymous nor under-privileged callers can slip past security.